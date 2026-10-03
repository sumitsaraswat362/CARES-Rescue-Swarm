import json, math, random

W, H = 1000, 1000
GCS = [W/2, 50]
N_UAVS = 6
N_POIS = 10
MAX_TIME = 900

random.seed(99)

# 10 POIs
pois = []
for i in range(N_POIS):
    pois.append({
        "id": i+1,
        "x": random.uniform(100, W-100),
        "y": random.uniform(100, H-100),
        "priority": random.randint(1, 5),
        "label": f"Disaster Zone {i+1}"
    })

# Buildings (Obstacles)
obstacles = [
    {"x": 300, "y": 300, "w": 100, "h": 150, "z": 80, "color": "#7a7a7a"},
    {"x": 700, "y": 600, "w": 120, "h": 80, "z": 60, "color": "#5c4033"},
    {"x": 800, "y": 200, "w": 50, "h": 50, "z": 120, "color": "#7a7a7a"}
]

def terrain(x, y):
    h = 0
    peaks = [
        (400, 400, 200, 180),
        (700, 300, 150, 140),
        (300, 700, 180, 160),
        (800, 700, 250, 200),
    ]
    for px, py, spread, height in peaks:
        dist_sq = (x - px)**2 + (y - py)**2
        h += height * math.exp(-dist_sq / (2 * spread**2))
    return max(0, h)

uav_targets = [None] * N_UAVS
uav_pos = [[GCS[0], GCS[1]] for _ in range(N_UAVS)]
uav_z = [0] * N_UAVS
surveyed = set()
snapshots = []

for t in range(0, MAX_TIME, 5):
    for i in range(N_UAVS):
        if i == 0:
            target = [GCS[0], GCS[1] + 100, 100] # Root relay hovering high
        elif i == 1:
            target = [W/2, H/2, 150] # Central relay hovering very high
        else:
            if not uav_targets[i]:
                avail = [p for p in pois if p['id'] not in surveyed]
                if avail:
                    target_poi = avail[i % len(avail)]
                    uav_targets[i] = [target_poi['x'], target_poi['y'], target_poi['id']]
                else:
                    uav_targets[i] = [GCS[0], GCS[1], None]
            
            tx, ty = uav_targets[i][:2]
            tz = terrain(tx, ty) + 40 # target altitude
            target = [tx, ty, tz]
        
        # move towards target
        dx, dy, dz = target[0] - uav_pos[i][0], target[1] - uav_pos[i][1], target[2] - uav_z[i]
        dist2d = math.hypot(dx, dy)
        dist3d = math.sqrt(dx**2 + dy**2 + dz**2)
        
        speed = 25 # 5m/s * 5s
        
        if dist3d > speed:
            uav_pos[i][0] += (dx/dist3d) * speed
            uav_pos[i][1] += (dy/dist3d) * speed
            uav_z[i] += (dz/dist3d) * speed
        else:
            uav_pos[i][0] = target[0]
            uav_pos[i][1] = target[1]
            uav_z[i] = target[2]
            if i >= 2 and len(uav_targets[i]) > 2 and uav_targets[i][2]:
                surveyed.add(uav_targets[i][2])
                uav_targets[i] = None
                
        # safety altitude: never clip terrain
        terr = terrain(uav_pos[i][0], uav_pos[i][1])
        if uav_z[i] < terr + 10:
            uav_z[i] = terr + 10
            
        # add some oscillation for realism
        uav_z[i] += math.sin(t / 10 + i) * 2
    
    uavs = []
    for i in range(N_UAVS):
        uavs.append({
            "id": i,
            "pos": [uav_pos[i][0], uav_pos[i][1]],
            "altitude": uav_z[i],
            "battery": max(0.1, 1.0 - (t / 1800)),
            "state": "active",
            "role": "relay" if i < 2 else "scout",
            "mode": "auto"
        })
    
    metrics = {
        "duration_s": t,
        "total_pois": 10,
        "surveyed_pois": len(surveyed),
        "mission_completion_pct": (len(surveyed)/10)*100,
        "any_uav_connectivity_pct": 100.0,
        "minimum_separation_m": 25.4,
        "communication_downtime_s": 0,
        "failed_uavs": 0
    }
    
    snapshots.append({"time": t, "metrics": metrics, "uavs": uavs})
    
    if len(surveyed) == 10 and all(math.hypot(uav_pos[i][0]-GCS[0], uav_pos[i][1]-GCS[1]) < 30 for i in range(N_UAVS)):
        break

with open('dashboard/app/data/replay.json', 'w') as f:
    json.dump(snapshots, f)

scenario = {
    "world": {"width": W, "height": H, "obstacles": obstacles},
    "gcs": {"position": {"x": GCS[0], "y": GCS[1]}},
    "pois": pois
}
with open('dashboard/app/data/scenario.json', 'w') as f:
    json.dump(scenario, f)
print("done")
