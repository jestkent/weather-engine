import sqlite3
import json
import requests
import os
from datetime import datetime

# --- CONFIGURATION ---
# These lines find where your files are relative to this script
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'stations.json')
DB_PATH = os.path.join(BASE_DIR, 'data', 'observations.db')

def load_config():
    """Reads the list of stations to track."""
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_latest_observation(station_id, user_agent):
    """
    Fetches the current weather from NOAA API.
    """
    url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
    
    # NOAA strictly requires a User-Agent header
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/geo+json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        # If the server returns an error (like 404 or 500), this raises an exception
        response.raise_for_status() 
        
        return response.json()
    except Exception as e:
        print(f"❌ Error fetching {station_id}: {e}")
        return None

def save_observation(station_id, data):
    """
    Extracts temp and time, saves to database.
    """
    if not data:
        return

    try:
        properties = data.get('properties', {})
        
        # 1. Get Timestamp
        timestamp = properties.get('timestamp')
        
        # 2. Get Temperature (comes in Celsius, need Fahrenheit)
        temp_c_obj = properties.get('temperature', {})
        
        # Sometimes the sensor is down and returns null
        if temp_c_obj is None or temp_c_obj.get('value') is None:
            print(f"⚠️  No temperature data available for {station_id}")
            return

        temp_c = temp_c_obj.get('value')
        
        # Convert Celsius to Fahrenheit
        temp_f = (temp_c * 9/5) + 32
        
        # 3. Save to Database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # We use 'INSERT OR IGNORE' so we don't save duplicates if we run it twice
        cursor.execute('''
            INSERT OR IGNORE INTO observations (station_id, timestamp, temp_f, raw_json)
            VALUES (?, ?, ?, ?)
        ''', (station_id, timestamp, round(temp_f, 1), json.dumps(data)))
        
        # Check if we actually added a new row
        if cursor.rowcount > 0:
            print(f"✅ SAVED: {station_id} | {temp_f:.1f}°F | {timestamp}")
        else:
            print(f"ℹ️  SKIPPED: {station_id} (Already exists)")
            
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error saving {station_id}: {e}")

def run_collection():
    """Main function to loop through all stations."""
    config = load_config()
    user_agent = config['defaults']['user_agent']
    
    print(f"--- STARTING COLLECTION: {datetime.now().strftime('%H:%M:%S')} ---")
    
    for key, station in config['stations'].items():
        station_id = station['station_id']
        name = station['name']
        
        print(f"Fetching {name} ({station_id})...")
        
        # 1. Fetch
        raw_data = get_latest_observation(station_id, user_agent)
        
        # 2. Save
        save_observation(station_id, raw_data)
        
    print("---------------------------------------------")

if __name__ == "__main__":
    run_collection()