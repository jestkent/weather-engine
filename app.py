import streamlit as st
import pandas as pd
import sqlite3
import json
import os
from datetime import datetime
import pytz

# --- CONFIGURATION ---
st.set_page_config(page_title="NOAA Weather Intelligence", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'stations.json')
DB_PATH = os.path.join(BASE_DIR, 'data', 'observations.db')

@st.cache_data
def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_data(station_id, timezone_str):
    conn = sqlite3.connect(DB_PATH)
    
    # Load all data for this station
    query = f"SELECT timestamp, temp_f FROM observations WHERE station_id = '{station_id}'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return pd.DataFrame()

    # Convert strings to datetime objects
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Handle timezones (Assuming source is UTC)
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
    
    # Convert to target station timezone
    target_tz = pytz.timezone(timezone_str)
    df['local_time'] = df['timestamp'].dt.tz_convert(target_tz)

    # Filter for TODAY only (based on local time)
    now_local = datetime.now(target_tz)
    today_date = now_local.date()
    
    df = df[df['local_time'].dt.date == today_date]
    df = df.sort_values('local_time')
    
    return df, now_local # Return current time too

def main():
    st.title("🌤️ Weather Intelligence Engine")

    # Sidebar
    config = load_config()
    station_map = {v['name']: k for k, v in config['stations'].items()}
    selected_name = st.sidebar.selectbox("Select Station", list(station_map.keys()))
    
    # Get station details
    station_key = station_map[selected_name]
    station_data = config['stations'][station_key]
    station_id = station_data['station_id']
    tz_str = station_data['timezone']

    # Load Data & Current Time
    df, current_time = get_data(station_id, tz_str)

    # --- DISPLAY LOCAL TIME ---
    # Format: "Sunday, 12:45 AM"
    time_str = current_time.strftime("%A, %I:%M %p")
    st.markdown(f"### 🕒 Local Time: **{time_str}**")
    st.caption(f"Timezone: {tz_str}")

    if df.empty:
        st.warning(f"No data collected for **{current_time.strftime('%A')}** yet.")
        st.info("💡 Tip: It might be a new day! Run `py weather/live_observations.py` to get the first reading.")
        return

    # Metrics
    current_temp = df['temp_f'].iloc[-1]
    high = df['temp_f'].max()
    low = df['temp_f'].min()
    
    # Calculate Change (Last reading vs. 1 hour ago)
    delta = 0.0
    if len(df) >= 4:
        past_temp = df['temp_f'].iloc[-4]
        delta = current_temp - past_temp

    # Display Columns
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Temp", f"{current_temp:.1f}°F", f"{delta:+.1f}°F / hr")
    col2.metric("Today's High", f"{high:.1f}°F")
    col3.metric("Today's Low", f"{low:.1f}°F")
    col4.metric("Data Points", len(df))

    # Chart
    st.subheader(f"Temperature Trend")
    
    # Prepare chart data (Time on X, Temp on Y)
    chart_data = df.set_index('local_time')['temp_f']
    st.line_chart(chart_data, color="#ff4b4b")

if __name__ == "__main__":
    main()