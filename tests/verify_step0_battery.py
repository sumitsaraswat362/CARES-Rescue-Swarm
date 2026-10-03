#!/usr/bin/env python3
"""Verify Step 0: Battery init randomization actually produces different values per seed."""
import sys, os, random
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.core.mission import MissionManager

scenario = "scenarios/earthquake_hard.yaml"
config = "config/swarm_config.yaml"

print("=" * 60)
print("Step 0 Verification: Battery Randomization Across Seeds")
print("=" * 60)

all_profiles = []
for seed in [42, 43, 44, 45, 46]:
    random.seed(seed)
    np.random.seed(seed)
    mission = MissionManager(scenario, config)
    levels = [round(uav.battery.level * 100, 1) for uav in mission.uavs]
    all_profiles.append(levels)
    print(f"Seed {seed}: {levels}")

# Check variance across seeds
profiles_array = np.array(all_profiles)
per_uav_std = np.std(profiles_array, axis=0)
print(f"\nPer-UAV std across seeds: {[round(s, 1) for s in per_uav_std]}")
print(f"Mean std: {round(np.mean(per_uav_std), 1)}%")

if np.mean(per_uav_std) < 1.0:
    print("\n❌ FAIL: Battery levels barely vary across seeds (< 1% std)")
    sys.exit(1)
else:
    print("\n✅ PASS: Battery levels diverge meaningfully across seeds")
    sys.exit(0)

