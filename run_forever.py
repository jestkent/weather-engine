import time
import subprocess
import sys
from datetime import datetime

# Define the command to run the collector
# We use 'sys.executable' to make sure we use the same Python that is running this script
COLLECTOR_SCRIPT = "weather/live_observations.py"

print("--- 🔄 STARTING 24/7 WEATHER COLLECTOR ---")
print("Press Ctrl+C to stop.")

try:
    while True:
        now = datetime.now().strftime("%I:%M %p")
        print(f"\n[{now}] Waking up to collect data...")
        
        # This runs: py weather/live_observations.py
        result = subprocess.run([sys.executable, COLLECTOR_SCRIPT])
        
        if result.returncode == 0:
            print("✅ Collection successful.")
        else:
            print("❌ Collection script crashed!")
            
        print("💤 Sleeping for 15 minutes...")
        
        # Sleep for 15 minutes (15 * 60 seconds)
        time.sleep(900)

except KeyboardInterrupt:
    print("\n🛑 Stopping collector. Goodbye!")