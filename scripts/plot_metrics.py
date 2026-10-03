import os
import sys
import json
import argparse
import matplotlib.pyplot as plt

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    
    log_dir = args.run
    
    with open(os.path.join(log_dir, 'metrics_history.json'), 'r') as f:
        metrics = json.load(f)
        
    with open(os.path.join(log_dir, 'events.jsonl'), 'r') as f:
        events = [json.loads(line) for line in f.readlines()]
        
    times = [m['time'] for m in metrics]
    fiedler = [m.get('fiedler', 0) or m.get('fiedler_value', 0) for m in metrics]
    avg_cov = [m.get('avg_covariance', 0) for m in metrics]
    
    failures = [entry['time'] for entry in events if entry.get('event') == 'injected_failure']

    fig, ax1 = plt.subplots(figsize=(10, 5))
    
    color = 'tab:blue'
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Fiedler Eigenvalue (Connectivity)', color=color)
    ax1.plot(times, fiedler, color=color, linewidth=2)
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.axhline(y=0.05, color='r', linestyle=':', label='CBF Safety Margin')
    
    ax2 = ax1.twinx()
    color = 'tab:red'
    ax2.set_ylabel('EKF Avg Position Covariance (m²)', color=color)
    ax2.plot(times, avg_cov, color=color, linewidth=2)
    ax2.tick_params(axis='y', labelcolor=color)
    
    for fail_time in failures:
        ax1.axvline(x=fail_time, color='k', linestyle='--', alpha=0.5)
        ax1.text(fail_time + 5, max(fiedler)*0.8, 'Failure', rotation=90, alpha=0.7)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.title("CARES: Uncertainty Drives Behavior (EKF + CBF Integration)")
    
    os.makedirs('artifacts', exist_ok=True)
    plt.savefig('artifacts/cares_metrics.png', dpi=300)
    
if __name__ == "__main__":
    main()
