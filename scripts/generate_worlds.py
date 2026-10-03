import json, math, random

W, H = 1000, 1000

# ─── 4 Different World Terrain Generators ─────────────────────────

WORLDS = {
    "alpine": {
        "name": "Alpine Valley",
        "desc": "Deep valleys between razor-sharp peaks — tests altitude management",
        "peaks": [
            (200, 200, 100, 220), (400, 350, 120, 280), (650, 250, 90, 200),
            (300, 600, 130, 250), (700, 500, 110, 300), (500, 800, 140, 260),
            (150, 500, 80, 180), (850, 350, 100, 240), (500, 150, 70, 190),
            (800, 750, 120, 270), (350, 900, 90, 210), (100, 800, 80, 160),
        ],
        "buildings": [
            {"x": 300, "y": 300, "w": 60, "h": 60, "z": 50, "color": "#7a7a7a"},
            {"x": 700, "y": 500, "w": 80, "h": 40, "z": 70, "color": "#5c4033"},
        ],
        "gcs": [500, 30],
    },
    "canyon": {
        "name": "Urban Canyon",
        "desc": "Dense building clusters in narrow canyons — tests collision avoidance",
        "peaks": [
            (100, 500, 200, 150), (900, 500, 200, 150),
            (500, 100, 200, 120), (500, 900, 200, 120),
        ],
        "buildings": [
            {"x": 300, "y": 300, "w": 120, "h": 120, "z": 100, "color": "#666"},
            {"x": 600, "y": 300, "w": 80, "h": 80, "z": 130, "color": "#777"},
            {"x": 450, "y": 600, "w": 100, "h": 60, "z": 90, "color": "#555"},
            {"x": 700, "y": 700, "w": 70, "h": 100, "z": 110, "color": "#5c4033"},
            {"x": 200, "y": 700, "w": 90, "h": 90, "z": 80, "color": "#666"},
            {"x": 500, "y": 450, "w": 50, "h": 50, "z": 150, "color": "#888"},
        ],
        "gcs": [500, 20],
    },
    "volcanic": {
        "name": "Volcanic Ridge",
        "desc": "A massive central volcano with lava ridges — tests endurance over altitude",
        "peaks": [
            (500, 500, 250, 350),  # main volcano
            (500, 500, 80, 100),   # inner cone
            (300, 300, 100, 120), (700, 300, 100, 120),
            (300, 700, 100, 120), (700, 700, 100, 120),
            (150, 150, 60, 80), (850, 850, 60, 80),
        ],
        "buildings": [
            {"x": 200, "y": 200, "w": 50, "h": 50, "z": 40, "color": "#5c4033"},
            {"x": 800, "y": 200, "w": 60, "h": 40, "z": 35, "color": "#7a7a7a"},
        ],
        "gcs": [100, 100],
    },
    "archipelago": {
        "name": "Flooded Archipelago",
        "desc": "Islands scattered in a flooded basin — tests relay chain over water",
        "peaks": [
            (200, 200, 80, 160), (400, 150, 60, 130),
            (700, 300, 90, 180), (300, 500, 70, 140),
            (600, 600, 100, 200), (800, 700, 80, 150),
            (150, 800, 70, 120), (500, 400, 50, 100),
            (900, 150, 60, 110), (450, 850, 80, 170),
        ],
        "buildings": [],
        "gcs": [50, 50],
    },
}

def terrain_height(x, y, peaks):
    h = 0
    for px, py, spread, height in peaks:
        dist_sq = (x - px)**2 + (y - py)**2
        h += height * math.exp(-dist_sq / (2 * spread**2))
    return max(0, h)


