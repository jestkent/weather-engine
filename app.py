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
DASHBOARD_TIMEZONE = 'America/New_York' 

st.set_page_config(page_title="Weather Engine AI", page_icon="🌤️", layout="wide")

# --- 1. LOAD CONFIGURATION (For Friendly Names) ---
def get_station_mapping():
    """Reads the JSON config to create a dictionary of friendly names."""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        
        mapping = {}
        # Loop through the config to match IDs with Names
        # Example: mapping['KSOW'] = "KSOW (SHOW_LOW_AZ)"
        for key, info in config.get("stations", {}).items():
            sid = info.get("station_id")
            if sid:
                mapping[sid] = f"{sid} ({key})"
        return mapping
    except Exception as e:
        print(f"⚠️ Could not load config names: {e}")
        return {}

# --- 2. GET AVAILABLE STATIONS FROM DB ---
def get_stations():
    try:
        conn = sqlite3.connect(DB_FILE)
        query = "SELECT DISTINCT station_id FROM observations"
        df = pd.read_sql(query, conn)
        conn.close()
        return df['station_id'].tolist()
    except:
        return []

# --- 3. GET HISTORICAL DATA ---
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
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['timestamp'] = df['timestamp'].dt.tz_convert(DASHBOARD_TIMEZONE)
    
    return df

# --- 4. GET FORECAST (Bulletproof) ---
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
        for p in periods[:24]:
            future_data.append({
                'timestamp': pd.to_datetime(p['startTime']),
                'temperature': p['temperature']
            })
        return pd.DataFrame(future_data)
        
    except Exception as e:
        print(f"Forecast Error: {e}")
        return pd.DataFrame()

# --- MAIN APP LAYOUT ---

# 1. Sidebar Control
available_stations = get_stations()
station_map = get_station_mapping()

if not available_stations:
    st.warning("Waiting for data collector... (Check if run_forever.py is running)")
    st.stop()

# This is the magic part: We use 'format_func' to show the friendly name
selected_station = st.sidebar.selectbox(
    "Select Station:", 
    available_stations,
    format_func=lambda x: station_map.get(x, x) # Shows "KSOW (SHOW_LOW_AZ)"
)

# 2. Header and Time
tz = pytz.timezone(DASHBOARD_TIMEZONE)
current_time = datetime.now(tz).strftime("%A, %B %d, %I:%M %p")

# Get friendly name for title too
friendly_title = station_map.get(selected_station, selected_station)

st.title(f"🌤️ {friendly_title}")
st.markdown(f"### 🕒 {current_time}")

# 3. Load Data
df = get_data(selected_station)
df_forecast = get_forecast(selected_station)

if df.empty:
    st.warning("No historical data yet.")
    st.stop()

# --- DATA PROCESSING ---
now = datetime.now(tz)
start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

df_yesterday = df[df['timestamp'] < start_of_today]
df_today = df[df['timestamp'] >= start_of_today]

# --- METRICS ---
curr_temp = df_today.iloc[-1]['temperature'] if not df_today.empty else 0
high_today = df_today['temperature'].max() if not df_today.empty else 0
low_today = df_today['temperature'].min() if not df_today.empty else 0
high_tmrw = df_forecast['temperature'].max() if not df_forecast.empty else "N/A"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Current Temp", f"{curr_temp}°F")
c2.metric("Today's High", f"{high_today}°F")
c3.metric("Today's Low", f"{low_today}°F")
c4.metric("Tomorrow High", f"{high_tmrw}°F")

# --- CHART ---
fig = go.Figure()

if not df_yesterday.empty:
    fig.add_trace(go.Scatter(x=df_yesterday['timestamp'], y=df_yesterday['temperature'],
                             mode='lines', name='Yesterday', line=dict(color='grey', width=2)))

if not df_today.empty:
    fig.add_trace(go.Scatter(x=df_today['timestamp'], y=df_today['temperature'],
                             mode='lines', name='Today', line=dict(color='blue', width=4)))

if not df_forecast.empty:
    fig.add_trace(go.Scatter(x=df_forecast['timestamp'], y=df_forecast['temperature'],
                             mode='lines', name='Forecast (24h)', line=dict(color='orange', width=3, dash='dash')))

fig.update_layout(
    title=f"72-Hour Timeline: {friendly_title}",
    xaxis=dict(title="Time", tickformat="%I:%M %p"),
    yaxis=dict(title="Temp (°F)"),
    hovermode="x unified"
)

st.plotly_chart(fig)