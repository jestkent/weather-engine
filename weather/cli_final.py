import requests
import re
import sqlite3
import json
import os
from datetime import datetime

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'stations.json')
DB_PATH = os.path.join(BASE_DIR, 'data', 'daily_results.db')

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def fetch_cli_html(wfo, cli_code, user_agent):
    """
    Fetches the HTML page using the specific CLI code (e.g., LAX, NYC).
    URL: https://forecast.weather.gov/product.php?site=LOX&product=CLI&issuedby=LAX
    """
    url = f"https://forecast.weather.gov/product.php?site={wfo}&product=CLI&issuedby={cli_code}"
    
    headers = {"User-Agent": user_agent}
    
    try:
        print(f"   -> Fetching: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # EXTRACT THE TEXT INSIDE THE <pre> TAG
        # The report is always wrapped in <pre> tags on this page.
        html_content = response.text
        match = re.search(r'<pre[^>]*>(.*?)</pre>', html_content, re.DOTALL)
        
        if match:
            return match.group(1) # Return just the text inside
        else:
            print("   -> ⚠️ Loaded page, but could not find <pre> tag.")
            return None

    except Exception as e:
        print(f"❌ Error fetching {cli_code}: {e}")
        return None

def parse_cli_text(text):
    """
    Scans the text report for Max/Min temperatures.
    """
    if not text:
        return None, None

    lines = text.split('\n')
    max_temp = None
    min_temp = None
    
    for line in lines:
        clean_line = line.upper().strip()
        
        if "FORECAST" in clean_line: continue

        # LOOK FOR HIGH
        # Matches "MAXIMUM... 82", "MAX TEMP... 82"
        if "MAX" in clean_line and ("TEMP" in clean_line or "YESTERDAY" in clean_line):
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", clean_line)
            if numbers and max_temp is None:
                try:
                    val = float(numbers[0])
                    if -40 < val < 135: max_temp = val
                except: pass

        # LOOK FOR LOW
        if "MIN" in clean_line and ("TEMP" in clean_line or "YESTERDAY" in clean_line):
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", clean_line)
            if numbers and min_temp is None:
                try:
                    val = float(numbers[0])
                    if -40 < val < 135: min_temp = val
                except: pass
                    
        if max_temp is not None and min_temp is not None:
            break
            
    return max_temp, min_temp

def save_result(station_id, date_str, high, low):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO daily_results (station_id, date, high_f, low_f, is_final)
            VALUES (?, ?, ?, ?, 1)
        ''', (station_id, date_str, high, low))
        print(f"✅ LOCKED: {station_id} | High: {high}°F | Low: {low}°F | Date: {date_str}")
        conn.commit()
    except Exception as e:
        print(f"❌ Database Error: {e}")
    finally:
        conn.close()

def run_cli_check():
    config = load_config()
    user_agent = config['defaults']['user_agent']
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    print(f"--- CHECKING OFFICIAL RESULTS (USER URL METHOD) ---")
    
    for key, station in config['stations'].items():
        wfo = station['wfo']
        cli_code = station['cli_code'] # Using our new config field!
        sid = station['station_id']
        
        # 1. Fetch
        raw_text = fetch_cli_html(wfo, cli_code, user_agent)
        
        # 2. Parse
        if raw_text:
            high, low = parse_cli_text(raw_text)
            
            if high is not None and low is not None:
                save_result(sid, today_str, high, low)
            else:
                print(f"⚠️  Found report for {cli_code} but could not parse temps.")
        
    print("---------------------------------------------")

if __name__ == "__main__":
    run_cli_check()