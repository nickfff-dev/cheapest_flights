#!/usr/bin/env python3
"""
skyprowl_server.py — SkyProwl Flight Search API
Run: uvicorn skyprowl_server:app --host 0.0.0.0 --port 8001
"""
from __future__ import annotations

import csv
import io
import os
import sys
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from google_flights_cheapest.google_flights_cheapest import (
    get_freebase_id,
    build_google_url,
    parse_flights,
    _price_sort_key,
    CABIN_CLASS,
)
from scraper.scraper import fetch_flights

app = FastAPI(title="SkyProwl")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory results cache (keyed by UUID, for CSV download) ─────────────────
_results_cache: Dict[str, dict] = {}


# ── Validation ────────────────────────────────────────────────────────────────

def _resolve_location(q: str) -> dict:
    """
    Mirror main.py logic:
      - 3-letter alpha string → airport code (no lookup)
      - anything else         → Wikidata city lookup
    """
    q = q.strip()
    if not q:
        raise ValueError("Location cannot be empty.")
    if len(q) == 3 and q.isalpha():
        code = q.upper()
        return {"location_id": code, "location_name": code, "type": "airport"}
    name, fid = get_freebase_id(q)  # raises ValueError on failure
    return {"location_id": fid, "location_name": name, "type": "city"}


@app.get("/api/validate-location")
def validate_location(q: str):
    """Validate an origin or destination (city name or IATA code)."""
    try:
        return _resolve_location(q)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Search ────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    origin_id:    str
    dest_id:      str
    dep_date:     str
    ret_date:     Optional[str] = None
    adults:       int = 1
    cabin:        str = "economy"
    sort:         str = "cheapest"

    @field_validator("adults")
    @classmethod
    def adults_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("adults must be at least 1")
        return v

    @field_validator("cabin")
    @classmethod
    def cabin_valid(cls, v: str) -> str:
        if v not in CABIN_CLASS:
            raise ValueError(f"cabin must be one of {list(CABIN_CLASS)}")
        return v

    @field_validator("sort")
    @classmethod
    def sort_valid(cls, v: str) -> str:
        if v not in ("cheapest", "best"):
            raise ValueError("sort must be 'cheapest' or 'best'")
        return v


@app.post("/api/search")
def search_flights(req: SearchRequest):
    cabin_int  = CABIN_CLASS[req.cabin]
    sort_order = 2 if req.sort == "cheapest" else 0

    url = build_google_url(
        req.origin_id,
        req.dest_id,
        dep_date=req.dep_date,
        ret_date=req.ret_date,
        sort_order=sort_order,
        adults=req.adults,
        cabin=cabin_int,
    )

    try:
        html = fetch_flights(url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fetch failed: {exc}")

    flights = parse_flights(html)

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
    records.sort(key=_price_sort_key)

    # Cache for CSV download
    key = str(uuid.uuid4())
    _results_cache[key] = {
        "records":    records,
        "origin":     req.origin_id,
        "dest":       req.dest_id,
        "dep_date":   req.dep_date,
        "ret_date":   req.ret_date,
    }

    return {
        "flights":      records,
        "count":        len(records),
        "download_key": key,
    }


# ── CSV download ──────────────────────────────────────────────────────────────

@app.get("/api/download/{key}")
def download_csv(key: str):
    cached = _results_cache.get(key)
    if not cached:
        raise HTTPException(status_code=404, detail="Results not found or expired.")

    records  = cached["records"]
    origin   = cached["origin"].replace("/m/", "").replace(" ", "_")
    dest     = cached["dest"].replace("/m/", "").replace(" ", "_")
    dep_date = cached["dep_date"]
    filename = f"skyprowl_{origin}_{dest}_{dep_date}.csv"

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Airline", "Price", "Origin", "Destination",
        "Depart", "Arrive", "Duration", "Stops",
        "CO2_kg", "CO2_pct", "CarryOn_Excluded", "Layovers",
    ])
    for r in records:
        layovers = "; ".join(
            f"{ls.get('airport_name') or ls.get('city', '')} ({ls.get('duration', '')})"
            for ls in (r.get("layover_stops") or [])
        )
        writer.writerow([
            r["airline"], r["price"], r["origin"], r["destination"],
            r["departure_time"], r["arrival_time"], r["duration"], r["stops"],
            r["co2_kg"], r["co2_percent_diff"],
            "Yes" if r["carry_on_excluded"] else "No",
            layovers,
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Static frontend ───────────────────────────────────────────────────────────
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount(
    "/",
    StaticFiles(directory=_static_dir, html=True),
    name="static",
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, reload=False)