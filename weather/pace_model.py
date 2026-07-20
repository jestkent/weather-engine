import sqlite3
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Windows consoles default to cp1252 and crash on the emoji in our logs; force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'stations.json')
DB_PATH = os.path.join(BASE_DIR, 'data', 'observations.db')

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def local_day_start_utc(tz_name):
    """UTC ISO string for the most recent LOCAL midnight in the given timezone.

    Daily high/low is a local-day concept. UTC midnight is 7-8pm local for US
    stations, so filtering on UTC midnight mixes two calendar days. NWS timestamps
    are stored as UTC (`...+00:00`), so we return a matching UTC string to compare.
    """
    now_local = datetime.now(ZoneInfo(tz_name))
    midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def get_todays_observations(station_id, tz_name):
    """Fetches all temperature readings for the station since LOCAL midnight."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    today_start = local_day_start_utc(tz_name)

    cursor.execute('''
        SELECT timestamp, temp_f
        FROM observations
        WHERE station_id = ? AND timestamp >= ? AND temp_f IS NOT NULL
        ORDER BY timestamp ASC
    ''', (station_id, today_start))

    rows = cursor.fetchall()
    conn.close()
    return rows

def calculate_velocity(observations):
    """
    Calculates how fast the temperature is changing (Degrees per Hour).
    Compares the last reading to the reading ~60 minutes ago.
    """
    if len(observations) < 2:
        return 0.0

    # Get latest reading
    last_time_str, last_temp = observations[-1]
    last_time = datetime.fromisoformat(last_time_str.replace('Z', '+00:00'))

    # Look for a reading 1 hour ago (or as close as possible)
    one_hour_ago = last_time - timedelta(hours=1)
    
    past_temp = None
    closest_time_diff = timedelta(hours=24) # Start with a big gap

    for time_str, temp in observations:
        curr_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        
        # We want the reading closest to "1 hour ago"
        time_diff = abs(curr_time - one_hour_ago)
        
        if time_diff < closest_time_diff:
            closest_time_diff = time_diff
            past_temp = temp

    # If we found a comparison point within reason (e.g., +/- 30 mins of 1 hour ago)
    if past_temp is not None and closest_time_diff < timedelta(minutes=45):
        change = last_temp - past_temp
        return change # e.g., +2.5 or -1.0
    
    return 0.0

def analyze_station(station_id, name, tz_name):
    print(f"\n📊 ANALYZING: {name} ({station_id})")

    data = get_todays_observations(station_id, tz_name)
    
    if not data:
        print("   ⚠️  No data found for today yet.")
        return

    # 1. Basic Stats
    temps = [row[1] for row in data]
    current_temp = temps[-1]
    running_high = max(temps)
    running_low = min(temps)
    
    # 2. Calculate Pace (Velocity)
    velocity = calculate_velocity(data)
    
    # 3. Simple Projection (Where will we be in 3 hours?)
    # This is a basic "Linear Projection"
    projected_3hr = current_temp + (velocity * 3)
    
    # --- OUTPUT DASHBOARD ---
    print(f"   🌡️  Current Temp:   {current_temp}°F")
    print(f"   📈  Today's High:   {running_high}°F")
    print(f"   📉  Today's Low:    {running_low}°F")
    
    # Formatting Velocity
    if velocity > 0.5:
        pace_str = f"🔥 HEATING UP (+{velocity:.1f}°F/hr)"
    elif velocity < -0.5:
        pace_str = f"❄️ COOLING DOWN ({velocity:.1f}°F/hr)"
    else:
        pace_str = "➡️  STABLE"
        
    print(f"   🚀  Pace Signal:    {pace_str}")
    
    # Formatting Signal
    if velocity > 2.0:
        print("   🚨  SIGNAL: SURGE DETECTED (Rapid Heating)")
    elif velocity < -2.0:
        print("   🚨  SIGNAL: PLUNGE DETECTED (Rapid Cooling)")
    else:
        print("   ✅  SIGNAL: NORMAL")

def run_analysis():
    config = load_config()
    print("--- 🧠 LIVE PACE MODEL ENGINE ---")
    
    for key, station in config['stations'].items():
        tz_name = station.get('timezone', 'America/New_York')
        analyze_station(station['station_id'], station['name'], tz_name)
        
    print("\n---------------------------------")

if __name__ == "__main__":
    run_analysis()