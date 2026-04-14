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

══════════════════════════════════════════════════════════════════════════════
"""
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
        "tfs": build_tfs(legs, adults=adults, cabin=cabin),
        "tfu": build_tfu(sort_order),
        "hl":  "en",
        "gl":  "us",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://www.google.com/travel/flights/search?{qs}"


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
    layover_stops:    list  = None  # list of {airport_name, city, duration}

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
                f"    ↳ {s['airport_name']} {s['city']} {s['duration']}"
            )
        return "\n".join(lines)

def _extract_layover_stops(label: str):
    if "Layover" not in label:
        return []

    # Split only on the FIRST "Layover" so all subsequent ones are preserved
    layover_part = label.split("Layover", 1)[1]

    # Trim trailing noise — try "Carbon" first, then "Select flight"
    for trailer in ("Carbon", "Select flight"):
        if trailer in layover_part:
            layover_part = layover_part.split(trailer)[0]
            break

    pattern = re.findall(
        # Duration: "8 hr 55 min" | "7 hr 31 min" | "3 hr" | "55 min"
        r'(\d+\s*hr(?:\s*\d+\s*min)?|\d+\s*min)'
        # Zero or more qualifier words ("overnight", etc.) then "layover at"
        r'\s+(?:\w+\s+)*layover at\s+'
        # Airport name, then city
        r'(.*?)\s+in\s+(.*?)'
        # Stop before a period, the next "Layover" marker, or end of string
        r'(?=\s*\.|\s*Layover|$)',
        layover_part,
        re.IGNORECASE
    )

    return [
        {
            "airport_name": airport.strip(),
            "city": city.strip(),
            "duration": duration.strip()
        }
        for duration, airport, city in pattern
    ]
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

def _extract_duration(label: str) -> str:
    """
    Pull total duration from the main aria-label sentence.
    Format is always: '… Total duration <DURATION>. Layover  …'
    """
    marker = "Total duration "
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
        dep_node = card.css_first('[aria-label^="Departure time:"][role="text"]') or card.css_first('[aria-label^="Departure time:"]')
        arr_node = card.css_first('[aria-label^="Arrival time:"][role="text"]') or card.css_first('[aria-label^="Arrival time:"]')
        dep_time = dep_node.text(strip=True) if dep_node else "–"
        arr_time = arr_node.text(strip=True) if arr_node else "–"

        # ── Duration ──────────────────────────────────────────────────────────
        dur_node = card.css_first('[aria-label^="Total duration"]')
        duration = dur_node.text(strip=True) if dur_node else _extract_duration(label)

        # ── Stop count ────────────────────────────────────────────────────────
        stops_node = card.css_first('[aria-label$=" flight."]')
        stops      = stops_node.text(strip=True) if stops_node else "–"

        # ── IATA airport codes ────────────────────────────────────────────────
        # Deduplicate preserving first-seen DOM order.
        # iata[0]=origin, iata[1]=dest, iata[2+]=stop airports.
        _codes = [j.text(strip=True) if j else "" for j in card.css('div.YZ7LI.ogfYpf')]

        seen_iata: set[str] = set()
        iata: list[str] = []
        for n in card.css('span[aria-label=""]'):
            t = n.text(strip=True)
            if len(t) == 3 and t.isalpha() and t.isupper() and t not in seen_iata:
                seen_iata.add(t)
                iata.append(t)

        origin_code = iata[0] if len(iata) >= 1 else _codes[0]
        dest_code   = iata[1] if len(iata) >= 2 else _codes[1]

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

        layover_stops: list[dict] = _extract_layover_stops(label)

        # for layover_node in card.css('[aria-label^="Layover ("]'):
        #     lbl = layover_node.attributes.get("aria-label", "")

        #     # Split combined label into one segment per stop
        #     segments = re.split(r'(?=Layover \(\d+ of \d+\))', lbl)
        #     segments = [s.strip() for s in segments if s.strip()]

        #     # Collect IATA codes scoped to this node in DOM order
        #     stop_codes = [
        #         n.text(strip=True)
        #         for n in layover_node.css('span[aria-label=""]')
        #         if (lambda t: len(t) == 3 and t.isalpha() and t.isupper())(n.text(strip=True))
        #     ]

        #     for i, seg in enumerate(segments):
        #         m_dur = re.search(r'is a (.+?) layover at', seg)
        #         dur   = m_dur.group(1).strip() if m_dur else ""

        #         m_apt = re.search(r'layover at (.+?)(?:\s+in\s+|\.$)', seg)
        #         apt   = m_apt.group(1).strip() if m_apt else ""

        #         code  = stop_codes[i] if i < len(stop_codes) else ""

        #         if dur or code:
        #             layover_stops.append({
        #                 "airport_code": code,
        #                 "duration":     dur,
        #                 "airport_name": apt,
        #             })

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