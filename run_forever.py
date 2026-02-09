import time
import subprocess
import sys
import sqlite3
import os
from datetime import datetime

# --- CONFIGURATION ---
DB_FILE = "data/observations.db"
COLLECTOR_SCRIPT = "weather/live_observations.py"
INTERVAL_SECONDS = 900  # 15 minutes

# --- 1. SELF-HEALING DATABASE FUNCTION ---
def init_db():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛠️ Checking database health...")
    
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # This creates the table with the CORRECT column name (raw_json)
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
    print("✅ Database table is ready.")

# --- 2. MAIN LOOP ---
print("--- 🔄 STARTING 24/7 WEATHER COLLECTOR ---")

# Run the setup ONCE before the loop starts
init_db()

try:
    while True:
        now = datetime.now().strftime("%I:%M %p")
        print(f"\n[{now}] Waking up to collect data...")
        
        result = subprocess.run([sys.executable, COLLECTOR_SCRIPT])
        
        if result.returncode == 0:
            print("✅ Collection successful.")
        else:
            print("❌ Collection script crashed!")
            
        print(f"💤 Sleeping for {INTERVAL_SECONDS/60} minutes...")
        time.sleep(INTERVAL_SECONDS)

except KeyboardInterrupt:
    print("\n🛑 Stopping collector. Goodbye!")