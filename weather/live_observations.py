"""Collect NWS temperature observations into data/observations.db.

Why full history, not just "latest": the market edge is the running daily HIGH.
The old collector polled /observations/latest (a single instant) and took max() over
whatever it happened to catch, so ANY downtime, or NWS simply skipping the peak minute,
made the running high read low. Instead we pull every observation since the station's
LOCAL midnight (/observations?start=...) each cycle. INSERT OR IGNORE dedups, so this is
idempotent AND self-healing: a cycle that runs after an outage backfills the gap and
recovers the true peak.
"""
import json
import time

import requests

from common import (
    OBS_DB_PATH, get_logger, get_user_agent, get_with_retry, init_observations_db,
    load_config, local_day_start_utc, open_db,
)

log = get_logger("observations")


def build_session(user_agent):
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    return s


def fetch_todays_observations(session, station_id, tz_name):
    """All observations for the station since its LOCAL midnight (list of feature props)."""
    start = local_day_start_utc(tz_name)
    url = f"https://api.weather.gov/stations/{station_id}/observations"
    resp = get_with_retry(session, url, params={"start": start}, timeout=15, logger=log)
    if resp is None:
        return []
    if resp.status_code != 200:
        log.warning("API error for %s: %s", station_id, resp.status_code)
        return []
    try:
        features = resp.json().get("features", [])
    except ValueError:
        log.warning("Non-JSON response for %s", station_id)
        return []
    return [f.get("properties", {}) for f in features]


def to_row(station_id, props):
    """Map one NWS observation to our column tuple, or None if it has no timestamp."""
    timestamp = props.get("timestamp")
    if not timestamp:
        return None

    # NWS temperature is Celsius. Guard with `is not None`, NOT truthiness: a real
    # 0.0 C reading (= 32 F, common winter at KNYC/KORD/KDEN) is falsy.
    temp_c = props.get("temperature", {}).get("value")
    temp_f = (temp_c * 9 / 5) + 32 if temp_c is not None else None

    humidity = props.get("relativeHumidity", {}).get("value")
    wind = props.get("windSpeed", {}).get("value")
    desc = props.get("textDescription", "Unknown")
    return (station_id, timestamp, temp_f, humidity, wind, desc, json.dumps(props))


def save_observations(conn, rows):
    """Bulk INSERT OR IGNORE; returns count of NEW rows actually stored."""
    rows = [r for r in rows if r is not None]
    if not rows:
        return 0
    c = conn.cursor()
    before = conn.total_changes
    c.executemany("""
        INSERT OR IGNORE INTO observations
        (station_id, timestamp, temp_f, humidity, wind_speed, description, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return conn.total_changes - before


def collect():
    config = load_config()
    session = build_session(get_user_agent(config))
    conn = open_db(OBS_DB_PATH)
    init_observations_db(conn)

    log.info("--- collection start ---")
    total_new = 0
    for name, info in config["stations"].items():
        sid = info["station_id"]
        tz_name = info.get("timezone", "America/New_York")
        props_list = fetch_todays_observations(session, sid, tz_name)
        rows = [to_row(sid, p) for p in props_list]
        new = save_observations(conn, rows)
        total_new += new

        # Report the running high so a glance at the log tells you the day's peak.
        temps = [r[2] for r in rows if r and r[2] is not None]
        hi = f"{max(temps):.1f}F" if temps else "n/a"
        log.info("%-6s %-22s seen=%2d new=%2d running_high=%s",
                 sid, name, len(props_list), new, hi)
        time.sleep(1)  # be polite between stations

    conn.close()
    log.info("--- collection done: %d new rows ---", total_new)
    return total_new


if __name__ == "__main__":
    collect()
