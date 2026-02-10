import requests
import sqlite3
import json
from datetime import datetime
import os
import time

# --- CONFIGURATION ---
DB_FILE = "data/observations.db"
CONFIG_FILE = "config/stations.json"

# 🚨 THE FIX: A polite ID card for the API
HEADERS = {
    "User-Agent": "(student-weather-station-v1.0, contact@github.com)"
}

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
    """Ensures the DB exists (Just in case)."""
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
    conn.commit()
    conn.close()

def fetch_weather(station_id):
    """Gets data from NWS API with the new Headers."""
    url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
    
    try:
        # 🚨 THE FIX IS HERE: We pass 'headers=HEADERS'
        response = requests.get(url, headers=HEADERS, timeout=10)
        
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
        
        # Extract fields
        temp_f = props.get('temperature', {}).get('value')
        if temp_f: temp_f = (temp_f * 9/5) + 32  # Convert C to F
        
        humidity = props.get('relativeHumidity', {}).get('value')
        wind = props.get('windSpeed', {}).get('value')
        desc = props.get('textDescription', 'Unknown')
        timestamp = props.get('timestamp', datetime.now().isoformat())
        raw_json = json.dumps(data)

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO observations 
            (station_id, timestamp, temp_f, humidity, wind_speed, description, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (station_id, timestamp, temp_f, humidity, wind, desc, raw_json))
        
        conn.commit()
        conn.close()
        print(f"✅ SAVED: {station_id} | {temp_f:.1f}°F")
        
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