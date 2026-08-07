"""Scrape the NWS CLI (Climate) report -> data/daily_results.db.

This is the RESOLUTION source: Polymarket weather markets settle on the official CLI
daily high/low, so getting the date and the finality right matters more than anything.

Two correctness rules learned from the real reports:

1. DATE the row by the report's own "...CLIMATE SUMMARY FOR <MONTH DAY YEAR>..." line,
   never by wall-clock "today". A report issued 2:34 AM Jul 27 summarizes JULY 26; the
   old code stamped it Jul 27 (off-by-one), corrupting the resolution row.

2. FINAL vs PRELIMINARY. A report whose temperature block is headed "YESTERDAY" is the
   settled morning summary (is_final=1). One headed "TODAY" (with "VALID TODAY AS OF
   HHMM ...") is an intraday running value that will still change (is_final=0). We never
   let a preliminary overwrite a stored final.
"""
import html
import re
from datetime import datetime

import requests

from common import (
    RESULTS_DB_PATH, get_logger, get_user_agent, get_with_retry, init_results_db,
    load_config, open_db,
)

log = get_logger("cli_final")

VALID_MIN, VALID_MAX = -60.0, 140.0  # sanity bounds for a US surface temperature (F)


def fetch_cli_text(session, wfo, cli_code, user_agent):
    """Return the plain text inside the report's <pre> block, or None."""
    url = f"https://forecast.weather.gov/product.php?site={wfo}&product=CLI&issuedby={cli_code}"
    resp = get_with_retry(session, url, headers={"User-Agent": user_agent}, timeout=15, logger=log)
    if resp is None or resp.status_code != 200:
        log.warning("%s: fetch failed (%s)", cli_code, getattr(resp, "status_code", "no response"))
        return None
    match = re.search(r"<pre[^>]*>(.*?)</pre>", resp.text, re.DOTALL)
    if not match:
        # e.g. KSOW: this WFO/code has no CLI product page.
        log.warning("%s: page loaded but has no <pre> report block", cli_code)
        return None
    return html.unescape(match.group(1))


def parse_report_date(text):
    """Date the report is FOR, from '...CLIMATE SUMMARY FOR JULY 26 2026...'. -> 'YYYY-MM-DD' or None."""
    m = re.search(r"SUMMARY FOR\s+([A-Z]+\s+\d{1,2}\s+\d{4})", text, re.IGNORECASE)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).title(), "%B %d %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_temps_and_finality(text):
    """Return (high_f, low_f, is_final).

    Reads the MAXIMUM/MINIMUM 'observed' value (first number on the line) from within
    the TEMPERATURE section only, and decides finality from the TODAY/YESTERDAY heading
    plus the 'VALID TODAY AS OF' marker.
    """
    lines = text.split("\n")

    # Isolate the TEMPERATURE (F) block: from its header to the next section.
    start = next((i for i, ln in enumerate(lines) if ln.strip().upper().startswith("TEMPERATURE")), None)
    if start is None:
        return None, None, 0
    block = []
    for ln in lines[start + 1:]:
        s = ln.strip().upper()
        if s.startswith(("PRECIPITATION", "SNOWFALL", "DEGREE DAYS", "WIND")):
            break
        block.append(ln)

    # Intraday reports say the day isn't settled yet.
    intraday = "VALID TODAY AS OF" in text.upper()
    period_is_today = None  # True=TODAY, False=YESTERDAY, None=unknown

    high = low = None
    for ln in block:
        s = ln.strip().upper()
        if s == "TODAY":
            period_is_today = True
        elif s == "YESTERDAY":
            period_is_today = False
        elif s.startswith("MAXIMUM") and high is None:
            high = _first_temp(s)
        elif s.startswith("MINIMUM") and low is None:
            low = _first_temp(s)

    # Final = settled prior-day summary: labeled YESTERDAY and not an intraday snapshot.
    is_final = 1 if (period_is_today is False and not intraday) else 0
    return high, low, is_final


def _first_temp(line):
    """First integer/decimal on the line (the observed value column), if in range."""
    for tok in re.findall(r"-?\d+(?:\.\d+)?", line):
        val = float(tok)
        if VALID_MIN <= val <= VALID_MAX:
            return val
    return None


def save_result(conn, station_id, date_str, high, low, is_final):
    """Upsert on (station_id, date); never let a preliminary clobber a stored final."""
    c = conn.cursor()
    c.execute("SELECT is_final FROM daily_results WHERE station_id=? AND date=?",
              (station_id, date_str))
    row = c.fetchone()
    if row and row[0] == 1 and is_final == 0:
        log.info("%s %s: keeping stored FINAL, ignoring preliminary %s/%s",
                 station_id, date_str, high, low)
        return
    c.execute("""
        INSERT INTO daily_results (station_id, date, high_f, low_f, is_final)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(station_id, date) DO UPDATE SET
            high_f=excluded.high_f, low_f=excluded.low_f, is_final=excluded.is_final
    """, (station_id, date_str, high, low, is_final))
    conn.commit()
    tag = "FINAL" if is_final else "prelim"
    log.info("%s %s: high=%s low=%s [%s]", station_id, date_str, high, low, tag)


def run_cli_check():
    config = load_config()
    user_agent = get_user_agent(config)
    session = requests.Session()
    conn = open_db(RESULTS_DB_PATH)
    init_results_db(conn)

    log.info("--- CLI results check start ---")
    for _, station in config["stations"].items():
        sid = station["station_id"]
        wfo = station["wfo"]
        cli_code = station.get("cli_code")
        if not cli_code:
            log.info("%s: skipped (no cli_code in config)", sid)
            continue

        text = fetch_cli_text(session, wfo, cli_code, user_agent)
        if not text:
            continue

        date_str = parse_report_date(text)
        if not date_str:
            log.warning("%s: could not parse report date; skipping", sid)
            continue

        high, low, is_final = parse_temps_and_finality(text)
        if high is None and low is None:
            log.warning("%s %s: found report but parsed no temps", sid, date_str)
            continue
        save_result(conn, sid, date_str, high, low, is_final)

    conn.close()
    log.info("--- CLI results check done ---")


if __name__ == "__main__":
    run_cli_check()
