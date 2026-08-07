"""24/7 scheduler: runs the observation collector every 15 min and the official CLI
scrape ~hourly. This is the process to keep alive (see deploy/ for auto-start setup).

Hardened so a single bad cycle can't silently kill collection:
  - each child runs under a hard timeout (a hung request can't freeze the loop forever)
  - the whole cycle body is wrapped so an unexpected error is logged and we continue
  - sleep is drift-corrected so cycles stay aligned to the 15-min cadence
  - everything goes to logs/scheduler.log, so a crash leaves a trail
"""
import os
import subprocess
import sys
import time

from weather.common import get_logger

log = get_logger("scheduler")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COLLECTOR = os.path.join(BASE_DIR, "weather", "live_observations.py")
CLI_SCRIPT = os.path.join(BASE_DIR, "weather", "cli_final.py")

INTERVAL_SECONDS = 900       # 15 minutes between observation polls
CLI_EVERY_N_CYCLES = 4       # official CLI scrape ~hourly (4 * 15 min)
CHILD_TIMEOUT = 300          # kill a child that runs longer than 5 min (likely hung)


def run_script(script):
    """Run a collector as a subprocess under a timeout. Never raises."""
    name = os.path.basename(script)
    try:
        result = subprocess.run([sys.executable, script], timeout=CHILD_TIMEOUT,
                                capture_output=True, text=True)
        if result.returncode == 0:
            log.info("%s finished OK", name)
        else:
            log.error("%s exited %s; stderr tail: %s",
                      name, result.returncode, (result.stderr or "").strip()[-500:])
    except subprocess.TimeoutExpired:
        log.error("%s TIMED OUT after %ss and was killed", name, CHILD_TIMEOUT)
    except Exception as e:
        log.error("failed to launch %s: %s", name, e)


def main():
    log.info("=== STARTING 24/7 WEATHER COLLECTOR (interval=%ss) ===", INTERVAL_SECONDS)
    cycle = 0
    while True:
        started = time.monotonic()
        try:
            log.info("cycle %d: collecting observations", cycle)
            run_script(COLLECTOR)
            if cycle % CLI_EVERY_N_CYCLES == 0:
                log.info("cycle %d: fetching official CLI results", cycle)
                run_script(CLI_SCRIPT)
        except Exception as e:  # belt-and-suspenders: a bad cycle must not kill the loop
            log.exception("unexpected error in cycle %d: %s", cycle, e)

        cycle += 1
        # Drift-corrected sleep: subtract the work we already did this cycle.
        elapsed = time.monotonic() - started
        nap = max(1.0, INTERVAL_SECONDS - elapsed)
        log.info("sleeping %.0f min", nap / 60)
        time.sleep(nap)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("stopping collector (keyboard interrupt)")
