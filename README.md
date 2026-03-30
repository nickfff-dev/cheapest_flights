# google_flights_cheapest.py

Scrapes Google Flights and returns the **Cheapest** (or Best) tab results for any route, via the [Bright Data SERP API](https://brightdata.com/). City KG MIDs are resolved live from Wikidata — no static airport/city lookup table.

---

## Requirements

```bash
pip install requests selectolax
```

| Dependency | Purpose |
|---|---|
| `requests` | HTTP calls to Bright Data and Wikidata SPARQL |
| `selectolax` | Fast HTML parsing with CSS selectors (Lexbor backend) |

---

## Configuration

Set your Bright Data API key as an environment variable before running:

```bash
# Linux / macOS
export BRIGHTDATA_API_KEY="your_key_here"

# Windows (PowerShell)
$env:BRIGHTDATA_API_KEY="your_key_here"
```

The zone is hardcoded to `serp_api1`. Change `BRIGHTDATA_ZONE` at the top of the script if yours differs.

---

## Usage

### Basic — both cities

```bash
python google_flights_cheapest.py London Milan 2026-04-15
```

### Round-trip — add a return date

```bash
python google_flights_cheapest.py London Milan 2026-04-15 2026-04-22
```

### Mix city and airport code

```bash
# City → airport
python google_flights_cheapest.py London 2026-04-15 --to-airport MXP

# Airport → city
python google_flights_cheapest.py Milan 2026-04-15 --from-airport LHR

# Both airports — no city tokens needed
python google_flights_cheapest.py 2026-04-15 --from-airport LHR --to-airport MXP
```

> Airport codes are passed via flags, never as positional arguments. This avoids ambiguity with 3-letter city abbreviations.

### All filters

```bash
python google_flights_cheapest.py London Milan 2026-04-15 2026-04-22 \
  --adults 2 \
  --cabin business \
  --sort best \
  --time-windows 4
```

### Decode a `tfs=` blob (find KG MIDs for unknown cities)

```bash
python google_flights_cheapest.py --decode CBwQAhonEgoy...
```

---

## All flags

| Flag | Default | Description |
|---|---|---|
| `--from-airport IATA` | — | Origin airport code, e.g. `LHR`. Replaces origin city. |
| `--to-airport IATA` | — | Destination airport code, e.g. `MXP`. Replaces dest city. |
| `--adults N` | `1` | Number of adult passengers. |
| `--cabin` | `economy` | `economy` · `premium_economy` · `business` · `first` |
| `--sort` | `cheapest` | `cheapest` or `best` (Google's sort tabs). |
| `--time-windows N` | `6` | Split the day into N departure-hour windows, fetch each separately, then merge and deduplicate. Must divide 24 evenly: `1 2 3 4 6 8 12 24`. Use `1` to disable splitting. |
| `--dump-cards N` | `0` | Save first N raw card HTMLs to `card_1.html`, `card_2.html` … for debugging selector failures. |
| `--decode TFS` | — | Decode a `tfs=` URL blob and print embedded city KG MIDs and dates, then exit. |

---

## How it works

### 1 — City lookup (Wikidata SPARQL)

City names are resolved to Google Knowledge Graph / Freebase MIDs (format: `/m/0…`) by querying the Wikidata SPARQL endpoint. Results are ordered by sitelink count so the most prominent city wins when multiple entities share the same English label (e.g. London UK beats London Ontario).

Airport codes bypass this step entirely — they are passed directly into the protobuf encoder.

### 2 — Protobuf URL encoding

Google Flights encodes all search parameters in the `tfs=` query parameter as a base64-encoded protobuf blob. This script encodes that blob from scratch using a minimal hand-rolled encoder — no `google-protobuf` dependency needed.

The encoding has been verified **byte-for-byte** against real Google Flights URLs for:

| Scenario | Verified |
|---|---|
| 1 adult, economy, one-way | ✓ |
| 1 adult, economy, round-trip | ✓ |
| 2 adults, business, round-trip | ✓ |
| City → airport | ✓ |
| Airport → city | ✓ |
| Airport → airport | ✓ |
| Time-window filter (dep hour range) | ✓ |

The `tfu=` parameter encodes the active tab — `f4=2` selects Cheapest, omitting `f4` selects Best.

### 3 — Bright Data fetch

The assembled URL is posted to `https://api.brightdata.com/request` with your zone and API key. Bright Data returns the fully rendered HTML. Each window in time-split mode is a separate request.

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

### 5 — Time-window splitting

Google Flights caps the number of results returned per request. With `--time-windows 4` the day is divided into `[00:00–06:00)`, `[06:00–12:00)`, `[12:00–18:00)`, `[18:00–24:00)` and each window is fetched separately. Results are merged and deduplicated by `(airline, departure_time, origin_code, dest_code)` — first-seen wins, so cheaper flights from earlier windows are preserved.

The time filter is encoded as **segment fields f8/f9** inside the protobuf segment, confirmed from a decoded real URL.

---

## Output

Results are written to **`result.json`** in the working directory, sorted by price (cheapest first), and also printed to stdout.

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
  "time_windows": 6,
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
| `co2_kg` | string | Estimated CO2 in kilograms for the whole itinerary |
| `co2_percent_diff` | string | % vs typical flight on this route; negative = greener |
| `carry_on_excluded` | bool | `true` if the price does not include overhead bin access |
| `layover_stops` | array | One object per stop: `airport_code`, `duration`, `airport_name` |

---

## Adding a city not found by Wikidata

If `get_freebase_id` returns "City not found", try the full official name (e.g. `"Ho Chi Minh City"` not `"Saigon"`). For cities that still fail, find the KG MID manually:

1. Search the route on Google Flights in a browser.
2. Copy the `tfs=` value from the address bar.
3. Run:
   ```bash
   python google_flights_cheapest.py --decode <tfs_value>
   ```
4. The decoded output shows the KG MID. You can then pass it directly to `build_google_url()` if using the script as a library.

---

## Troubleshooting

**No flights found** — The Bright Data zone is returning HTML before Google's JS has finished loading flight data. Enable JS rendering in your zone configuration, or increase `--time-windows` to reduce results per request.

**`City not found in Wikidata`** — Check spelling. Use `.title()` casing (e.g. `New York`, not `new york`). Try the full official name.

**`--time-windows N` rejected** — N must divide 24 evenly. Valid values: `1 2 3 4 6 8 12 24`.

**`--dump-cards N`** — Saves raw card HTML to `card_1.html` … so you can inspect what selectolax is actually receiving from Bright Data when selectors return nothing.
