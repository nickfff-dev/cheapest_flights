# EuroScan — European Flight Scanner

Scan cheapest Google Flights from any origin to all ~240 European airports in parallel, with a live progress dashboard.

## Setup

```bash
# 1. Clone / copy files to your VPS
# 2. Set your Bright Data API key
export BRIGHTDATA_API_KEY="your_key_here"

# 3. Install dependencies (Python 3.9+)
pip install -r requirements.txt

# 4. Run the server
python server.py
# or for production:
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1
```

Open http://your-vps-ip:8000 in a browser.

## How it works

1. **Enter an origin** — type a city name (validated via Wikidata) or IATA code (e.g. `LHR`)
2. **Pick a date and time windows** — the day is split into N equal windows (default 3 = 8h each). More windows = more coverage, more requests.
3. **Select airports** — all ~240 European airports are pre-selected; deselect any by country or individually.
4. **Click Scan** — requests run on configurable parallel workers. Watch the live dashboard.
5. **Stop / Resume** — pause the scan at any time; pending jobs resume from where they left off.
6. **Export JSON** — download all found flights as a structured JSON file.

## Architecture

```
server.py
├── GET  /api/airports              → list of European airports
├── GET  /api/validate-origin?q=    → validate city/airport code
├── POST /api/tasks                 → start new scan task
├── GET  /api/tasks/{id}            → poll task progress
├── POST /api/tasks/{id}/stop       → pause execution
├── POST /api/tasks/{id}/resume     → resume from pending jobs
└── GET  /api/tasks/{id}/download   → export all results as JSON

Threading model:
  • Each (airport, time_window) pair is one job
  • A job queue feeds N worker threads (configurable)
  • Stop sets a threading.Event; workers drain after current job
  • Resume spawns new workers for remaining pending jobs
  • Results are deduplicated per airport by (airline, dep_time, origin, dest)
```

## Request volume

| Windows | Airports | Total Requests |
|---------|----------|----------------|
| 1       | 240      | 240            |
| 3       | 240      | 720            |
| 6       | 240      | 1,440          |
| 12      | 240      | 2,880          |

With 10 workers and ~5s/request average, 720 requests ≈ ~6 minutes.

## Notes

- `BRIGHTDATA_API_KEY` must be set in environment
- Tasks are stored in memory only — they are lost on server restart
- The scraper logic lives in `google_flights_cheapest.py` (unchanged from original)
- `economy` cabin class is hardcoded; adults = 1; sort = cheapest