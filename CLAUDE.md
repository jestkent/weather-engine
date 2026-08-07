# Weather Engine

Collects live U.S. temperature observations + official daily climate results to support
**Polymarket weather markets** (e.g. "Highest temperature in NYC today"). Those markets resolve
on the **official NWS daily high/low from the CLI (Climate) report**. The live hourly
observations exist to give an *edge* — you can watch the running high climb toward (or fall
short of) a market threshold before the official number is posted in the afternoon/evening.

## Architecture / data flow

```
config/stations.json        <- single source of truth: 10 stations (station_id, wfo, cli_code, timezone)
        |
        v
weather/common.py             shared: config load, WAL db conn, HTTP retry/backoff, file logging
weather/live_observations.py  --NWS full day history-->    data/observations.db (table: observations)
weather/cli_final.py          --NWS CLI report scrape-->   data/daily_results.db (table: daily_results)
weather/pace_model.py         reads observations.db -> velocity (regression) / running high-low
weather/signal.py             reads observations + NWS forecast -> per-station trade signal
run_forever.py                scheduler: runs live_observations every 15 min, cli_final hourly
app.py                        Streamlit dashboard (chart + forecast)
logs/                         rotating logs: scheduler.log, observations.log, cli_final.log
deploy/                       24/7 keep-alive: Windows Scheduled Task scripts + README
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

Docker: `docker build -t weather-engine . && docker run -d --restart=unless-stopped -p 8501:8501 -v weather_data:/app/data weather-engine`
(runs `run_forever.py` + streamlit together). See **`deploy/README.md`** for 24/7 setup
(Windows Scheduled Task or always-on Docker host) — the collector code is robust, but a
sleeping laptop still pauses collection.

## Production deployment (the real 24/7 host)

**This repo is the source/dev copy. The live collector runs on a Raspberry Pi**, NOT on any
laptop. A local `data/observations.db` here is only as fresh as the last time someone ran the
collector on that machine — it says nothing about production. To judge whether collection is
actually live, check the **Pi**, not this checkout.

- **Host:** `kent-pi5@192.168.2.140` (hostname `kentpi5-desktop`), same box as the IBKR bot.
- **Runs as Docker container `weather-station`** (`restart: always`), started from this repo's
  `Dockerfile` — `run_forever.py` + Streamlit together. `docker` + `containerd` are enabled at
  boot, so it self-heals on crash **and** survives reboots. No systemd unit needed (Docker is the
  supervisor — do NOT add one, it would conflict).
- **Databases live on a bind mount:** `/home/kent-pi5/weather-engine/data -> /app/data`, so both
  `.db` files persist across container rebuilds.
- **Dashboard:** `http://192.168.2.140:8501`.

Check it's live (read-only, from anywhere that can SSH the Pi):

```bash
ssh kent-pi5@192.168.2.140 "docker ps --filter name=weather-station; \
  docker exec weather-station python3 -c \"import sqlite3; \
  print(sqlite3.connect('/app/data/observations.db').execute('SELECT MAX(timestamp) FROM observations').fetchone())\""
```

Latest timestamp within ~1h during US daytime = healthy.

## Databases

**`data/observations.db` — table `observations`** (created by the collector; this is the
schema that actually exists at runtime):
`id, station_id, timestamp, temp_f, humidity, wind_speed, description, raw_json`
with a `UNIQUE(station_id, timestamp)` index. Inserts use `INSERT OR IGNORE` so re-polling the
same (unchanged) NWS observation does not create duplicates.

**`data/daily_results.db` — table `daily_results`**:
`id, station_id, date, high_f, low_f, is_final` with `UNIQUE(station_id, date)`.
`is_final=1` = a **settled** CLI summary (report's temp block is headed `YESTERDAY`);
`is_final=0` = an **intraday/preliminary** report (headed `TODAY`, still `VALID TODAY AS OF …`).
Upsert on `(station_id, date)` **never lets a preliminary overwrite a stored final**.
Rows are dated by the report's own `CLIMATE SUMMARY FOR <date>` line, not wall-clock today.

> DB writes use WAL mode so the Streamlit dashboard can read while the collector writes.
> Schema is created centrally in `weather/common.py` (`init_observations_db` / `init_results_db`).

## Gotchas / domain rules

- **Temperatures from NWS are Celsius**; we convert to °F on ingest. Convert with
  `if temp_f is not None` — never `if temp_f:` (0.0 °C = 32 °F is a real winter reading and is falsy).
- **Daily high/low is a LOCAL-day concept.** UTC midnight is 7–8pm local for US stations, so any
  "today's high" query must use the station's local timezone, not UTC.
- **Collect the FULL day's observations, not just `/observations/latest`.** We pull
  `/observations?start=<local-midnight-UTC>` each cycle so the running high is robust to
  downtime/polling gaps (a cycle after an outage backfills the peak). `INSERT OR IGNORE`
  dedups, making it idempotent. Pass the ISO `start` via `params=` so `+00:00` is
  URL-encoded — baking it into the URL 400s (`+` decodes to a space).
- **NWS API needs a `User-Agent` header** or it returns 403. Read from config `defaults.user_agent`.
- Station gridpoint (station -> lat/lon -> forecast URL) is **static per station**; cache/precompute it.
- Every station in `config/stations.json` needs a `cli_code` or `cli_final.py` skips it.
  **KSOW (Show Low) has `cli_code: null`** — FGZ issues no CLI product for it, so it has
  observations but NO official resolution source (see `cli_note` in config).
- **CLI temp parsing anchors to the `TEMPERATURE (F)` section** and takes the *observed*
  value column — not the first number on the line (which caught the `NORMAL` column, e.g.
  storing PHX 106 instead of the real 110).

## Stations

10 stations, keyed by CLI/Polymarket relevance: KNYC, KLAX, KORD, KSOW, KPHX, KMIA, KSFO, KLAS, KDEN, KSEA.
