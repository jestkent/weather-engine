import json
import os

# Define the path to the config file
config_path = os.path.join("config", "stations.json")

print("--- TESTING SETUP ---")

# 1. Check if file exists
if os.path.exists(config_path):
    print("✅ stations.json found!")
else:
    print("❌ stations.json NOT found. Check your folder names.")
    exit()

# 2. Try to read the file
try:
    with open(config_path, "r") as f:
        data = json.load(f)
    
    # 3. Print what we found
    print(f"✅ Successfully loaded configuration.")
    print(f"Found {len(data['stations'])} stations:")
    
    for key, info in data['stations'].items():
        print(f"   -> {info['name']}")

except Exception as e:
    print(f"❌ Error reading file: {e}")

print("---------------------")