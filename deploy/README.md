# Keeping the collector running 24/7

The engine's edge depends on **continuous** collection through the afternoon — a gap
during peak heating means the running high reads low. The collector itself is robust
(retries, self-healing backfill, per-cycle error isolation), but *something* has to keep
the process alive. Pick one:

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