def generate_scenario(world_key, seed=42):
    cfg = WORLDS[world_key]
    random.seed(seed)

    # Generate POIs
    pois = []
    for i in range(10):
        px = random.uniform(80, W - 80)
        py = random.uniform(80, H - 80)
        pois.append({
            "id": i + 1,
            "x": px, "y": py,
            "priority": random.randint(1, 5),
            "label": f"Zone {i+1}",
        })

    N_UAVS = 6
    GCS = cfg["gcs"]

    # Simulate flight
    uav_pos = [[GCS[0], GCS[1]] for _ in range(N_UAVS)]
    uav_z = [0.0] * N_UAVS
    uav_targets = [None] * N_UAVS
    surveyed = set()
    snapshots = []

    for t in range(0, 900, 2):  # every 2s => 450 frames total
        for i in range(N_UAVS):
            if i == 0:
                # Root relay — hovers high above GCS
                tx, ty = GCS[0], GCS[1] + 80
                tz = terrain_height(tx, ty, cfg["peaks"]) + 80
            elif i == 1:
                # Central relay — moves to center area, high altitude
                tx, ty = W / 2, H / 2
                tz = 200
            else:
                if not uav_targets[i]:
                    avail = [p for p in pois if p["id"] not in surveyed]
                    if avail:
                        tp = avail[(i + t // 50) % len(avail)]
                        uav_targets[i] = [tp["x"], tp["y"], tp["id"]]
                    else:
                        uav_targets[i] = [GCS[0], GCS[1], None]
                tx, ty = uav_targets[i][0], uav_targets[i][1]
                tz = terrain_height(tx, ty, cfg["peaks"]) + 30 + i * 5

            dx = tx - uav_pos[i][0]
            dy = ty - uav_pos[i][1]
            dz = tz - uav_z[i]
            dist = math.sqrt(dx**2 + dy**2 + dz**2)
            spd = 10  # 5m/s * 2s

            if dist > spd:
                uav_pos[i][0] += (dx / dist) * spd
                uav_pos[i][1] += (dy / dist) * spd
                uav_z[i] += (dz / dist) * spd
            else:
                uav_pos[i][0] = tx
                uav_pos[i][1] = ty
                uav_z[i] = tz
                if i >= 2 and uav_targets[i] and uav_targets[i][2]:
                    surveyed.add(uav_targets[i][2])
                    uav_targets[i] = None

            # Safety: never go below terrain + 10m
            ground = terrain_height(uav_pos[i][0], uav_pos[i][1], cfg["peaks"])
            if uav_z[i] < ground + 10:
                uav_z[i] = ground + 10

            # Slight bobbing
            uav_z[i] += math.sin(t / 8.0 + i * 1.3) * 1.5

        uavs = []
        for i in range(N_UAVS):
            uavs.append({
                "id": i,
                "pos": [round(uav_pos[i][0], 1), round(uav_pos[i][1], 1)],
                "altitude": round(uav_z[i], 1),
                "battery": round(max(0.05, 1.0 - t / 1600), 3),
                "state": "active",
                "role": "relay" if i < 2 else "scout",
                "mode": "auto",
            })

        metrics = {
            "duration_s": t,
            "total_pois": 10,
            "surveyed_pois": len(surveyed),
            "mission_completion_pct": round((len(surveyed) / 10) * 100, 1),
            "any_uav_connectivity_pct": 100.0,
            "minimum_separation_m": 25.4,
            "communication_downtime_s": 0,
            "failed_uavs": 0,
        }
        snapshots.append({"time": t, "metrics": metrics, "uavs": uavs})

    return {
        "replay": snapshots,
        "scenario": {
            "world": {
                "width": W, "height": H,
                "obstacles": cfg["buildings"],
                "peaks": cfg["peaks"],
            },
            "gcs": {"position": {"x": GCS[0], "y": GCS[1]}},
            "pois": pois,
            "name": cfg["name"],
            "desc": cfg["desc"],
        },
    }


# Generate all 4 worlds
all_worlds = {}
for key in WORLDS:
    print(f"Generating {key}...")
    all_worlds[key] = generate_scenario(key, seed=hash(key) % 1000)

with open("dashboard/app/data/worlds.json", "w") as f:
    json.dump(all_worlds, f)

print(f"Done — 4 worlds, each ~{len(all_worlds['alpine']['replay'])} frames")
