#!/usr/bin/env python3
from __future__ import annotations
import argparse
import base64
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from google_flights_cheapest.google_flights_cheapest import (
parse_flights,decode_tfs,build_google_url,
get_freebase_id,_price_sort_key, CABIN_CLASS, 
Flight, _print_diagnostics,_detect_block,_is_date
)
from scraper.scraper import fetch_flights


_SEP = "─" * 66

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Fetch cheapest Google Flights results via Bright Data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    positional arguments (city names and dates — in order):
    [ORIGIN_CITY]  [DEST_CITY]  DEP_DATE  [RET_DATE]
    Omit a city if replacing it with --from-airport / --to-airport.

    examples:
    python main.py London Milan 2026-04-15
    python main.py London Milan 2026-04-15 2026-04-22
    python main.py London 2026-04-15 --to-airport MXP
    python main.py Milan 2026-04-15 --from-airport LHR
    python main.py 2026-04-15 --from-airport LHR --to-airport MXP
    python main.py London Milan 2026-04-15 --adults 2 --cabin business
    python main.py --decode CBwQAho...
            """,
        )

    parser.add_argument(
        "tokens", nargs="*", metavar="CITY_OR_DATE",
        help="City name(s) and departure/return date(s) in order",
    )
    parser.add_argument(
        "--from-airport", metavar="IATA", dest="from_airport",
        help="Origin airport code, e.g. LHR (replaces origin city)",
    )
    parser.add_argument(
        "--to-airport", metavar="IATA", dest="to_airport",
        help="Destination airport code, e.g. MXP (replaces dest city)",
    )
    parser.add_argument("--adults", type=int, default=1, metavar="N",
                        help="Adult passengers (default: 1)")
    parser.add_argument("--cabin", choices=list(CABIN_CLASS), default="economy",
                        help="Cabin class (default: economy)")
    parser.add_argument("--sort", choices=["cheapest", "best"], default="cheapest",
                        help="Sort order (default: cheapest)")
    parser.add_argument("--decode", metavar="TFS",
                        help="Decode a tfs= blob to reveal KG MIDs, then exit")

    parser.add_argument("--dump-cards", type=int, default=0, metavar="N",
                        dest="dump_cards",
                        help="Save first N raw card HTMLs to card_N.html for debugging")

    args = parser.parse_args()

    # ── --decode mode ─────────────────────────────────────────────────────────
    if args.decode:
        decode_tfs(args.decode)
        return

    # ── Split tokens into dates and city names ────────────────────────────────
    dates  = [t for t in args.tokens if     _is_date(t)]
    cities = [t for t in args.tokens if not _is_date(t)]

    if not dates:
        parser.error("Departure date (YYYY-MM-DD) is required.")
    if len(dates) > 2:
        parser.error(f"Too many dates provided: {dates}")

    dep_date = dates[0]
    ret_date = dates[1] if len(dates) == 2 else None

    # ── Validate airport codes ────────────────────────────────────────────────
    def _validate_iata(code: str, flag: str) -> str:
        c = code.strip().upper()
        if not (len(c) == 3 and c.isalpha()):
            parser.error(f"{flag} must be a 3-letter IATA code, got: {code!r}")
        return c

    from_airport = _validate_iata(args.from_airport, "--from-airport") if args.from_airport else None
    to_airport   = _validate_iata(args.to_airport,   "--to-airport")   if args.to_airport   else None

    # ── Resolve origin ────────────────────────────────────────────────────────
    if (from_airport or to_airport) and len(cities) > 1:
        parser.error("Provide either destination city and origin city,\
            or destination city and --from-airport,\
                or origin city and --to-airport\
                    or --from-airport and --to-airport")
    if not from_airport and not cities:
        parser.error("Provide an origin city or --from-airport.")

    if from_airport:
        origin_name, origin_id = from_airport, from_airport
        city_args = cities
    else:
        try:
            origin_name, origin_id = get_freebase_id(cities[0])
        except ValueError as exc:
            sys.exit(f"[✗] {exc}")
        city_args = cities[1:]

    # ── Resolve destination ───────────────────────────────────────────────────
    if to_airport and city_args:
        parser.error("Provide either a destination city or --to-airport, not both.")
    if not to_airport and not city_args:
        parser.error("Provide a destination city or --to-airport.")

    if to_airport:
        dest_name, dest_id = to_airport, to_airport
    else:
        try:
            dest_name, dest_id = get_freebase_id(city_args[0])
        except ValueError as exc:
            sys.exit(f"[✗] {exc}")

    # ── Validate remaining options ────────────────────────────────────────────
    if args.adults < 1:
        parser.error("--adults must be at least 1")

    sort_order = 2 if args.sort == "cheapest" else 0
    cabin      = CABIN_CLASS[args.cabin]
    trip_label = "Round-trip" if ret_date else "One-way"

    print(f"\n✈  {trip_label}: {origin_name}  →  {dest_name}")
    print(f"   Departure : {dep_date}" + (f"  |  Return: {ret_date}" if ret_date else ""))
    print(f"   Adults    : {args.adults}")
    print(f"   Cabin     : {args.cabin}  (encoded as {cabin})")
    print(f"   Sort      : {args.sort}")
    print(f"   IDs       : {origin_id}  →  {dest_id}")

    url = build_google_url(
        origin_id, dest_id,
        dep_date=dep_date, ret_date=ret_date,
        sort_order=sort_order, adults=args.adults, cabin=cabin,
    )
    print(f"\n[URL] {url}\n")

    MAX_RETRIES = 2
    raw_path    = "flights_raw.html"
    flights: list[Flight] = []

    for attempt in range(1, MAX_RETRIES + 2):
        if attempt > 1:
            print(f"[⟳]  No flights on attempt {attempt - 1} — retrying ({attempt - 1}/{MAX_RETRIES}) …\n")

        print("[→]  Fetching via Bright Data …")
        try:
            html = fetch_flights(url)
        except RuntimeError as exc:
            sys.exit(f"[✗] {exc}")
        except requests.RequestException as exc:
            sys.exit(f"[✗] HTTP error: {exc}")

        with open(raw_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"[✓] HTML saved → {raw_path!r}  ({len(html):,} bytes)\n")

        block = _detect_block(html)
        if block:
            print(f"[⚠]  {block}\n")

        print("[ℹ] Diagnostics:")
        _print_diagnostics(html)
        print()

        flights = parse_flights(html, dump_cards=args.dump_cards)
        if flights:
            break

    # ── JSON output ───────────────────────────────────────────────────────────
    if flights:
        records = [
            {
                "airline":           fl.airline,
                "price":             fl.price,
                "departure_time":    fl.departure_time,
                "arrival_time":      fl.arrival_time,
                "duration":          fl.duration,
                "stops":             fl.stops,
                "origin":            fl.origin_code,
                "destination":       fl.dest_code,
                "co2_kg":            fl.co2_kg,
                "co2_percent_diff":  fl.co2_percent_diff,
                "carry_on_excluded": fl.carry_on_excluded,
                "layover_stops":     fl.layover_stops,
            }
            for fl in flights
        ]

        # Sort by numeric price value before writing — cheapest first
        records.sort(key=_price_sort_key)

        meta = {
            "origin":       origin_name,
            "destination":  dest_name,
            "dep_date":     dep_date,
            "ret_date":     ret_date,
            "adults":       args.adults,
            "cabin":        args.cabin,
            "sort":         args.sort,
            "results":      records,
        }
        with open("result11.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"[✓] Results saved → result.json  ({len(records)} flight(s))")

    # ── Display results ───────────────────────────────────────────────────────
    print(_SEP)
    print(f" {args.sort.capitalize()} flights   {origin_name}  →  {dest_name}   {dep_date}")
    print(_SEP)

    if not flights:
        print(f"""
        ⚠  No flights found after {MAX_RETRIES + 1} attempt(s) per window.

        Verify the route is valid by opening this URL in a browser:
        {url}

        If the route loads in the browser but not here, the Bright Data zone is
        returning HTML before Google's JS has finished loading flight data.
        Enable JS rendering in your Bright Data zone configuration.
        """)
    else:
        print(f"\n{_SEP}")
        print(f"  {len(flights)} flight(s) total  —  sorted {args.sort} first")
        print(f"{_SEP}\n")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    try:
        os.remove(raw_path)
    except OSError:
        pass


if __name__ == "__main__":
    main()