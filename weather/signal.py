"""
Polymarket weather trade-signal tool.

For each station it combines what we already know (live observations so far *today*,
local time) with what NWS expects for the rest of the day, and reports the number that
markets actually resolve on: the **projected daily HIGH**.

    projected_high = max(running_high_so_far, forecast_high_for_remaining_hours)

Optionally pass thresholds to see the lean vs a market line:

    py weather/signal.py                 # all stations, no thresholds
    py weather/signal.py KNYC=75 KLAX=82 # show margin vs "high above X" markets

This is decision support, not an oracle. The official result is the NWS CLI report
(weather/cli_final.py) — this tool tells you where the day is heading before that posts.
"""
import sys
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

# Windows consoles default to cp1252 and crash on the emoji in our logs; force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Same-dir imports (run as `py weather/signal.py`)
from pace_model import get_todays_observations, calculate_velocity

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'stations.json')

SESSION = requests.Session()


def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)


def resolve_forecast_url(station_id, user_agent):
    """station -> lat/lon -> gridpoint -> hourly forecast URL (static per station)."""
    headers = {"User-Agent": user_agent}
    r1 = SESSION.get(f"https://api.weather.gov/stations/{station_id}", headers=headers, timeout=10)
    if r1.status_code != 200:
        return None
    lon, lat = r1.json()['geometry']['coordinates']
    r2 = SESSION.get(f"https://api.weather.gov/points/{lat},{lon}", headers=headers, timeout=10)
    if r2.status_code != 200:
        return None
    return r2.json()['properties']['forecastHourly']


def get_forecast_highs(station_id, tz_name, user_agent):
    """Returns (today_remaining_high, tomorrow_high) in F from the NWS hourly forecast.

    today_remaining_high = hottest forecast hour still ahead of us *today* (local day).
    Returns (None, None) on any failure.
    """
    try:
        url = resolve_forecast_url(station_id, user_agent)
        if not url:
            return None, None
        r = SESSION.get(url, headers={"User-Agent": user_agent}, timeout=10)
        if r.status_code != 200:
            return None, None

        tz = ZoneInfo(tz_name)
        now_local = datetime.now(tz)
        today = now_local.date()

        remaining_today = []
        tomorrow = []
        for p in r.json()['properties']['periods']:
            start = datetime.fromisoformat(p['startTime']).astimezone(tz)
            temp = p['temperature']  # NWS hourly forecast temps are already in F
            if start.date() == today and start >= now_local:
                remaining_today.append(temp)
            elif (start.date() - today).days == 1:
                tomorrow.append(temp)

        return (max(remaining_today) if remaining_today else None,
                max(tomorrow) if tomorrow else None)
    except Exception as e:
        print(f"   forecast error for {station_id}: {e}")
        return None, None


def analyze(station, thresholds, user_agent):
    sid = station['station_id']
    name = station['name']
    tz_name = station.get('timezone', 'America/New_York')

    obs = get_todays_observations(sid, tz_name)
    now_local = datetime.now(ZoneInfo(tz_name)).strftime("%I:%M %p")

    if not obs:
        print(f"\n📍 {sid:5} {name}")
        print("   ⚠️  no observations yet today (is run_forever.py running?)")
        return

    temps = [t for _, t in obs]
    current = temps[-1]
    running_high = max(temps)
    running_low = min(temps)
    velocity = calculate_velocity(obs)

    fc_remaining_high, fc_tomorrow_high = get_forecast_highs(sid, tz_name, user_agent)

    # The projected daily high = best of what already happened and what's still coming
    projected_high = running_high
    if fc_remaining_high is not None:
        projected_high = max(running_high, fc_remaining_high)

    # Is the high probably already locked in for the day?
    high_in = (fc_remaining_high is not None and fc_remaining_high <= running_high)

    print(f"\n📍 {sid:5} {name}   (local {now_local})")
    print(f"   current {current:.0f}°F  |  today so far  H {running_high:.0f}  L {running_low:.0f}"
          f"  |  pace {velocity:+.1f}°/hr")
    fc_txt = f"{fc_remaining_high:.0f}°F" if fc_remaining_high is not None else "n/a"
    print(f"   forecast remaining high {fc_txt}  ->  PROJECTED DAY HIGH {projected_high:.0f}°F"
          f"{'  (high likely already in)' if high_in else ''}")
    if fc_tomorrow_high is not None:
        print(f"   tomorrow forecast high {fc_tomorrow_high:.0f}°F")

    # Market lean vs a threshold, if given
    thr = thresholds.get(sid)
    if thr is not None:
        margin = projected_high - thr
        if margin >= 3:
            lean = f"🟢 LEAN YES (above {thr:.0f})"
        elif margin <= -3:
            lean = f"🔴 LEAN NO (below {thr:.0f})"
        else:
            lean = f"🟡 TOSS-UP (near {thr:.0f})"
        print(f"   vs line {thr:.0f}°F: projected margin {margin:+.0f}°  ->  {lean}")


def parse_thresholds(args):
    """Parses CLI args like KNYC=75 into {'KNYC': 75.0}."""
    out = {}
    for a in args:
        if '=' in a:
            k, v = a.split('=', 1)
            try:
                out[k.strip().upper()] = float(v)
            except ValueError:
                print(f"   (ignoring bad threshold: {a})")
    return out


def main():
    config = load_config()
    user_agent = config['defaults']['user_agent']
    thresholds = parse_thresholds(sys.argv[1:])

    print("--- 🎯 POLYMARKET WEATHER SIGNAL ---")
    for _, station in config['stations'].items():
        analyze(station, thresholds, user_agent)
    print("\n------------------------------------")


if __name__ == "__main__":
    main()
