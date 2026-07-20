import requests
import sqlite3
import json
from datetime import datetime
import os
import sys
import time

# Windows consoles default to cp1252 and crash on the emoji in our logs; force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- CONFIGURATION ---
DB_FILE = "data/observations.db"
CONFIG_FILE = "config/stations.json"

# 🚨 THE FIX: A polite ID card for the API (NWS returns 403 without a User-Agent)
HEADERS = {
    "User-Agent": "(student-weather-station-v1.0, contact@github.com)"
}

# Reuse one TCP connection across all station requests (faster, kinder to the API)
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def get_stations():
    """Reads the JSON config file."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return data["stations"]
    except FileNotFoundError:
        print(f"❌ Error: Config file {CONFIG_FILE} not found!")
        return {}

def init_db():
    """Ensures the DB exists and enforces (station_id, timestamp) uniqueness.

    NWS 'latest observation' only updates ~hourly, but we poll every 15 min, so the
    same reading would otherwise be inserted 3-4x. We dedup legacy rows once, then a
    UNIQUE index + INSERT OR IGNORE keeps it clean going forward.
    """
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id TEXT,
            timestamp TEXT,
            temp_f REAL,
            humidity REAL,
            wind_speed REAL,
            description TEXT,
            raw_json TEXT
        )
    ''')
    # Migrate: drop any pre-existing duplicate readings (keep the earliest id)
    c.execute('''
        DELETE FROM observations
        WHERE id NOT IN (
            SELECT MIN(id) FROM observations GROUP BY station_id, timestamp
        )
    ''')
    # Enforce uniqueness from now on
    c.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_obs_unique
        ON observations (station_id, timestamp)
    ''')
    conn.commit()
    conn.close()

def fetch_weather(station_id):
    """Gets data from NWS API with the new Headers."""
    url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
    
    try:
        # Uses the shared session (User-Agent already set) so NWS doesn't 403 us
        response = SESSION.get(url, timeout=10)

        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ API Error for {station_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Connection Error for {station_id}: {e}")
        return None

def save_observation(station_id, data):
    """Saves the data to SQLite."""
    if not data: return

    try:
        props = data.get('properties', {})
        
        # Extract fields. NWS gives temperature in Celsius.
        # NOTE: must be `is not None`, NOT `if temp_f:` — a real 0.0 C reading (= 32 F,
        # common in winter at KNYC/KORD/KDEN) is falsy and would be stored as 0 F.
        temp_f = props.get('temperature', {}).get('value')
        if temp_f is not None:
            temp_f = (temp_f * 9 / 5) + 32  # Convert C to F
        
        humidity = props.get('relativeHumidity', {}).get('value')
        wind = props.get('windSpeed', {}).get('value')
        desc = props.get('textDescription', 'Unknown')
        timestamp = props.get('timestamp', datetime.now().isoformat())
        raw_json = json.dumps(data)

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT OR IGNORE INTO observations
            (station_id, timestamp, temp_f, humidity, wind_speed, description, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (station_id, timestamp, temp_f, humidity, wind, desc, raw_json))
        
        conn.commit()
        inserted = c.rowcount  # 0 if this (station, timestamp) was already stored
        conn.close()
        temp_display = f"{temp_f:.1f}°F" if temp_f is not None else "N/A"
        if inserted:
            print(f"✅ SAVED: {station_id} | {temp_display}")
        else:
            print(f"➡️  UNCHANGED: {station_id} | {temp_display} (obs not updated yet)")
        
    except Exception as e:
        print(f"❌ Error saving {station_id}: {e}")

# --- MAIN LOOP ---
if __name__ == "__main__":
    print(f"--- STARTING COLLECTION: {datetime.now().strftime('%H:%M:%S')} ---")
    init_db()
    stations = get_stations()
    
    for name, info in stations.items():
        sid = info["station_id"]
        print(f"Fetching {name} ({sid})...")
        weather_data = fetch_weather(sid)
        save_observation(sid, weather_data)
        time.sleep(1) # Be polite, wait 1 second between requests
        
    print("---------------------------------------------")