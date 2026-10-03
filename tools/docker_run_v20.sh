#!/usr/bin/env bash
# docker_run_v20.sh — PX4 SIH headless flight gates (pure pymavlink, no ROS2)
# Uses mavlink_flight.py bridge to avoid rclpy dependency.
set -euo pipefail

LOG=/tmp/run_px4_v20.log
PX4_IMG="ros:humble-ros-base-jammy"
BUILD_DIR="/tmp/UAV-X-Build-v20"

echo "=== Starting PX4 SIH Gate v20 ===" | tee "$LOG"

docker run --rm \
  -v "$BUILD_DIR:/workspace" \
  --platform linux/arm64 \
  "$PX4_IMG" \
  bash -c "
set -e
echo '--- Bootstrap ---'
cd /workspace
git -C /workspace fetch origin main
git -C /workspace reset --hard origin/main

# Install dependencies (pymavlink only — no ROS2 packages needed)
apt-get update -qq
apt-get install -y -q python3-pip python3-wheel python3-yaml
pip3 install -q pymavlink

echo '--- Verify pymavlink ---'
python3 -c 'from pymavlink import mavutil; print(\"pymavlink OK\")'

echo '--- Running Single Vehicle Gate (SIH mode) ---'
python3 tools/run_px4_gate.py \
  --px4 /workspace/PX4-Autopilot \
  --out /workspace/logs/px4-ci-v20

echo '--- Running Swarm Fault-Injection Gate (SIH mode) ---'
python3 tools/run_px4_swarm_gate.py \
  --px4 /workspace/PX4-Autopilot \
  --out /workspace/logs/px4-swarm-v20

echo '=== ALL DONE ==='
" 2>&1 | tee -a "$LOG"
