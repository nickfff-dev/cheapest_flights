#!/usr/bin/env python3
"""
server.py — European Flight Scanner API
Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))
from google_flights_cheapest.google_flights_cheapest import (
    get_freebase_id,
    build_google_url,
    fetch_via_brightdata,
    parse_flights,
)

app = FastAPI(title="European Flight Scanner")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ── European airports list ─────────────────────────────────────────────────────
EUROPEAN_AIRPORTS: List[Dict[str, str]] = [
    # UK
    {"code": "LHR", "name": "London Heathrow",       "country": "UK"},
    {"code": "LGW", "name": "London Gatwick",         "country": "UK"},
    {"code": "STN", "name": "London Stansted",        "country": "UK"},
    {"code": "LTN", "name": "London Luton",           "country": "UK"},
    {"code": "LCY", "name": "London City",            "country": "UK"},
    {"code": "MAN", "name": "Manchester",             "country": "UK"},
    {"code": "EDI", "name": "Edinburgh",              "country": "UK"},
    {"code": "BHX", "name": "Birmingham",             "country": "UK"},
    {"code": "GLA", "name": "Glasgow",                "country": "UK"},
    {"code": "BRS", "name": "Bristol",                "country": "UK"},
    {"code": "NCL", "name": "Newcastle",              "country": "UK"},
    {"code": "LBA", "name": "Leeds Bradford",         "country": "UK"},
    {"code": "ABZ", "name": "Aberdeen",               "country": "UK"},
    {"code": "BFS", "name": "Belfast International",  "country": "UK"},
    {"code": "BHD", "name": "Belfast City",           "country": "UK"},
    {"code": "EXT", "name": "Exeter",                 "country": "UK"},
    {"code": "SOU", "name": "Southampton",            "country": "UK"},
    {"code": "NQY", "name": "Newquay",                "country": "UK"},
    {"code": "DSA", "name": "Doncaster Sheffield",    "country": "UK"},
    # France
    {"code": "CDG", "name": "Paris Charles de Gaulle","country": "France"},
    {"code": "ORY", "name": "Paris Orly",             "country": "France"},
    {"code": "NCE", "name": "Nice",                   "country": "France"},
    {"code": "LYS", "name": "Lyon",                   "country": "France"},
    {"code": "MRS", "name": "Marseille",              "country": "France"},
    {"code": "TLS", "name": "Toulouse",               "country": "France"},
    {"code": "NTE", "name": "Nantes",                 "country": "France"},
    {"code": "BOD", "name": "Bordeaux",               "country": "France"},
    {"code": "LIL", "name": "Lille",                  "country": "France"},
    {"code": "SXB", "name": "Strasbourg",             "country": "France"},
    {"code": "BES", "name": "Brest",                  "country": "France"},
    {"code": "BIA", "name": "Bastia",                 "country": "France"},
    {"code": "AJA", "name": "Ajaccio",                "country": "France"},
    {"code": "MPL", "name": "Montpellier",            "country": "France"},
    {"code": "RNS", "name": "Rennes",                 "country": "France"},
    {"code": "CFE", "name": "Clermont-Ferrand",       "country": "France"},
    {"code": "PUF", "name": "Pau",                    "country": "France"},
    {"code": "TUF", "name": "Tours",                  "country": "France"},
    {"code": "LRH", "name": "La Rochelle",            "country": "France"},
    {"code": "XCR", "name": "Paris Vatry",            "country": "France"},
    # Germany
    {"code": "FRA", "name": "Frankfurt",              "country": "Germany"},
    {"code": "MUC", "name": "Munich",                 "country": "Germany"},
    {"code": "DUS", "name": "Dusseldorf",             "country": "Germany"},
    {"code": "BER", "name": "Berlin Brandenburg",     "country": "Germany"},
    {"code": "HAM", "name": "Hamburg",                "country": "Germany"},
    {"code": "CGN", "name": "Cologne Bonn",           "country": "Germany"},
    {"code": "STR", "name": "Stuttgart",              "country": "Germany"},
    {"code": "NUE", "name": "Nuremberg",              "country": "Germany"},
    {"code": "LEJ", "name": "Leipzig",                "country": "Germany"},
    {"code": "HAJ", "name": "Hannover",               "country": "Germany"},
    {"code": "FDH", "name": "Friedrichshafen",        "country": "Germany"},
    {"code": "FKB", "name": "Karlsruhe/Baden-Baden",  "country": "Germany"},
    {"code": "PAD", "name": "Paderborn",              "country": "Germany"},
    {"code": "DRS", "name": "Dresden",                "country": "Germany"},
    {"code": "ERF", "name": "Erfurt",                 "country": "Germany"},
    {"code": "FMM", "name": "Memmingen",              "country": "Germany"},
    {"code": "HHN", "name": "Frankfurt Hahn",         "country": "Germany"},
    # Italy
    {"code": "FCO", "name": "Rome Fiumicino",         "country": "Italy"},
    {"code": "MXP", "name": "Milan Malpensa",         "country": "Italy"},
    {"code": "VCE", "name": "Venice",                 "country": "Italy"},
    {"code": "BGY", "name": "Milan Bergamo",          "country": "Italy"},
    {"code": "NAP", "name": "Naples",                 "country": "Italy"},
    {"code": "LIN", "name": "Milan Linate",           "country": "Italy"},
    {"code": "CTA", "name": "Catania",                "country": "Italy"},
    {"code": "PMO", "name": "Palermo",                "country": "Italy"},
    {"code": "BLQ", "name": "Bologna",                "country": "Italy"},
    {"code": "BRI", "name": "Bari",                   "country": "Italy"},
    {"code": "VRN", "name": "Verona",                 "country": "Italy"},
    {"code": "TRN", "name": "Turin",                  "country": "Italy"},
    {"code": "PSA", "name": "Pisa",                   "country": "Italy"},
    {"code": "CAG", "name": "Cagliari",               "country": "Italy"},
    {"code": "AHO", "name": "Alghero",                "country": "Italy"},
    {"code": "OLB", "name": "Olbia",                  "country": "Italy"},
    {"code": "BDS", "name": "Brindisi",               "country": "Italy"},
    {"code": "FLR", "name": "Florence",               "country": "Italy"},
    {"code": "AOI", "name": "Ancona",                 "country": "Italy"},
    {"code": "CIA", "name": "Rome Ciampino",          "country": "Italy"},
    {"code": "SUF", "name": "Lamezia Terme",          "country": "Italy"},
    {"code": "PMF", "name": "Parma",                  "country": "Italy"},
    {"code": "REG", "name": "Reggio Calabria",        "country": "Italy"},
    # Spain
    {"code": "MAD", "name": "Madrid",                 "country": "Spain"},
    {"code": "BCN", "name": "Barcelona",              "country": "Spain"},
    {"code": "AGP", "name": "Malaga",                 "country": "Spain"},
    {"code": "PMI", "name": "Palma de Mallorca",      "country": "Spain"},
    {"code": "TFS", "name": "Tenerife South",         "country": "Spain"},
    {"code": "LPA", "name": "Gran Canaria",           "country": "Spain"},
    {"code": "ACE", "name": "Lanzarote",              "country": "Spain"},
    {"code": "FUE", "name": "Fuerteventura",          "country": "Spain"},
    {"code": "VLC", "name": "Valencia",               "country": "Spain"},
    {"code": "SVQ", "name": "Seville",                "country": "Spain"},
    {"code": "IBZ", "name": "Ibiza",                  "country": "Spain"},
    {"code": "ALC", "name": "Alicante",               "country": "Spain"},
    {"code": "SDR", "name": "Santander",              "country": "Spain"},
    {"code": "BIO", "name": "Bilbao",                 "country": "Spain"},
    {"code": "ZAZ", "name": "Zaragoza",               "country": "Spain"},
    {"code": "GRX", "name": "Granada",                "country": "Spain"},
    {"code": "VGO", "name": "Vigo",                   "country": "Spain"},
    {"code": "OVD", "name": "Asturias",               "country": "Spain"},
    {"code": "SCQ", "name": "Santiago de Compostela", "country": "Spain"},
    {"code": "MJV", "name": "Murcia",                 "country": "Spain"},
    {"code": "LEI", "name": "Almeria",                "country": "Spain"},
    {"code": "TFN", "name": "Tenerife North",         "country": "Spain"},
    {"code": "MAH", "name": "Menorca",                "country": "Spain"},
    {"code": "XRY", "name": "Jerez",                  "country": "Spain"},
    {"code": "SPC", "name": "La Palma",               "country": "Spain"},
    {"code": "PNA", "name": "Pamplona",               "country": "Spain"},
    {"code": "LCG", "name": "La Coruna",              "country": "Spain"},
    # Netherlands
    {"code": "AMS", "name": "Amsterdam Schiphol",     "country": "Netherlands"},
    {"code": "EIN", "name": "Eindhoven",              "country": "Netherlands"},
    {"code": "RTM", "name": "Rotterdam",              "country": "Netherlands"},
    {"code": "GRQ", "name": "Groningen",              "country": "Netherlands"},
    {"code": "MST", "name": "Maastricht",             "country": "Netherlands"},
    # Belgium
    {"code": "BRU", "name": "Brussels",               "country": "Belgium"},
    {"code": "CRL", "name": "Brussels South Charleroi","country": "Belgium"},
    {"code": "LGG", "name": "Liege",                  "country": "Belgium"},
    {"code": "ANR", "name": "Antwerp",                "country": "Belgium"},
    # Switzerland
    {"code": "ZRH", "name": "Zurich",                 "country": "Switzerland"},
    {"code": "GVA", "name": "Geneva",                 "country": "Switzerland"},
    {"code": "BSL", "name": "Basel Mulhouse",         "country": "Switzerland"},
    {"code": "BRN", "name": "Bern",                   "country": "Switzerland"},
    # Austria
    {"code": "VIE", "name": "Vienna",                 "country": "Austria"},
    {"code": "GRZ", "name": "Graz",                   "country": "Austria"},
    {"code": "SZG", "name": "Salzburg",               "country": "Austria"},
    {"code": "INN", "name": "Innsbruck",              "country": "Austria"},
    {"code": "KLU", "name": "Klagenfurt",             "country": "Austria"},
    {"code": "LNZ", "name": "Linz",                   "country": "Austria"},
    # Portugal
    {"code": "LIS", "name": "Lisbon",                 "country": "Portugal"},
    {"code": "OPO", "name": "Porto",                  "country": "Portugal"},
    {"code": "FAO", "name": "Faro",                   "country": "Portugal"},
    {"code": "FNC", "name": "Funchal (Madeira)",      "country": "Portugal"},
    {"code": "PDL", "name": "Ponta Delgada (Azores)", "country": "Portugal"},
    {"code": "TER", "name": "Terceira (Azores)",      "country": "Portugal"},
    {"code": "HOR", "name": "Horta (Azores)",         "country": "Portugal"},
    # Greece
    {"code": "ATH", "name": "Athens",                 "country": "Greece"},
    {"code": "SKG", "name": "Thessaloniki",           "country": "Greece"},
    {"code": "HER", "name": "Heraklion (Crete)",      "country": "Greece"},
    {"code": "CFU", "name": "Corfu",                  "country": "Greece"},
    {"code": "JMK", "name": "Mykonos",                "country": "Greece"},
    {"code": "RHO", "name": "Rhodes",                 "country": "Greece"},
    {"code": "KGS", "name": "Kos",                    "country": "Greece"},
    {"code": "ZTH", "name": "Zakynthos",              "country": "Greece"},
    {"code": "JTR", "name": "Santorini",              "country": "Greece"},
    {"code": "CHQ", "name": "Chania (Crete)",         "country": "Greece"},
    {"code": "KVA", "name": "Kavala",                 "country": "Greece"},
    {"code": "AOK", "name": "Karpathos",              "country": "Greece"},
    {"code": "EFL", "name": "Kefalonia",              "country": "Greece"},
    {"code": "PVK", "name": "Preveza",                "country": "Greece"},
    {"code": "IOA", "name": "Ioannina",               "country": "Greece"},
    {"code": "KLX", "name": "Kalamata",               "country": "Greece"},
    {"code": "MJT", "name": "Mytilene",               "country": "Greece"},
    {"code": "SMI", "name": "Samos",                  "country": "Greece"},
    {"code": "SKU", "name": "Skiathos",               "country": "Greece"},
    {"code": "JKH", "name": "Chios",                  "country": "Greece"},
    {"code": "PAS", "name": "Paros",                  "country": "Greece"},
    # Denmark
    {"code": "CPH", "name": "Copenhagen",             "country": "Denmark"},
    {"code": "AAL", "name": "Aalborg",                "country": "Denmark"},
    {"code": "BLL", "name": "Billund",                "country": "Denmark"},
    {"code": "AAR", "name": "Aarhus",                 "country": "Denmark"},
    {"code": "EBJ", "name": "Esbjerg",                "country": "Denmark"},
    # Sweden
    {"code": "ARN", "name": "Stockholm Arlanda",      "country": "Sweden"},
    {"code": "GOT", "name": "Gothenburg",             "country": "Sweden"},
    {"code": "MMX", "name": "Malmo",                  "country": "Sweden"},
    {"code": "LLA", "name": "Lulea",                  "country": "Sweden"},
    {"code": "UME", "name": "Umea",                   "country": "Sweden"},
    {"code": "OSD", "name": "Ostersund",              "country": "Sweden"},
    {"code": "VXO", "name": "Vaxjo",                  "country": "Sweden"},
    {"code": "KSD", "name": "Karlstad",               "country": "Sweden"},
    {"code": "NRK", "name": "Norrkoping",             "country": "Sweden"},
    {"code": "ORB", "name": "Orebro",                 "country": "Sweden"},
    {"code": "JKG", "name": "Jonkoping",              "country": "Sweden"},
    {"code": "KLR", "name": "Kalmar",                 "country": "Sweden"},
    # Norway
    {"code": "OSL", "name": "Oslo Gardermoen",        "country": "Norway"},
    {"code": "BGO", "name": "Bergen",                 "country": "Norway"},
    {"code": "TRD", "name": "Trondheim",              "country": "Norway"},
    {"code": "SVG", "name": "Stavanger",              "country": "Norway"},
    {"code": "BOO", "name": "Bodo",                   "country": "Norway"},
    {"code": "TOS", "name": "Tromso",                 "country": "Norway"},
    {"code": "AES", "name": "Alesund",                "country": "Norway"},
    {"code": "KRS", "name": "Kristiansand",           "country": "Norway"},
    {"code": "HAU", "name": "Haugesund",              "country": "Norway"},
    {"code": "TRF", "name": "Oslo Torp Sandefjord",   "country": "Norway"},
    {"code": "MOL", "name": "Molde",                  "country": "Norway"},
    {"code": "LYR", "name": "Longyearbyen (Svalbard)","country": "Norway"},
    {"code": "EVE", "name": "Evenes",                 "country": "Norway"},
    {"code": "ANX", "name": "Andoya",                 "country": "Norway"},
    {"code": "NVK", "name": "Narvik",                 "country": "Norway"},
    {"code": "KKN", "name": "Kirkenes",               "country": "Norway"},
    {"code": "HFT", "name": "Hammerfest",             "country": "Norway"},
    {"code": "HVG", "name": "Honningsvag",            "country": "Norway"},
    # Finland
    {"code": "HEL", "name": "Helsinki",               "country": "Finland"},
    {"code": "OUL", "name": "Oulu",                   "country": "Finland"},
    {"code": "TMP", "name": "Tampere",                "country": "Finland"},
    {"code": "TKU", "name": "Turku",                  "country": "Finland"},
    {"code": "JYV", "name": "Jyvaskyla",              "country": "Finland"},
    {"code": "KUO", "name": "Kuopio",                 "country": "Finland"},
    {"code": "JOE", "name": "Joensuu",                "country": "Finland"},
    {"code": "RVN", "name": "Rovaniemi",              "country": "Finland"},
    {"code": "KAJ", "name": "Kajaani",                "country": "Finland"},
    {"code": "KTT", "name": "Kittila",                "country": "Finland"},
    {"code": "IVL", "name": "Ivalo",                  "country": "Finland"},
    {"code": "KEM", "name": "Kemi-Tornio",            "country": "Finland"},
    # Poland
    {"code": "WAW", "name": "Warsaw Chopin",          "country": "Poland"},
    {"code": "KRK", "name": "Krakow",                 "country": "Poland"},
    {"code": "GDN", "name": "Gdansk",                 "country": "Poland"},
    {"code": "POZ", "name": "Poznan",                 "country": "Poland"},
    {"code": "WRO", "name": "Wroclaw",                "country": "Poland"},
    {"code": "KTW", "name": "Katowice",               "country": "Poland"},
    {"code": "SZZ", "name": "Szczecin",               "country": "Poland"},
    {"code": "RZE", "name": "Rzeszow",                "country": "Poland"},
    {"code": "BZG", "name": "Bydgoszcz",              "country": "Poland"},
    {"code": "LUZ", "name": "Lublin",                 "country": "Poland"},
    {"code": "WMI", "name": "Warsaw Modlin",          "country": "Poland"},
    # Czech Republic
    {"code": "PRG", "name": "Prague",                 "country": "Czech Republic"},
    {"code": "BRQ", "name": "Brno",                   "country": "Czech Republic"},
    {"code": "OSR", "name": "Ostrava",                "country": "Czech Republic"},
    # Hungary
    {"code": "BUD", "name": "Budapest",               "country": "Hungary"},
    {"code": "DEB", "name": "Debrecen",               "country": "Hungary"},
    # Romania
    {"code": "OTP", "name": "Bucharest Henri Coanda", "country": "Romania"},
    {"code": "CLJ", "name": "Cluj-Napoca",            "country": "Romania"},
    {"code": "IAS", "name": "Iasi",                   "country": "Romania"},
    {"code": "TSR", "name": "Timisoara",              "country": "Romania"},
    {"code": "CND", "name": "Constanta",              "country": "Romania"},
    {"code": "SBZ", "name": "Sibiu",                  "country": "Romania"},
    {"code": "BCM", "name": "Bacau",                  "country": "Romania"},
    {"code": "TGM", "name": "Targu Mures",            "country": "Romania"},
    {"code": "OMR", "name": "Oradea",                 "country": "Romania"},
    # Bulgaria
    {"code": "SOF", "name": "Sofia",                  "country": "Bulgaria"},
    {"code": "VAR", "name": "Varna",                  "country": "Bulgaria"},
    {"code": "BOJ", "name": "Burgas",                 "country": "Bulgaria"},
    {"code": "PDV", "name": "Plovdiv",                "country": "Bulgaria"},
    # Croatia
    {"code": "ZAG", "name": "Zagreb",                 "country": "Croatia"},
    {"code": "SPU", "name": "Split",                  "country": "Croatia"},
    {"code": "DBV", "name": "Dubrovnik",              "country": "Croatia"},
    {"code": "ZAD", "name": "Zadar",                  "country": "Croatia"},
    {"code": "PUY", "name": "Pula",                   "country": "Croatia"},
    {"code": "RJK", "name": "Rijeka",                 "country": "Croatia"},
    # Serbia
    {"code": "BEG", "name": "Belgrade",               "country": "Serbia"},
    {"code": "INI", "name": "Nis",                    "country": "Serbia"},
    # Slovakia
    {"code": "BTS", "name": "Bratislava",             "country": "Slovakia"},
    {"code": "KSC", "name": "Kosice",                 "country": "Slovakia"},
    # Slovenia
    {"code": "LJU", "name": "Ljubljana",              "country": "Slovenia"},
    # Estonia
    {"code": "TLL", "name": "Tallinn",                "country": "Estonia"},
    # Latvia
    {"code": "RIX", "name": "Riga",                   "country": "Latvia"},
    # Lithuania
    {"code": "VNO", "name": "Vilnius",                "country": "Lithuania"},
    {"code": "KUN", "name": "Kaunas",                 "country": "Lithuania"},
    {"code": "PLQ", "name": "Palanga",                "country": "Lithuania"},
    # Luxembourg
    {"code": "LUX", "name": "Luxembourg",             "country": "Luxembourg"},
    # Malta
    {"code": "MLA", "name": "Malta",                  "country": "Malta"},
    # Cyprus
    {"code": "LCA", "name": "Larnaca",                "country": "Cyprus"},
    {"code": "PFO", "name": "Paphos",                 "country": "Cyprus"},
    # Ireland
    {"code": "DUB", "name": "Dublin",                 "country": "Ireland"},
    {"code": "SNN", "name": "Shannon",                "country": "Ireland"},
    {"code": "ORK", "name": "Cork",                   "country": "Ireland"},
    {"code": "NOC", "name": "Knock",                  "country": "Ireland"},
    {"code": "KIR", "name": "Kerry",                  "country": "Ireland"},
    # Iceland
    {"code": "KEF", "name": "Reykjavik Keflavik",     "country": "Iceland"},
    {"code": "AEY", "name": "Akureyri",               "country": "Iceland"},
    {"code": "EGS", "name": "Egilsstadir",            "country": "Iceland"},
    # Turkey (Thrace / major European gateway hubs)
    {"code": "IST", "name": "Istanbul Airport",       "country": "Turkey"},
    {"code": "SAW", "name": "Istanbul Sabiha Gokcen", "country": "Turkey"},
    {"code": "ESB", "name": "Ankara",                 "country": "Turkey"},
    {"code": "ADB", "name": "Izmir",                  "country": "Turkey"},
    {"code": "AYT", "name": "Antalya",                "country": "Turkey"},
    {"code": "DLM", "name": "Dalaman",                "country": "Turkey"},
    {"code": "BJV", "name": "Bodrum",                 "country": "Turkey"},
    # Albania
    {"code": "TIA", "name": "Tirana",                 "country": "Albania"},
    # North Macedonia
    {"code": "SKP", "name": "Skopje",                 "country": "North Macedonia"},
    {"code": "OHD", "name": "Ohrid",                  "country": "North Macedonia"},
    # Bosnia
    {"code": "SJJ", "name": "Sarajevo",               "country": "Bosnia"},
    # Montenegro
    {"code": "TGD", "name": "Podgorica",              "country": "Montenegro"},
    {"code": "TIV", "name": "Tivat",                  "country": "Montenegro"},
    # Kosovo
    {"code": "PRN", "name": "Pristina",               "country": "Kosovo"},
    # Moldova
    {"code": "KIV", "name": "Chisinau",               "country": "Moldova"},
    # Georgia
    {"code": "TBS", "name": "Tbilisi",                "country": "Georgia"},
    {"code": "BUS", "name": "Batumi",                 "country": "Georgia"},
    # Armenia
    {"code": "EVN", "name": "Yerevan",                "country": "Armenia"},
    # Azerbaijan
    {"code": "GYD", "name": "Baku",                   "country": "Azerbaijan"},
]

# ── In-memory task store ───────────────────────────────────────────────────────
_tasks: Dict[str, dict] = {}
_tasks_lock = threading.Lock()


# ── API endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/validate-origin")
def validate_origin(q: str):
    """Validate city name (Wikidata) or IATA airport code."""
    q = q.strip()
    if len(q) == 3 and q.isalpha():
        return {"origin_id": q.upper(), "origin_name": q.upper(), "type": "airport"}
    try:
        name, fid = get_freebase_id(q)
        return {"origin_id": fid, "origin_name": name, "type": "city"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/airports")
def list_airports():
    return EUROPEAN_AIRPORTS


class StartTaskRequest(BaseModel):
    origin_id: str
    origin_name: str
    dep_date: str
    time_windows: int = 3
    max_workers: int = 10
    selected_airports: Optional[List[str]] = None


@app.post("/api/tasks")
def start_task(req: StartTaskRequest):
    task_id = str(uuid.uuid4())

    if req.time_windows not in (1, 2, 3, 4, 6, 8, 12, 24):
        raise HTTPException(status_code=400, detail="time_windows must divide 24 evenly")

    airports = req.selected_airports or [a["code"] for a in EUROPEAN_AIRPORTS]
    band_size = 24 // req.time_windows

    jobs: Dict[str, dict] = {}
    for airport_code in airports:
        for i in range(req.time_windows):
            win_start = i * band_size
            win_end = (i + 1) * band_size
            key = f"{airport_code}:{win_start}-{win_end}"
            jobs[key] = {
                "airport_code": airport_code,
                "win_start": win_start,
                "win_end": win_end,
                "status": "pending",
                "flight_count": 0,
                "error": None,
                "start_time": None,
                "end_time": None,
            }

    task = {
        "task_id": task_id,
        "origin_id": req.origin_id,
        "origin_name": req.origin_name,
        "dep_date": req.dep_date,
        "time_windows": req.time_windows,
        "max_workers": req.max_workers,
        "airports": airports,
        "jobs": jobs,
        "results": {},
        "status": "running",
        "created_at": datetime.now().isoformat(),
        "end_time": None,
        "stop_flag": threading.Event(),
    }

    with _tasks_lock:
        _tasks[task_id] = task

    t = threading.Thread(target=_run_task, args=(task_id,), daemon=True)
    t.start()

    return {"task_id": task_id, "total_jobs": len(jobs)}


@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    airport_summary: Dict[str, dict] = {}
    for job in task["jobs"].values():
        code = job["airport_code"]
        if code not in airport_summary:
            airport_summary[code] = {
                "total": 0, "completed": 0, "failed": 0,
                "running": 0, "pending": 0, "flights": 0,
            }
        s = airport_summary[code]
        s["total"] += 1
        s[job["status"]] = s.get(job["status"], 0) + 1
        s["flights"] = len(task["results"].get(code, []))

    total_jobs = len(task["jobs"])
    completed_jobs = sum(1 for j in task["jobs"].values() if j["status"] in ("completed", "failed"))
    failed_jobs    = sum(1 for j in task["jobs"].values() if j["status"] == "failed")
    running_jobs   = sum(1 for j in task["jobs"].values() if j["status"] == "running")

    return {
        "task_id":       task_id,
        "status":        task["status"],
        "origin_name":   task["origin_name"],
        "dep_date":      task["dep_date"],
        "total_jobs":    total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs":   failed_jobs,
        "running_jobs":  running_jobs,
        "created_at":    task["created_at"],
        "end_time":      task["end_time"],
        "airport_summary": airport_summary,
        "total_flights": sum(len(v) for v in task["results"].values()),
    }


@app.post("/api/tasks/{task_id}/stop")
def stop_task(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["stop_flag"].set()
    task["status"] = "stopped"
    return {"message": "Task stopping"}


@app.post("/api/tasks/{task_id}/resume")
def resume_task(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "stopped":
        raise HTTPException(status_code=400, detail="Task is not stopped")
    task["stop_flag"].clear()
    task["status"] = "running"
    t = threading.Thread(target=_run_task, args=(task_id,), daemon=True)
    t.start()
    return {"message": "Task resumed"}


@app.get("/api/tasks/{task_id}/download")
def download_results(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    output = {
        "task_id":       task_id,
        "origin":        task["origin_name"],
        "dep_date":      task["dep_date"],
        "time_windows":  task["time_windows"],
        "generated_at":  datetime.now().isoformat(),
        "results":       task["results"],
    }
    return JSONResponse(content=output)


# ── Job execution ──────────────────────────────────────────────────────────────

def _execute_job(task_id: str, job_info: dict) -> None:
    airport_code = job_info["airport_code"]
    win_start    = job_info["win_start"]
    win_end      = job_info["win_end"]
    key          = f"{airport_code}:{win_start}-{win_end}"

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task or task["stop_flag"].is_set():
            return
        task["jobs"][key]["status"]     = "running"
        task["jobs"][key]["start_time"] = datetime.now().isoformat()
        origin_id = task["origin_id"]
        dep_date  = task["dep_date"]

    try:
        url = build_google_url(
            origin_id, airport_code,
            dep_date=dep_date, ret_date=None,
            sort_order=2, adults=1, cabin=1,
            dep_from_h=win_start, dep_to_h=win_end,
        )
        html    = fetch_via_brightdata(url)
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

        with _tasks_lock:
            task = _tasks.get(task_id)
            if task:
                task["jobs"][key]["status"]       = "completed"
                task["jobs"][key]["end_time"]      = datetime.now().isoformat()
                task["jobs"][key]["flight_count"]  = len(records)

                existing   = task["results"].setdefault(airport_code, [])
                seen_keys  = {
                    (r["airline"], r["departure_time"], r["origin"], r["destination"])
                    for r in existing
                }
                for r in records:
                    k2 = (r["airline"], r["departure_time"], r["origin"], r["destination"])
                    if k2 not in seen_keys:
                        existing.append(r)
                        seen_keys.add(k2)

    except Exception as exc:
        with _tasks_lock:
            task = _tasks.get(task_id)
            if task:
                task["jobs"][key]["status"]   = "failed"
                task["jobs"][key]["error"]    = str(exc)[:300]
                task["jobs"][key]["end_time"] = datetime.now().isoformat()


def _run_task(task_id: str) -> None:
    """Spawn worker threads and feed them pending jobs."""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        stop_flag   = task["stop_flag"]
        max_workers = task["max_workers"]
        pending     = [v for v in task["jobs"].values() if v["status"] == "pending"]

    job_q: queue.Queue = queue.Queue()
    for job in pending:
        job_q.put(job)

    def worker() -> None:
        while not stop_flag.is_set():
            try:
                job_info = job_q.get(timeout=2)
            except queue.Empty:
                break
            if stop_flag.is_set():
                job_q.task_done()
                break
            _execute_job(task_id, job_info)
            job_q.task_done()

    n_workers = min(max_workers, max(len(pending), 1))
    threads   = [threading.Thread(target=worker, daemon=True) for _ in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with _tasks_lock:
        task = _tasks.get(task_id)
        if task and task["status"] == "running":
            all_done = all(j["status"] in ("completed", "failed") for j in task["jobs"].values())
            if all_done:
                task["status"]   = "completed"
                task["end_time"] = datetime.now().isoformat()


# ── Serve frontend ─────────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)