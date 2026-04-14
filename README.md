# google_flights_cheapest

Scrapes Google Flights and returns the **Cheapest** (or Best) tab results for any route. City KG MIDs are resolved live from Wikidata — no static airport/city lookup table.

<img width="1910" height="1520" alt="screencapture-127-0-0-1-8001-2026-04-14-06_38_14" src="https://github.com/user-attachments/assets/285e1f21-cda0-43a2-abd3-e81a7660c4ce" />
---


## Requirements

```bash
pip install requests selectolax fastapi uvicorn
```

| Dependency | Purpose |
|---|---|
| `requests` | HTTP calls to Wikidata SPARQL |
| `selectolax` | Fast HTML parsing (Lexbor backend) |
| `fastapi` + `uvicorn` | Web UIs (optional) |

---

## Project structure

```
.
├── google_flights_cheapest/
│   └── google_flights_cheapest.py   # Core library (URL builder, parser)
├── scraper/
│   └── scraper.py                   # HTTP fetch layer
├── main.py                          # CLI entry point
├── server.py                        # European Flight Scanner web UI
└── skyprowl/
    ├── skyprowl_server.py           # SkyProwl single-route web UI
    └── static/
        └── index.html
```

---

## CLI — `main.py`

### Basic — both cities

```bash
python main.py London Milan 2026-04-15
```

### Round-trip — add a return date

```bash
python main.py London Milan 2026-04-15 2026-04-22
```

### Mix city and airport code

```bash
# City → airport
python main.py London 2026-04-15 --to-airport MXP

# Airport → city
python main.py Milan 2026-04-15 --from-airport LHR

# Both airports — no city tokens needed
python main.py 2026-04-15 --from-airport LHR --to-airport MXP
```

> Airport codes are passed via flags, never as positional arguments. This avoids ambiguity with 3-letter city abbreviations.

### All filters

```bash
python main.py London Milan 2026-04-15 2026-04-22 \
  --adults 2 \
  --cabin business \
  --sort best
```

### Decode a `tfs=` blob (find KG MIDs for unknown cities)

```bash
python main.py --decode CBwQAhonEgoy...
```

---

## CLI flags

| Flag | Default | Description |
|---|---|---|
| `--from-airport IATA` | — | Origin airport code, e.g. `LHR`. Replaces origin city. |
| `--to-airport IATA` | — | Destination airport code, e.g. `MXP`. Replaces dest city. |
| `--adults N` | `1` | Number of adult passengers. |
| `--cabin` | `economy` | `economy` · `premium_economy` · `business` · `first` |
| `--sort` | `cheapest` | `cheapest` or `best` |
| `--decode TFS` | — | Decode a `tfs=` URL blob and print embedded city KG MIDs and dates, then exit. |

---

## Web UIs

### SkyProwl — single route search

A single-route search interface with a results table, filters, sortable columns, layover details, and CSV export.

```bash
cd skyprowl
uvicorn skyprowl_server:app --host 0.0.0.0 --port 8001
```

Open `http://localhost:8001`. Enter origin and destination (city name or IATA code), departure date, and optional return date. Fields validate on blur — city names are resolved against Wikidata, airport codes are accepted as-is.

**API endpoints:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/validate-location?q=` | Resolve city name or IATA code |
| `POST` | `/api/search` | Run a search, returns flights + `download_key` |
| `GET` | `/api/download/{key}` | Download results as CSV |

### European Flight Scanner — bulk origin scan

Scans from one origin to all (or a selected subset of) European airports in parallel, with live progress tracking, stop/resume, and JSON download.

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

**API endpoints:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/validate-origin?q=` | Resolve origin city or IATA code |
| `GET` | `/api/airports` | Full European airport list |
| `POST` | `/api/tasks` | Start a scan task |
| `GET` | `/api/tasks/{id}` | Poll task status and per-airport progress |
| `POST` | `/api/tasks/{id}/stop` | Pause a running task |
| `POST` | `/api/tasks/{id}/resume` | Resume a stopped task |
| `GET` | `/api/tasks/{id}/download` | Download all results as JSON |

---

## How it works

### 1 — City lookup (Wikidata SPARQL)

City names are resolved to Google Knowledge Graph / Freebase MIDs (format: `/m/0…`) by querying the Wikidata SPARQL endpoint. Results are ordered by sitelink count so the most prominent city wins when multiple entities share the same English label (e.g. London UK beats London Ontario).

Airport codes bypass this step entirely — they are passed directly into the protobuf encoder.

### 2 — Protobuf URL encoding

Google Flights encodes all search parameters in the `tfs=` query parameter as a base64-encoded protobuf blob. The library encodes that blob from scratch with a minimal hand-rolled encoder — no `google-protobuf` dependency needed.

The encoding has been verified **byte-for-byte** against real Google Flights URLs for:

