"""Running high/low + temperature velocity per station, from data/observations.db.

Velocity is a least-squares slope (F/hr) over a recent window rather than a two-point
difference. The old two-point method needed a reading within 45 min of exactly "1 hour
ago" and returned 0.0 whenever it couldn't find one -- which, with hourly data, was most
of the time. Now that live_observations.py stores the full observation history (often a
point every ~5 min), a regression over the last ~90 min is both available and far less
noisy than differencing two samples.
"""
from datetime import datetime, timedelta

from common import OBS_DB_PATH, load_config, local_day_start_utc, open_db

VELOCITY_WINDOW_MIN = 90  # look back this far for the slope fit


def get_todays_observations(station_id, tz_name):
    """All (timestamp, temp_f) for the station since its LOCAL midnight, oldest first."""
    conn = open_db(OBS_DB_PATH)
    try:
        rows = conn.execute("""
            SELECT timestamp, temp_f
            FROM observations
            WHERE station_id = ? AND timestamp >= ? AND temp_f IS NOT NULL
            ORDER BY timestamp ASC
        """, (station_id, local_day_start_utc(tz_name))).fetchall()
    finally:
        conn.close()
    return rows


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def calculate_velocity(observations, window_min=VELOCITY_WINDOW_MIN):
    """Least-squares slope of temp vs time (F/hr) over the last `window_min` minutes.

    Returns 0.0 if there aren't >=2 points in the window or time doesn't vary.
    """
    if len(observations) < 2:
        return 0.0

    last_time = _parse(observations[-1][0])
    cutoff = last_time - timedelta(minutes=window_min)
    pts = [(_parse(ts), t) for ts, t in observations if _parse(ts) >= cutoff]
    if len(pts) < 2:
        return 0.0

    # x in hours relative to the window's first point, y in F.
    t0 = pts[0][0]
    xs = [(t - t0).total_seconds() / 3600.0 for t, _ in pts]
    ys = [t for _, t in pts]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return slope


def analyze_station(station_id, name, tz_name):
    print(f"\nANALYZING: {name} ({station_id})")
    data = get_todays_observations(station_id, tz_name)
    if not data:
        print("   no data for today yet.")
        return

    temps = [row[1] for row in data]
    current_temp = temps[-1]
    running_high = max(temps)
    running_low = min(temps)
    velocity = calculate_velocity(data)
    projected_3hr = current_temp + (velocity * 3)

    print(f"   current temp:  {current_temp:.1f} F  ({len(data)} obs today)")
    print(f"   today's high:  {running_high:.1f} F")
    print(f"   today's low:   {running_low:.1f} F")

    if velocity > 0.5:
        pace = f"HEATING UP (+{velocity:.1f} F/hr)"
    elif velocity < -0.5:
        pace = f"COOLING DOWN ({velocity:.1f} F/hr)"
    else:
        pace = "STABLE"
    print(f"   pace:          {pace}")
    print(f"   3hr projection:{projected_3hr:.1f} F (linear)")

    if velocity > 2.0:
        print("   SIGNAL: SURGE (rapid heating)")
    elif velocity < -2.0:
        print("   SIGNAL: PLUNGE (rapid cooling)")
    else:
        print("   SIGNAL: normal")


def run_analysis():
    config = load_config()
    print("--- LIVE PACE MODEL ENGINE ---")
    for _, station in config["stations"].items():
        tz_name = station.get("timezone", "America/New_York")
        analyze_station(station["station_id"], station["name"], tz_name)
    print("\n---------------------------------")


if __name__ == "__main__":
    run_analysis()
