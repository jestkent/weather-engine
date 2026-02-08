import requests

# We will check New York (OKX) and Los Angeles (LOX)
urls = [
    "https://forecast.weather.gov/product.php?site=NWS&product=CLI&issuedby=OKX&format=txt",
    "https://forecast.weather.gov/product.php?site=NWS&product=CLI&issuedby=LOX&format=txt"
]

headers = {"User-Agent": "(debug_weather_script, contact@example.com)"}

print("--- STARTING RAW TEXT DUMP ---")

for url in urls:
    print(f"\nFetching: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        text = response.text
        
        # Print the first 20 lines of the report
        print("------------------------------------------------")
        lines = text.split('\n')
        for i in range(min(20, len(lines))):
            print(f"LINE {i}: {lines[i]}")
        print("------------------------------------------------")
        
    except Exception as e:
        print(f"Error: {e}")

print("\n--- END DUMP ---")