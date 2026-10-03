#!/usr/bin/env bash
# Cleans up untracked, stale local log files that Git cannot automatically remove.

echo "Cleaning up untracked local logs..."
rm -f logs/final_report.json logs/metrics_history.json logs/mission_log.json logs/uav_telemetry.json
rm -rf logs/fresh_check_* logs/test_verify*
echo "✅ Local workspace is now clean."

