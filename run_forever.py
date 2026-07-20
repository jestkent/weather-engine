import time
import subprocess
import sys
import sqlite3
import os
from datetime import datetime

# Windows consoles default to cp1252 and crash on the emoji in our logs; force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- CONFIGURATION ---
DB_FILE = "data/observations.db"
COLLECTOR_SCRIPT = "weather/live_observations.py"
CLI_SCRIPT = "weather/cli_final.py"
INTERVAL_SECONDS = 900          # 15 minutes between observation polls
CLI_EVERY_N_CYCLES = 4          # run the official CLI scrape ~hourly (4 * 15 min)


# --- 1. SELF-HEALING DATABASE FUNCTION ---
def init_db():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛠️ Checking database health...")

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
    # Dedup legacy rows, then enforce (station_id, timestamp) uniqueness (see CLAUDE.md)
    c.execute('''
        DELETE FROM observations
        WHERE id NOT IN (
            SELECT MIN(id) FROM observations GROUP BY station_id, timestamp
        )
    ''')
    c.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_obs_unique
        ON observations (station_id, timestamp)
    ''')
    conn.commit()
    conn.close()
    print("✅ Database table is ready.")


def run_script(script):
    """Runs a collector script as a subprocess, reporting crashes without dying."""
    try:
        result = subprocess.run([sys.executable, script])
        if result.returncode == 0:
            print(f"✅ {script} finished.")
        else:
            print(f"❌ {script} exited with code {result.returncode}!")
    except Exception as e:
        print(f"❌ Failed to launch {script}: {e}")


# --- 2. MAIN LOOP ---
print("--- 🔄 STARTING 24/7 WEATHER COLLECTOR ---")

# Run the setup ONCE before the loop starts
init_db()

cycle = 0
try:
    while True:
        now = datetime.now().strftime("%I:%M %p")
        print(f"\n[{now}] Waking up to collect data...")

        # Live observations every cycle
        run_script(COLLECTOR_SCRIPT)

        # Official daily high/low (the market resolution source) ~hourly
        if cycle % CLI_EVERY_N_CYCLES == 0:
            print(f"[{now}] 📰 Fetching official CLI daily results...")
            run_script(CLI_SCRIPT)

        cycle += 1
        print(f"💤 Sleeping for {INTERVAL_SECONDS / 60:.0f} minutes...")
        time.sleep(INTERVAL_SECONDS)

except KeyboardInterrupt:
    print("\n🛑 Stopping collector. Goodbye!")
