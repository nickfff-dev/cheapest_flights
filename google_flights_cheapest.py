#!/usr/bin/env python3
"""
google_flights_cheapest.py
══════════════════════════════════════════════════════════════════════════════
Fetch the Google Flights Cheapest tab via Bright Data SERP API.
City KG MIDs are resolved live from Wikidata. Airport codes need no lookup.

Usage
─────
    pip install requests selectolax

    # Both cities
    python google_flights_cheapest.py London Milan 2026-04-15

    # Round-trip
    python google_flights_cheapest.py London Milan 2026-04-15 2026-04-22

    # City + airport code
    python google_flights_cheapest.py London 2026-04-15 --to-airport MXP

    # Airport + city
    python google_flights_cheapest.py Milan 2026-04-15 --from-airport LHR

    # Both airports (no city args needed)
    python google_flights_cheapest.py 2026-04-15 --from-airport LHR --to-airport MXP

    # With filters
    python google_flights_cheapest.py London Milan 2026-04-15 2026-04-19 \\
        --adults 2 --cabin business --sort best

    # Decode a tfs= blob to reveal city KG MIDs
    python google_flights_cheapest.py --decode <tfs_value>

Configuration
─────────────
    export BRIGHTDATA_API_KEY="your_key_here"

══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests
from selectolax.lexbor import LexborHTMLParser

# ── Bright Data configuration ─────────────────────────────────────────────────
BRIGHTDATA_API_KEY  = os.environ.get("BRIGHTDATA_API_KEY", "your_key_here")
BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"
BRIGHTDATA_ZONE     = "serp_api1"


# ══════════════════════════════════════════════════════════════════════════════
# § 1  City KG MID lookup via Wikidata
# ══════════════════════════════════════════════════════════════════════════════

def normalize_city_name(city_name: str) -> str:
    return city_name.strip().title()


def get_freebase_id(city_name: str) -> tuple[str, str]:
    """
    Query Wikidata SPARQL for the Freebase KG MID of a city.

    Returns (canonical_name, freebase_id), e.g. ("London", "/m/04jpl").
    Orders results by sitelink count so the most prominent city wins when
    multiple entities share the same English label (e.g. London UK vs Ontario).
    Raises ValueError if nothing is found or the request fails.
    """
    city_name = normalize_city_name(city_name)
    url   = "https://query.wikidata.org/sparql"
    query = f"""
    SELECT ?freebase_id WHERE {{
      ?city rdfs:label "{city_name}"@en .
      ?city wdt:P646 ?freebase_id .
      ?city wikibase:sitelinks ?links .
      VALUES ?type {{
        wd:Q515      wd:Q1637706  wd:Q174844
        wd:Q1093829  wd:Q3957     wd:Q5119
      }}
      ?city wdt:P31/wdt:P279* ?type .
    }}
    ORDER BY DESC(?links)
    LIMIT 1
    """
    headers = {
        "Accept":     "application/sparql-results+json",
        "User-Agent": "city-freebase-lookup/1.0",
    }
    try:
        resp = requests.get(url, params={"query": query}, headers=headers, timeout=90)
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        if not bindings:
            raise ValueError(
                f"City not found in Wikidata: {city_name!r}\n"
                f"Check spelling or try the full official name."
            )
        return (city_name, bindings[0]["freebase_id"]["value"])
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Wikidata lookup failed for {city_name!r}: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# § 2  Minimal protobuf encoder
#
#  Verified byte-for-byte against six real Google Flights URLs covering:
#    city→city one-way, city→city round-trip, 2-adult business round-trip,
#    city→airport, airport→city, airport→airport.
#
#  Outer message field map (confirmed):
#    f1  = 28                  constant
#    f2  = 2                   constant
#    f3  = segment             repeated — one per leg
#    f8  = 1  ×  adults        one entry per adult, value always 1
#                              1 adult → [40 01], 2 adults → [40 01 40 01]
#    f9  = cabin class         1=economy, 3=business (confirmed)
#                              2=premium_economy, 4=first (assumed same sequence)
#    f14 = 1                   constant
#    f16 = {f1: uint64_max}    no price cap
#    f19 = 2 one-way | 1 round-trip
#
#  Segment field map (confirmed):
#    f2  = "YYYY-MM-DD"
#    f8  = dep_from_h  departure window start hour (optional time filter)
#    f9  = dep_to_h    departure window end hour   (optional time filter)
#    f13 = location sub-message  (origin)
#    f14 = location sub-message  (dest)
#
#  Location sub-message encoding (confirmed from all six URLs):
#    Airport code  → f1=1, f2="LHR"      (plain 3-char IATA)
#    City KG MID   → f1=2, f2="/m/..."   (home city — first leg's origin)
#                  → f1=3, f2="/m/..."   (away city — every other city)
#    "Home" vs "away" is city-specific, not leg-role-specific:
#    the home city keeps f1=2 even when it appears as destination on return leg.
# ══════════════════════════════════════════════════════════════════════════════

CABIN_CLASS: dict[str, int] = {
    "economy":         1,   # confirmed
    "premium_economy": 2,   # assumed
    "business":        3,   # confirmed
    "first":           4,   # assumed
}


def _varint(n: int) -> bytes:
    buf = bytearray()
    while True:
        low7 = n & 0x7F
        n >>= 7
        buf.append(low7 | (0x80 if n else 0))
        if not n:
            break
    return bytes(buf)

def _pb_varint(field_no: int, value: int) -> bytes:
    return _varint(field_no << 3 | 0) + _varint(value)

def _pb_str(field_no: int, value: str) -> bytes:
    b = value.encode("utf-8")
    return _varint(field_no << 3 | 2) + _varint(len(b)) + b

def _pb_msg(field_no: int, payload: bytes) -> bytes:
    return _varint(field_no << 3 | 2) + _varint(len(payload)) + payload


def _encode_location(loc_id: str, home_id: str) -> bytes:
    """
    Encode one location sub-message.

    Airport code (does not start with '/m/')  → f1=1, raw IATA string
    City KG MID (starts with '/m/')           → f1=2 (home) or f1=3 (away)
    """
    if loc_id.startswith("/m/"):
        f1 = 2 if loc_id == home_id else 3
    else:
        f1 = 1
    return _pb_varint(1, f1) + _pb_str(2, loc_id)


def build_tfs(
    legs:       list[tuple[str, str, str]],
    adults:     int = 1,
    cabin:      int = 1,
    dep_from_h: Optional[int] = None,
    dep_to_h:   Optional[int] = None,
) -> str:
    """
    Encode flight-search parameters as a URL-safe base64 protobuf string.

    Parameters
    ----------
    legs       : list of (origin_id, dest_id, departure_date).
                 origin_id / dest_id is either a city KG MID ("/m/...") or an
                 IATA airport code ("LHR"). One tuple = one-way, two = round-trip.
    adults     : adult passenger count — encoded as f8=1 repeated N times.
    cabin      : integer from CABIN_CLASS — encoded as f9.
    dep_from_h : departure window start hour 0-23 (segment f8). Omit for no filter.
    dep_to_h   : departure window end hour 0-24 (segment f9). Omit for no filter.

    Time filter encoding confirmed from decoded URL with filters:
      segment f8 = dep_from_h  (tag 0x40)
      segment f9 = dep_to_h    (tag 0x48)
      Both sit inside the segment, between the date string and the location
      sub-messages (f13/f14).
    """
    home_id  = legs[0][0]
    segments = b""
    for origin_id, dest_id, date in legs:
        seg = _pb_str(2, date)
        if dep_from_h is not None:
            seg += _pb_varint(8, dep_from_h)   # departure window start hour (segment f8)
        if dep_to_h is not None:
            seg += _pb_varint(9, dep_to_h)     # departure window end hour   (segment f9)
        seg += (
            _pb_msg(13, _encode_location(origin_id, home_id))
            + _pb_msg(14, _encode_location(dest_id,   home_id))
        )
        segments += _pb_msg(3, seg)

    outer = (
        _pb_varint(1, 28)
        + _pb_varint(2, 2)
        + segments
        + _pb_varint(8, 1) * adults
        + _pb_varint(9, cabin)
        + _pb_varint(14, 1)
        + _pb_msg(16, _pb_varint(1, (1 << 64) - 1))
        + _pb_varint(19, 1 if len(legs) > 1 else 2)
    )
    return base64.urlsafe_b64encode(outer).decode("ascii").rstrip("=")


# ══════════════════════════════════════════════════════════════════════════════
# § 3  Build tfu  (sort order / active tab)
#
#  Decoded from EgoIABABGAAgAigB:
#    field-2 message → {f1:0, f2:1, f3:0, f4:sort_order, f5:1}
#    f4=2 → Cheapest tab,  f4 omitted → Best tab
# ══════════════════════════════════════════════════════════════════════════════

def build_tfu(sort_order: int = 2) -> str:
    """sort_order: 2=Cheapest (default), 0=Best"""
    inner = (
        _pb_varint(1, 0)
        + _pb_varint(2, 1)
        + _pb_varint(3, 0)
        + (_pb_varint(4, sort_order) if sort_order else b"")
        + _pb_varint(5, 1)
    )
    return base64.urlsafe_b64encode(_pb_msg(2, inner)).decode("ascii").rstrip("=")


# ══════════════════════════════════════════════════════════════════════════════
# § 4  URL builder
# ══════════════════════════════════════════════════════════════════════════════

def build_google_url(
    origin_id:  str,
    dest_id:    str,
    dep_date:   str,
    ret_date:   Optional[str] = None,
    sort_order: int = 2,
    adults:     int = 1,
    cabin:      int = 1,
    dep_from_h: Optional[int] = None,
    dep_to_h:   Optional[int] = None,
) -> str:
    """
    Assemble the Google Flights search URL.

    origin_id / dest_id may be a city KG MID or an IATA airport code.
    dep_from_h / dep_to_h optionally restrict the departure time window (hours 0-24).
    """
    if ret_date:
        legs = [(origin_id, dest_id, dep_date), (dest_id, origin_id, ret_date)]
    else:
        legs = [(origin_id, dest_id, dep_date)]

    params = {
        "tfs": build_tfs(legs, adults=adults, cabin=cabin,
                         dep_from_h=dep_from_h, dep_to_h=dep_to_h),
        "tfu": build_tfu(sort_order),
        "hl":  "en",
        "gl":  "us",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://www.google.com/travel/flights/search?{qs}"


# ══════════════════════════════════════════════════════════════════════════════
# § 5  Bright Data SERP API fetch
# ══════════════════════════════════════════════════════════════════════════════

def fetch_via_brightdata(google_url: str) -> str:
    """
    POST google_url to the Bright Data SERP API and return the HTML body.
    Handles both raw-HTML and JSON response formats.
    """
    if BRIGHTDATA_API_KEY in ("", "YOUR_API_KEY_HERE"):
        raise RuntimeError(
            "Bright Data API key not configured.\n"
            "Set the BRIGHTDATA_API_KEY environment variable:\n"
            "    export BRIGHTDATA_API_KEY='your_key_here'"
        )
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
    }
    payload = {
        "zone":   BRIGHTDATA_ZONE,
        "url":    google_url,
        "format": "raw",
    }
    resp = requests.post(BRIGHTDATA_ENDPOINT, json=payload, headers=headers, timeout=90)
    resp.raise_for_status()

    if "application/json" in resp.headers.get("Content-Type", ""):
        try:
            data = resp.json()
            for key in ("body", "html", "content", "text"):
                if isinstance(data.get(key), str) and len(data[key]) > 1_000:
                    return data[key]
            if isinstance(data, list) and data:
                item = data[0]
                for key in ("body", "html", "content"):
                    if isinstance(item.get(key), str):
                        return item[key]
            return json.dumps(data)
        except (json.JSONDecodeError, AttributeError):
            pass
    return resp.text


# ══════════════════════════════════════════════════════════════════════════════
# § 6  HTML parser
#
#  All selectors use aria-label / role attributes — Google cannot change these
#  without breaking screen-reader compliance.
#
#  Selector map (confirmed from real response HTML):
#    li:has(div[role="link"][aria-label^="From "])    — one flight card
#    div[role="link"][aria-label^="From "]            — main summary label
#    span[role="text"][aria-label*=" dollars/euros/pounds"] — price
#    span[aria-label^="Departure time:"][role="text"] — departure time
#    span[aria-label^="Arrival time:"][role="text"]   — arrival time
#    [aria-label^="Total duration"]                   — flight duration
#    [aria-label$=" flight."]                         — stop count
#    span[aria-label=""]  (3 uppercase alpha chars)   — IATA airport codes
#    [aria-label^="Layover ("]                        — layover container
#                                                       (one node may hold ALL
#                                                        stops for multi-stop flights)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Flight:
    departure_time:   str  = "–"
    arrival_time:     str  = "–"
    airline:          str  = "Unknown"
    duration:         str  = "–"
    stops:            str  = "–"
    price:            str  = "–"
    origin_code:      str  = ""
    dest_code:        str  = ""
    co2_kg:           str  = ""    # e.g. "79"
    co2_percent_diff: str  = ""    # e.g. "-21" (negative = below avg, positive = above)
    carry_on_excluded: bool = False
    layover_stops:    list  = None  # list of {airport_code, duration, airport_name}

    def __post_init__(self):
        if self.layover_stops is None:
            self.layover_stops = []

    def __str__(self) -> str:
        route = f"{self.origin_code}→{self.dest_code}" if self.origin_code else ""
        co2   = f"  CO2 {self.co2_kg}kg ({self.co2_percent_diff}%)" if self.co2_kg else ""
        warn  = "  [no carry-on]" if self.carry_on_excluded else ""
        lines = [
            f"  {self.airline}  {route}",
            f"    {self.departure_time} → {self.arrival_time}"
            f"  ·  {self.duration}  ·  {self.stops}  ·  {self.price}{warn}{co2}",
        ]
        for s in self.layover_stops:
            lines.append(
                f"    ↳ {s['airport_code']}  {s['duration']}  {s['airport_name']}"
            )
        return "\n".join(lines)


def _extract_airline(label: str) -> str:
    """
    Pull airline name from the main aria-label sentence.
    Format is always: '… flight with <AIRLINE>. Leaves …'
    """
    marker = "flight with "
    if marker not in label:
        return "Unknown"
    after = label[label.index(marker) + len(marker):]
    dot   = after.find(".")
    return after[:dot].strip() if dot != -1 else after.strip()


def parse_flights(html: str, dump_cards: int = 0) -> list[Flight]:
    """
    Extract flight listings from rendered Google Flights HTML.

    Uses selectolax LexborHTMLParser throughout — no class names, no IDs,
    no hardcoded airline or airport strings.

    Parameters
    ----------
    html       : raw HTML string from Bright Data
    dump_cards : if > 0, write the first N card HTMLs to card_N.html for
                 inspection (uses node.html — the selectolax raw-HTML accessor)
    """
    tree    = LexborHTMLParser(html)
    flights: list[Flight] = []

    # ── Locate all flight cards ───────────────────────────────────────────────
    cards = tree.css('li:has(div[role="link"][aria-label^="From "])')

    for idx, card in enumerate(cards[:dump_cards]):
        path = f"card_{idx + 1}.html"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(card.html or "")
        print(f"[debug] card {idx + 1} HTML → {path!r}")

    for card in cards:

        # ── Main summary aria-label ───────────────────────────────────────────
        # Fixed English sentence containing airline name, carry-on flag,
        # and all layover details for every stop in one string.
        link  = card.css_first('div[role="link"][aria-label^="From "]')
        if not link:
            continue
        label = link.attributes.get("aria-label", "")

        airline           = _extract_airline(label)
        carry_on_excluded = "does not include overhead bin" in label

        # ── Price ─────────────────────────────────────────────────────────────
        price_node = (
            card.css_first('span[role="text"][aria-label*=" dollars"]')
            or card.css_first('span[role="text"][aria-label*=" euros"]')
            or card.css_first('span[role="text"][aria-label*=" pounds"]')
        )
        if not price_node:
            continue
        price = price_node.text(strip=True)

        # ── Times ─────────────────────────────────────────────────────────────
        dep_node = card.css_first('[aria-label^="Departure time:"][role="text"]')
        arr_node = card.css_first('[aria-label^="Arrival time:"][role="text"]')
        dep_time = dep_node.text(strip=True) if dep_node else "–"
        arr_time = arr_node.text(strip=True) if arr_node else "–"

        # ── Duration ──────────────────────────────────────────────────────────
        dur_node = card.css_first('[aria-label^="Total duration"]')
        duration = dur_node.text(strip=True) if dur_node else "–"

        # ── Stop count ────────────────────────────────────────────────────────
        stops_node = card.css_first('[aria-label$=" flight."]')
        stops      = stops_node.text(strip=True) if stops_node else "–"

        # ── IATA airport codes ────────────────────────────────────────────────
        # Deduplicate preserving first-seen DOM order.
        # iata[0]=origin, iata[1]=dest, iata[2+]=stop airports.
        seen_iata: set[str] = set()
        iata: list[str] = []
        for n in card.css('span[aria-label=""]'):
            t = n.text(strip=True)
            if len(t) == 3 and t.isalpha() and t.isupper() and t not in seen_iata:
                seen_iata.add(t)
                iata.append(t)

        origin_code = iata[0] if len(iata) >= 1 else ""
        dest_code   = iata[1] if len(iata) >= 2 else ""

        # ── Layover stops ─────────────────────────────────────────────────────
        # Google puts ALL layovers for a multi-stop flight into a SINGLE node
        # whose aria-label concatenates every "Layover (N of M) is a …" sentence.
        #
        # Example (2-stop flight):
        #   "Layover (1 of 2) is a 7 hr 10 min overnight layover at Dublin Airport
        #    in Dublin. Layover (2 of 2) is a 3 hr 30 min layover at Manchester
        #    Airport in Manchester."
        #
        # We split on the "Layover (" boundary to recover each individual stop,
        # then pair with the IATA codes found inside the same node in DOM order.
        layover_stops: list[dict] = []
        for layover_node in card.css('[aria-label^="Layover ("]'):
            lbl = layover_node.attributes.get("aria-label", "")

            # Split combined label into one segment per stop
            segments = re.split(r'(?=Layover \(\d+ of \d+\))', lbl)
            segments = [s.strip() for s in segments if s.strip()]

            # Collect IATA codes scoped to this node in DOM order
            stop_codes = [
                n.text(strip=True)
                for n in layover_node.css('span[aria-label=""]')
                if (lambda t: len(t) == 3 and t.isalpha() and t.isupper())(n.text(strip=True))
            ]

            for i, seg in enumerate(segments):
                m_dur = re.search(r'is a (.+?) layover at', seg)
                dur   = m_dur.group(1).strip() if m_dur else ""

                m_apt = re.search(r'layover at (.+?)(?:\s+in\s+|\.$)', seg)
                apt   = m_apt.group(1).strip() if m_apt else ""

                code  = stop_codes[i] if i < len(stop_codes) else ""

                if dur or code:
                    layover_stops.append({
                        "airport_code": code,
                        "duration":     dur,
                        "airport_name": apt,
                    })

        # ── CO2 emissions ─────────────────────────────────────────────────────
        co2_kg = co2_pct = ""
        em_node = card.css_first("[data-co2currentflight]")
        if em_node:
            raw_g = em_node.attributes.get("data-co2currentflight", "")
            if raw_g.isdigit():
                co2_kg = str(int(raw_g) // 1000)
            co2_pct = em_node.attributes.get("data-percentagediff", "")

        flights.append(Flight(
            departure_time    = dep_time,
            arrival_time      = arr_time,
            airline           = airline,
            duration          = duration,
            stops             = stops,
            price             = price,
            origin_code       = origin_code,
            dest_code         = dest_code,
            co2_kg            = co2_kg,
            co2_percent_diff  = co2_pct,
            carry_on_excluded = carry_on_excluded,
            layover_stops     = layover_stops,
        ))

    return flights


# ══════════════════════════════════════════════════════════════════════════════
# § 6b  Time-window aggregator
#
#  Splits the departure day into N equal windows and fetches each separately,
#  then deduplicates and merges all results into one list.
#
#  Deduplication key: (airline, departure_time, origin_code, dest_code).
#  First-seen wins so the cheapest-sorted first window dominates on ties.
# ══════════════════════════════════════════════════════════════════════════════

def scrape_with_time_split(
    origin_id:   str,
    dest_id:     str,
    dep_date:    str,
    ret_date:    Optional[str],
    sort_order:  int,
    adults:      int,
    cabin:       int,
    n_windows:   int,
    max_retries: int,
    raw_path:    str,
    dump_cards:  int,
) -> list[Flight]:
    """
    Fetch one full day of flights by splitting into n_windows time bands
    and merging all results.

    Each window runs the same fetch-with-retry loop used in single-window mode.
    Results are deduplicated by (airline, departure_time, origin_code, dest_code).
    """
    band_size = 24 // n_windows
    windows   = [(i * band_size, (i + 1) * band_size) for i in range(n_windows)]

    seen:   set[tuple]   = set()
    merged: list[Flight] = []

    for win_start, win_end in windows:
        label = f"{win_start:02d}:00–{win_end:02d}:00"
        print(f"\n[⏱]  Window {label} …")

        url = build_google_url(
            origin_id, dest_id,
            dep_date=dep_date, ret_date=ret_date,
            sort_order=sort_order, adults=adults, cabin=cabin,
            dep_from_h=win_start, dep_to_h=win_end,
        )
        print(url,'ndio hii')
        window_flights: list[Flight] = []
        for attempt in range(1, max_retries + 2):
            if attempt > 1:
                print(f"[⟳]  No flights on attempt {attempt - 1} — retrying ({attempt - 1}/{max_retries}) …")

            print(f"[→]  Fetching {label} via Bright Data …")
            try:
                html = fetch_via_brightdata(url)
            except RuntimeError as exc:
                sys.exit(f"[✗] {exc}")
            except requests.RequestException as exc:
                sys.exit(f"[✗] HTTP error: {exc}")

            with open(raw_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            print(f"[✓] HTML saved → {raw_path!r}  ({len(html):,} bytes)")

            block = _detect_block(html)
            if block:
                print(f"[⚠]  {block}")

            _print_diagnostics(html)

            window_flights = parse_flights(html, dump_cards=dump_cards)
            if window_flights:
                break

        new_count = 0
        for fl in window_flights:
            key = (fl.airline, fl.departure_time, fl.origin_code, fl.dest_code)
            if key not in seen:
                seen.add(key)
                merged.append(fl)
                new_count += 1

        print(f"[✓]  Window {label}: {len(window_flights)} fetched, {new_count} new")

    return merged


# ══════════════════════════════════════════════════════════════════════════════
# § 7  --decode utility
#
#  Parses raw tfs= protobuf bytes to print the embedded city KG MIDs and dates.
#  Uses re.finditer on raw bytes — there is no selectolax equivalent for binary
#  protobuf data.
# ══════════════════════════════════════════════════════════════════════════════

def decode_tfs(tfs_value: str) -> None:
    raw     = base64.urlsafe_b64decode(tfs_value + "==")
    kg_mids = [m.group().decode() for m in re.finditer(rb'/m/[0-9A-Za-z_]+', raw)]
    dates   = [m.group().decode() for m in re.finditer(rb'20\d\d-\d\d-\d\d',  raw)]
    print("\n── Decoded tfs ─────────────────────────────────────────────────")
    print(f"  Dates   : {dates}")
    print(f"  KG MIDs : {kg_mids}")
    if len(kg_mids) >= 2:
        print(f"\n  Origin  : {kg_mids[0]}")
        print(f"  Dest    : {kg_mids[1]}")
        if len(kg_mids) == 4:
            print(f"  Return  : {kg_mids[2]} → {kg_mids[3]}")
    print("────────────────────────────────────────────────────────────────\n")


# ══════════════════════════════════════════════════════════════════════════════
# § 8  Diagnostics
# ══════════════════════════════════════════════════════════════════════════════

def _detect_block(html: str) -> Optional[str]:
    lower = html.lower()
    if "captcha" in lower or "recaptcha" in lower:
        return "CAPTCHA challenge detected"
    if "sorry, we could not process your request" in lower:
        return "Rate-limited / flagged by Google"
    if len(html) < 5_000:
        return f"Suspiciously short response ({len(html):,} bytes)"
    return None


def _print_diagnostics(html: str) -> None:
    tree    = LexborHTMLParser(html)
    scripts = tree.css("script")
    af_cbs  = [s for s in scripts if "AF_initDataCallback" in (s.text(deep=False) or "")]
    cards   = tree.css('li:has(div[role="link"][aria-label^="From "])')
    print(f"  HTML size                  : {len(html):,} bytes")
    print(f"  <script> tags              : {len(scripts)}")
    print(f"  AF_initDataCallback blocks : {len(af_cbs)}")
    print(f"  Flight cards found         : {len(cards)}")


# ══════════════════════════════════════════════════════════════════════════════
# § 9  Main
# ══════════════════════════════════════════════════════════════════════════════

_SEP = "─" * 66


def _is_date(s: str) -> bool:
    """True if s is exactly a YYYY-MM-DD date string (zero-padded)."""
    if len(s) != 10:
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _price_sort_key(record: dict) -> float:
    """
    Extract a numeric sort key from a price string like "$78", "€33", "£27".
    Strips all non-digit characters and returns the number.
    Records with unparseable prices sort to the end.
    """
    digits = "".join(c for c in record.get("price", "") if c.isdigit())
    return float(digits) if digits else float("inf")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="google_flights_cheapest.py",
        description="Fetch cheapest Google Flights results via Bright Data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
positional arguments (city names and dates — in order):
  [ORIGIN_CITY]  [DEST_CITY]  DEP_DATE  [RET_DATE]
  Omit a city if replacing it with --from-airport / --to-airport.

examples:
  python google_flights_cheapest.py London Milan 2026-04-15
  python google_flights_cheapest.py London Milan 2026-04-15 2026-04-22
  python google_flights_cheapest.py London 2026-04-15 --to-airport MXP
  python google_flights_cheapest.py Milan 2026-04-15 --from-airport LHR
  python google_flights_cheapest.py 2026-04-15 --from-airport LHR --to-airport MXP
  python google_flights_cheapest.py London Milan 2026-04-15 --adults 2 --cabin business
  python google_flights_cheapest.py --decode CBwQAho...
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
    parser.add_argument("--time-windows", type=int, default=12, metavar="N",
                        dest="time_windows",
                        help=(
                            "Split the day into N departure-hour windows and fetch each "
                            "separately, then merge and deduplicate results. "
                            "N must divide 24 evenly (1, 2, 3, 4, 6, 8, 12, 24). "
                            "Default: 6."
                        ))
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
    if from_airport and cities:
        parser.error("Provide either an origin city or --from-airport, not both.")
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
    if 24 % args.time_windows != 0:
        parser.error(f"--time-windows must divide 24 evenly (1,2,3,4,6,8,12,24), got {args.time_windows}")

    sort_order = 2 if args.sort == "cheapest" else 0
    cabin      = CABIN_CLASS[args.cabin]
    trip_label = "Round-trip" if ret_date else "One-way"

    print(f"\n✈  {trip_label}: {origin_name}  →  {dest_name}")
    print(f"   Departure : {dep_date}" + (f"  |  Return: {ret_date}" if ret_date else ""))
    print(f"   Adults    : {args.adults}")
    print(f"   Cabin     : {args.cabin}  (encoded as {cabin})")
    print(f"   Sort      : {args.sort}")
    print(f"   Windows   : {args.time_windows}  ({24 // args.time_windows}h each)")
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

    # ── Time-window split mode ────────────────────────────────────────────────
    if args.time_windows > 1:
        print(f"[⏱]  Splitting day into {args.time_windows} windows …")
        flights = scrape_with_time_split(
            origin_id   = origin_id,
            dest_id     = dest_id,
            dep_date    = dep_date,
            ret_date    = ret_date,
            sort_order  = sort_order,
            adults      = args.adults,
            cabin       = cabin,
            n_windows   = args.time_windows,
            max_retries = MAX_RETRIES,
            raw_path    = raw_path,
            dump_cards  = args.dump_cards,
        )

    # ── Single-window mode (original retry loop — unchanged) ──────────────────
    else:
        for attempt in range(1, MAX_RETRIES + 2):
            if attempt > 1:
                print(f"[⟳]  No flights on attempt {attempt - 1} — retrying ({attempt - 1}/{MAX_RETRIES}) …\n")

            print("[→]  Fetching via Bright Data …")
            try:
                html = fetch_via_brightdata(url)
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
            "time_windows": args.time_windows,
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
        for i, fl in enumerate(flights, 1):
            print(f"\n[{i:>2}]\n{fl}")
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