# Weather Engine

Collects live U.S. temperature observations + official daily climate results to support
**Polymarket weather markets** (e.g. "Highest temperature in NYC today"). Those markets resolve
on the **official NWS daily high/low from the CLI (Climate) report**. The live hourly
observations exist to give an *edge* — you can watch the running high climb toward (or fall
short of) a market threshold before the official number is posted in the afternoon/evening.

## Architecture / data flow

```
config/stations.json        <- single source of truth: 10 stations (id, wfo, cli_code, tz)
        |
        v
weather/live_observations.py  --NWS latest obs (~hourly)-->  data/observations.db (table: observations)
weather/cli_final.py          --NWS CLI report scrape-->     data/daily_results.db (table: daily_results)
weather/pace_model.py         reads observations.db -> velocity / running high-low (CLI report)
weather/signal.py             reads observations + NWS forecast -> per-station trade signal
run_forever.py                scheduler: runs live_observations every 15 min, cli_final hourly
app.py                        Streamlit dashboard (chart + forecast)
```

## Commands (Windows: use `py`, not `python`)

```powershell
py -m pip install -r requirements.txt
py run_forever.py                 # 24/7 collector (obs + CLI). This is the thing to keep running.
py weather/live_observations.py   # one-shot obs collection
py weather/cli_final.py           # one-shot official daily high/low scrape
py weather/pace_model.py          # running high/low + velocity per station
py weather/signal.py              # trade signal: running high vs forecast high vs threshold
py -m streamlit run app.py        # dashboard on :8501
```

Docker: `docker build -t weather-engine . && docker run -p 8501:8501 weather-engine`
(runs `run_forever.py` + streamlit together).

## Databases

**`data/observations.db` — table `observations`** (created by the collector; this is the
schema that actually exists at runtime):
`id, station_id, timestamp, temp_f, humidity, wind_speed, description, raw_json`
with a `UNIQUE(station_id, timestamp)` index. Inserts use `INSERT OR IGNORE` so re-polling the
same (unchanged) NWS observation does not create duplicates.

**`data/daily_results.db` — table `daily_results`**:
`id, station_id, date, high_f, low_f, is_final`. `is_final=1` = scraped from the CLI report
(the resolution source). `INSERT OR REPLACE` on `(station_id, date)`.

> Note: `initialize_db.py` contains an OLDER/alternate schema and is NOT the source of truth —
> the collector scripts create the live tables. Prefer `run_forever.py` / `live_observations.py`.

## Gotchas / domain rules

- **Temperatures from NWS are Celsius**; we convert to °F on ingest. Convert with
  `if temp_f is not None` — never `if temp_f:` (0.0 °C = 32 °F is a real winter reading and is falsy).
- **Daily high/low is a LOCAL-day concept.** UTC midnight is 7–8pm local for US stations, so any
  "today's high" query must use the station's local timezone, not UTC.
- **NWS "latest observation" only updates ~hourly**, but we poll every 15 min. Dedup is essential.
- **NWS API needs a `User-Agent` header** or it returns 403. Keep one set.
- Station gridpoint (station -> lat/lon -> forecast URL) is **static per station**; cache/precompute it.
- Every station in `config/stations.json` needs a `cli_code` or `cli_final.py` skips it.

## Stations

10 stations, keyed by CLI/Polymarket relevance: KNYC, KLAX, KORD, KSOW, KPHX, KMIA, KSFO, KLAS, KDEN, KSEA.
