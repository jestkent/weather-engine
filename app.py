import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta
import pytz

# --- CONFIGURATION ---
DB_FILE = "data/observations.db"
CONFIG_FILE = "config/stations.json"
USER_AGENT = "(weather-engine-v5, contact@github.com)"

# --- TIMEZONE MAP ---
STATION_TIMEZONES = {
    'KNYC': 'America/New_York',
    'KLAX': 'America/Los_Angeles',
    'KORD': 'America/Chicago',
    'KSOW': 'America/Phoenix',
    'KPHX': 'America/Phoenix',
    'KMIA': 'America/New_York',
    'KSFO': 'America/Los_Angeles',
    'KLAS': 'America/Los_Angeles',
    'KDEN': 'America/Denver',
    'KSEA': 'America/Los_Angeles'
}

st.set_page_config(page_title="Weather Engine AI", page_icon="🌤️", layout="wide")

# --- 1. LOAD CONFIGURATION ---
def get_station_mapping():
    """Reads the JSON config to create a dictionary of friendly names."""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        
        mapping = {}
        for key, info in config.get("stations", {}).items():
            sid = info.get("station_id")
            if sid:
                mapping[sid] = f"{sid} ({key})"
        return mapping
    except Exception as e:
        # Fallback if file missing
        return {}

# --- 2. GET STATIONS ---
def get_stations():
    try:
        conn = sqlite3.connect(DB_FILE)
        query = "SELECT DISTINCT station_id FROM observations"
        df = pd.read_sql(query, conn)
        conn.close()
        return df['station_id'].tolist()
    except:
        return []

# --- 3. GET DATA (FIXED TIMEZONES) ---
def get_data(station_code):
    conn = sqlite3.connect(DB_FILE)
    query = """
        SELECT timestamp, temp_f as temperature 
        FROM observations 
        WHERE station_id = ? 
        AND timestamp >= datetime('now', '-3 days')
        ORDER BY timestamp ASC
    """
    df = pd.read_sql(query, conn, params=(station_code,))
    conn.close()
    
    if not df.empty:
        # 1. Convert string to datetime objects
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 2. Look up the CORRECT timezone for this specific station
        target_tz = STATION_TIMEZONES.get(station_code, 'America/New_York')
        
        # 3. Ensure we start from UTC, then convert to Target
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        
        df['timestamp'] = df['timestamp'].dt.tz_convert(target_tz)
    
    return df

# --- 4. GET FORECAST ---
def get_forecast(station_id):
    headers = {"User-Agent": USER_AGENT}
    try:
        # Step 1: Get Lat/Lon
        url1 = f"https://api.weather.gov/stations/{station_id}"
        r1 = requests.get(url1, headers=headers)
        if r1.status_code != 200: return pd.DataFrame()
        
        coords = r1.json()['geometry']['coordinates']
        lon, lat = coords[0], coords[1]
        
        # Step 2: Get Gridpoint
        url2 = f"https://api.weather.gov/points/{lat},{lon}"
        r2 = requests.get(url2, headers=headers)
        if r2.status_code != 200: return pd.DataFrame()
        
        forecast_url = r2.json()['properties']['forecastHourly']
        
        # Step 3: Get Data
        r3 = requests.get(forecast_url, headers=headers)
        if r3.status_code != 200: return pd.DataFrame()
            
        periods = r3.json()['properties']['periods']
        future_data = []
        
        # Get the station's timezone to match the chart
        target_tz = STATION_TIMEZONES.get(station_id, 'America/New_York')

        for p in periods[:24]:
            # Forecast comes with timezone info, we just align it
            dt = pd.to_datetime(p['startTime'])
            dt = dt.tz_convert(target_tz)
            
            future_data.append({
                'timestamp': dt,
                'temperature': p['temperature']
            })
        return pd.DataFrame(future_data)
        
    except Exception as e:
        print(f"Forecast Error: {e}")
        return pd.DataFrame()

# --- MAIN APP LAYOUT ---

# Sidebar
available_stations = get_stations()
station_map = get_station_mapping()

if not available_stations:
    st.warning("Waiting for data... (Is run_forever.py running?)")
    st.stop()

selected_station = st.sidebar.selectbox(
    "Select Station:", 
    available_stations,
    format_func=lambda x: station_map.get(x, x)
)

# Load Data
df = get_data(selected_station)
df_forecast = get_forecast(selected_station)

if df.empty:
    st.warning("No historical data yet.")
    st.stop()

# Get Current Time in Station's Zone
station_tz = STATION_TIMEZONES.get(selected_station, 'America/New_York')
tz_obj = pytz.timezone(station_tz)
current_time = datetime.now(tz_obj).strftime("%A, %B %d, %I:%M %p")

friendly_title = station_map.get(selected_station, selected_station)

st.title(f"🌤️ {friendly_title}")
st.markdown(f"### 🕒 Local Time: {current_time} ({station_tz})")

# Split Data (Today vs Yesterday)
# We use the station's local midnight to split
now_local = datetime.now(tz_obj)
start_of_today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

df_yesterday = df[df['timestamp'] < start_of_today]
df_today = df[df['timestamp'] >= start_of_today]

# Metrics
curr_temp = df_today.iloc[-1]['temperature'] if not df_today.empty else 0
high_today = df_today['temperature'].max() if not df_today.empty else 0
low_today = df_today['temperature'].min() if not df_today.empty else 0
high_tmrw = df_forecast['temperature'].max() if not df_forecast.empty else "N/A"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Current Temp", f"{curr_temp}°F")
c2.metric("Today's High", f"{high_today}°F")
c3.metric("Today's Low", f"{low_today}°F")
c4.metric("Tomorrow High", f"{high_tmrw}°F")

# Chart
fig = go.Figure()

if not df_yesterday.empty:
    fig.add_trace(go.Scatter(
        x=df_yesterday['timestamp'], 
        y=df_yesterday['temperature'],
        mode='lines', 
        name='Yesterday', 
        line=dict(color='grey', width=2)
    ))

if not df_today.empty:
    fig.add_trace(go.Scatter(
        x=df_today['timestamp'], 
        y=df_today['temperature'],
        mode='lines', 
        name='Today', 
        line=dict(color='blue', width=4)
    ))

if not df_forecast.empty:
    fig.add_trace(go.Scatter(
        x=df_forecast['timestamp'], 
        y=df_forecast['temperature'],
        mode='lines', 
        name='Forecast', 
        line=dict(color='orange', width=3, dash='dash')
    ))

fig.update_layout(
    title=f"72-Hour Timeline ({station_tz})",
    xaxis=dict(title="Local Time", tickformat="%I:%M %p"),
    yaxis=dict(title="Temp (°F)"),
    hovermode="x unified"
)

st.plotly_chart(fig, width="stretch") # Using the safe modern fix!