import os
import argparse
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, help="Path to the log directory containing trajectory_log.json")
    args = parser.parse_args()

    log_dir = args.run
    if not os.path.exists(log_dir):
        print(f"Log directory {log_dir} does not exist.")
        sys.exit(1)

    os.makedirs('artifacts', exist_ok=True)
    scripts = [
        'scripts/plot_operations_2d.py',
        'scripts/plot_3d_replay.py',
        'scripts/plot_metrics.py'
    ]

    for script in scripts:
        print(f"Running {script}...")
        try:
            subprocess.run([sys.executable, script, '--run', log_dir], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running {script}: {e}")
            sys.exit(1)
            
    print("All artifacts generated successfully in artifacts/")

if __name__ == "__main__":
    main()
