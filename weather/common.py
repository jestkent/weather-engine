"""Shared helpers for the Weather Engine collectors.

Centralizes the things every script used to re-implement (config load, DB init,
HTTP with a User-Agent) and adds the reliability pieces a 24/7 collector needs:
WAL-mode SQLite (so the Streamlit dashboard can read while we write), HTTP retry
with backoff, and rotating file logging.

Logs are plain ASCII on purpose: the old scripts each had to monkeypatch
`sys.stdout.reconfigure(encoding="utf-8")` because emoji crash the Windows cp1252
console. A file logger with explicit utf-8 encoding + ASCII messages sidesteps that
whole class of problem.
"""
import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "stations.json")
OBS_DB_PATH = os.path.join(BASE_DIR, "data", "observations.db")
RESULTS_DB_PATH = os.path.join(BASE_DIR, "data", "daily_results.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# NWS returns 403 without a User-Agent. We read the real one from config, but keep a
# sane fallback so a partial config never silently gets us blocked.
DEFAULT_USER_AGENT = "(weather-engine, contact@example.com)"


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def get_user_agent(config=None):
    config = config or load_config()
    return config.get("defaults", {}).get("user_agent") or DEFAULT_USER_AGENT


def get_logger(name):
    """Logger that writes to logs/<name>.log (rotating) and to stdout.

    Idempotent: repeated calls with the same name won't stack duplicate handlers.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    os.makedirs(LOG_DIR, exist_ok=True)
    fh = RotatingFileHandler(os.path.join(LOG_DIR, f"{name}.log"),
                             maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def open_db(path):
    """SQLite connection tuned for a writer that shares the file with dashboard readers.

    WAL lets readers and the writer proceed concurrently instead of hitting
    'database is locked'; busy_timeout makes any remaining contention wait rather
    than fail immediately.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_observations_db(conn):
    """Create the observations table + uniqueness guard (single source of truth)."""
    c = conn.cursor()
    c.execute("""
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
    """)
    # Drop any legacy duplicate readings (keep earliest id), then enforce uniqueness.
    c.execute("""
        DELETE FROM observations
        WHERE id NOT IN (SELECT MIN(id) FROM observations GROUP BY station_id, timestamp)
    """)
    c.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_obs_unique
        ON observations (station_id, timestamp)
    """)
    conn.commit()


def init_results_db(conn):
    """Create the daily_results table used by the CLI (resolution) scraper."""
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id TEXT,
            date TEXT,
            high_f REAL,
            low_f REAL,
            is_final INTEGER,
            UNIQUE(station_id, date)
        )
    """)
    conn.commit()


def local_day_start_utc(tz_name):
    """UTC ISO string for the most recent LOCAL midnight in the given timezone.

    Daily high/low is a local-day concept. UTC midnight is 7-8pm local for US
    stations, so filtering on UTC midnight mixes two calendar days. NWS timestamps
    are stored as UTC ('...+00:00'), so we return a matching UTC string to compare.
    """
    now_local = datetime.now(ZoneInfo(tz_name))
    midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def get_with_retry(session, url, headers=None, params=None, timeout=10, retries=3,
                   backoff=2.0, logger=None):
    """GET with exponential backoff. Returns a Response (any status) or None if all
    attempts raised. NWS occasionally 500s or times out transiently; one try per
    cycle would silently drop that station's data right when we need it most.

    Pass query values via `params` (not baked into the URL) so requests URL-encodes
    them — critical for ISO timestamps, whose '+00:00' would otherwise be read as a
    space and 400.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=headers, params=params, timeout=timeout)
            # Retry on transient server errors; return immediately otherwise.
            if resp.status_code >= 500 and attempt < retries:
                if logger:
                    logger.warning("%s -> %s (attempt %d/%d), retrying",
                                   url, resp.status_code, attempt, retries)
                time.sleep(backoff ** attempt)
                continue
            return resp
        except Exception as e:  # timeout, connection reset, DNS, etc.
            last_exc = e
            if logger:
                logger.warning("%s failed (attempt %d/%d): %s", url, attempt, retries, e)
            if attempt < retries:
                time.sleep(backoff ** attempt)
    if logger and last_exc:
        logger.error("%s giving up after %d attempts: %s", url, retries, last_exc)
    return None
