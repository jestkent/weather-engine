# Keeping the collector running 24/7

The engine's edge depends on **continuous** collection through the afternoon — a gap
during peak heating means the running high reads low. The collector itself is robust
(retries, self-healing backfill, per-cycle error isolation), but *something* has to keep
the process alive.

## Current production deployment — Raspberry Pi (this is where it actually runs)

The live collector runs **on a Raspberry Pi, not on any laptop.** Options A/B below are
generic recipes; this is the deployment in use today:

- **Host:** `kent-pi5@192.168.2.140` (hostname `kentpi5-desktop`) — same box as the IBKR bot.
- **Container:** `weather-station`, built from this repo's `Dockerfile`, run with
  `--restart=always`. Runs `run_forever.py` + Streamlit together. `docker`/`containerd` are
  enabled at boot, so it self-heals on crash **and** survives reboots. **Do not add a systemd
  unit — Docker already supervises it; a second supervisor would fight it.**
- **Data:** bind-mounted `/home/kent-pi5/weather-engine/data -> /app/data` (DBs survive rebuilds).
- **Dashboard:** `http://192.168.2.140:8501`.

Verify it's live (read-only):

```bash
ssh kent-pi5@192.168.2.140 "docker ps --filter name=weather-station; \
  docker exec weather-station python3 -c \"import sqlite3; \
  print(sqlite3.connect('/app/data/observations.db').execute('SELECT MAX(timestamp) FROM observations').fetchone())\""
```

If you ever need to rebuild it on the Pi (pulls latest code, keeps the data volume):

```bash
ssh kent-pi5@192.168.2.140
cd ~/weather-engine && git pull
docker build -t weather-station . \
  && docker rm -f weather-station \
  && docker run -d --name weather-station --restart=always \
       -p 8501:8501 -v ~/weather-engine/data:/app/data weather-station
```

---

If you're standing up a **new** host instead, pick one:

## Option A — Windows Scheduled Task (this laptop)

```powershell
# one-time, in an elevated PowerShell
powershell -ExecutionPolicy Bypass -File deploy\install_task.ps1
Start-ScheduledTask -TaskName WeatherEngineCollector
```

The task starts at logon and auto-restarts within a minute if it ever exits.

> ⚠️ **Sleep still pauses collection.** A closed/sleeping laptop stops polling. Either
> disable sleep on AC power:
> ```powershell
> powercfg /change standby-timeout-ac 0
> powercfg /change hibernate-timeout-ac 0
> ```
> or use Option B for genuine 24/7.

Check health:
```powershell
Get-ScheduledTaskInfo -TaskName WeatherEngineCollector   # LastRunTime, LastTaskResult
Get-Content logs\scheduler.log -Tail 20
```

## Option B — Docker on an always-on host (recommended for real trading)

A $5/mo VPS that never sleeps is the reliable answer.

```bash
docker build -t weather-engine .
docker run -d --restart=unless-stopped -p 8501:8501 -v weather_data:/app/data weather-engine
```

`--restart=unless-stopped` brings it back after crashes and host reboots. The named
volume persists both databases across container rebuilds.

## Verifying it's actually collecting

```powershell
py -c "import sqlite3; c=sqlite3.connect('data/observations.db'); print(c.execute('SELECT MAX(timestamp) FROM observations').fetchone())"
```

If the latest timestamp isn't within the last ~hour during the day, collection has
stalled — check `logs/scheduler.log` and `logs/observations.log`.
