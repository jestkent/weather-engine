import sqlite3
import os

# Define paths to our two databases
# We use os.path.join so it works on Windows, Mac, and Linux
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, "data")

obs_db_path = os.path.join(data_dir, "observations.db")
results_db_path = os.path.join(data_dir, "daily_results.db")

def create_observations_db():
    """Creates the table for live temperature readings."""
    conn = sqlite3.connect(obs_db_path)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        temp_f REAL NOT NULL,
        raw_json TEXT,
        UNIQUE(station_id, timestamp)
    )
    ''')
    
    # Create an index so searching is fast
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_station_time 
    ON observations (station_id, timestamp)
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ Created/Verified: {obs_db_path}")

def create_results_db():
    """Creates the table for final official daily results."""
    conn = sqlite3.connect(results_db_path)
    cursor = conn.cursor()
    
    # Create table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station_id TEXT NOT NULL,
        date TEXT NOT NULL,
        high_f REAL,
        low_f REAL,
        is_final INTEGER DEFAULT 0,
        UNIQUE(station_id, date)
    )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ Created/Verified: {results_db_path}")

if __name__ == "__main__":
    print("--- INITIALIZING DATABASES ---")
    
    # 1. Create the 'data' folder if it doesn't exist
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"📁 Created folder: {data_dir}")
        
    # 2. Create the databases
    create_observations_db()
    create_results_db()
    print("------------------------------")