import urllib.request
import json

# IIT Bombay bounding box
bbox = "19.125,72.905,19.140,72.925"
query = f"""
[out:json];
(
  way["building"]({bbox});
);
out body;
>;
out skel qt;
"""
url = "http://overpass-api.de/api/interpreter"
data = query.encode('utf-8')
headers = {'User-Agent': 'CARES-UAV-X/1.0'}
try:
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as response:
        with open("iitb_buildings.json", "w") as f:
            f.write(response.read().decode('utf-8'))
    print("Success")
except Exception as e:
    print(f"Error: {e}")