| Scenario | Verified |
|---|---|
| 1 adult, economy, one-way | ✓ |
| 1 adult, economy, round-trip | ✓ |
| 2 adults, business, round-trip | ✓ |
| City → airport | ✓ |
| Airport → city | ✓ |
| Airport → airport | ✓ |

The `tfu=` parameter encodes the active tab — `f4=2` selects Cheapest, omitting `f4` selects Best.

### 3 — Fetch layer (`scraper/scraper.py`)

The assembled URL is passed to `fetch_flights()` in the scraper module, which returns the fully rendered HTML. The core library has no direct HTTP dependency — swap the scraper implementation without touching the URL builder or parser.

### 4 — HTML parsing (selectolax)

All selectors are anchored to `aria-label` and `role` attributes — never class names or IDs. Google cannot change these without breaking screen-reader compliance, making the parser resilient to front-end deploys.

| Field | Selector |
|---|---|
| Price | `span[role="text"][aria-label*=" dollars/euros/pounds"]` |
| Departure time | `span[aria-label^="Departure time:"][role="text"]` |
| Arrival time | `span[aria-label^="Arrival time:"][role="text"]` |
| Duration | `[aria-label^="Total duration"]` |
| Stops | `[aria-label$=" flight."]` |
| Airport codes | `span[aria-label=""]` with 3-char uppercase text |
| Layover details | `[aria-label^="Layover ("]` — all stops concatenated in one node for multi-stop flights |
| CO2 data | `[data-co2currentflight]` data attributes |
| Airline name | String split on `"flight with "` from the main summary label |

---

## Output

### CLI

Results are written to **`flights_{origin}_{dest}_{dep}{'_'+ret if ret else ''}.json`** in the working directory, sorted by price (cheapest first), and printed to stdout.

### JSON structure

```json
{
  "origin": "London",
  "destination": "MXP",
  "dep_date": "2026-04-15",
  "ret_date": null,
  "adults": 1,
  "cabin": "economy",
  "sort": "cheapest",
  "results": [
    {
      "airline": "Wizz Air",
      "price": "$17",
      "departure_time": "3:15 PM",
      "arrival_time": "6:15 PM",
      "duration": "2 hr",
      "stops": "Nonstop",
      "origin": "LTN",
      "destination": "MXP",
      "co2_kg": "79",
      "co2_percent_diff": "-21",
      "carry_on_excluded": true,
      "layover_stops": []
    },
    {
      "airline": "Ryanair",
      "price": "$78",
      "departure_time": "10:00 PM",
      "arrival_time": "2:15 PM+1",
      "duration": "15 hr 15 min",
      "stops": "2 stops",
      "origin": "STN",
      "destination": "MXP",
      "co2_kg": "217",
      "co2_percent_diff": "117",
      "carry_on_excluded": true,
      "layover_stops": [
        { "airport_code": "DUB", "duration": "7 hr 10 min overnight", "airport_name": "Dublin Airport" },
        { "airport_code": "MAN", "duration": "3 hr 30 min", "airport_name": "Manchester Airport" }
      ]
    }
  ]
}
```

### Field reference

| Field | Type | Notes |
|---|---|---|
| `airline` | string | Operating carrier name |
| `price` | string | Formatted with currency symbol, e.g. `$17`, `€33` |
| `departure_time` | string | Local time, e.g. `3:15 PM` |
| `arrival_time` | string | Local time; `+1` suffix means next day |
| `duration` | string | Total travel time including stops |
| `stops` | string | `Nonstop`, `1 stop`, `2 stops` … |
| `origin` | string | Departure IATA code |
| `destination` | string | Arrival IATA code |
| `co2_kg` | string | Estimated CO2 in kilograms |
| `co2_percent_diff` | string | % vs typical flight on this route; negative = greener |
| `carry_on_excluded` | bool | `true` if overhead bin access is not included in the price |
| `layover_stops` | array | One object per stop: `airport_code`, `duration`, `airport_name` |

---

## Adding a city not found by Wikidata

If `get_freebase_id` returns "City not found", try the full official name (e.g. `"Ho Chi Minh City"` not `"Saigon"`). For cities that still fail, find the KG MID manually:

1. Search the route on Google Flights in a browser.
2. Copy the `tfs=` value from the address bar.
3. Run:
   ```bash
   python main.py --decode <tfs_value>
   ```
4. The decoded output shows the KG MID. Pass it directly to `build_google_url()` if using the library programmatically.

---

## Troubleshooting

**No flights found** — The scraper is returning HTML before the page has fully loaded flight data. Check `scraper/scraper.py` to ensure JS rendering is enabled in your fetch configuration.

**`City not found in Wikidata`** — Check spelling. Use title case (e.g. `New York`, not `new york`). Try the full official name, e.g. `New York City`.

**`Provide either a destination city or --to-airport, not both`** — Airport codes must be passed via `--from-airport` / `--to-airport`, not as positional arguments.
