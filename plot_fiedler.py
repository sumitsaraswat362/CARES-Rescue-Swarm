import os
import json
import numpy as np
import matplotlib.pyplot as plt

def main():
    log_dir = "logs"
    seeds = [d for d in os.listdir(log_dir) if d.startswith("mc_seed_")]
    
    times = None
    all_fiedler = []
    all_cov = []
    
    for seed_dir in seeds:
        metrics_file = os.path.join(log_dir, seed_dir, "metrics_history.json")
        if not os.path.exists(metrics_file):
            continue
            
        with open(metrics_file, "r") as f:
            data = json.load(f)
            
        t = [d["time"] for d in data]
        fied = [d["fiedler"] for d in data]
        cov = [d.get("avg_covariance", 0.0) for d in data]
        
        if times is None or len(t) > len(times):
            times = t
            
        all_fiedler.append(fied)
        all_cov.append(cov)

    if not all_fiedler:
        print("No metrics data found.")
        return

    # Pad shorter arrays if simulation ended early
    max_len = len(times)
    for i in range(len(all_fiedler)):
        if len(all_fiedler[i]) < max_len:
            pad_len = max_len - len(all_fiedler[i])
            all_fiedler[i].extend([all_fiedler[i][-1]] * pad_len)
            all_cov[i].extend([all_cov[i][-1]] * pad_len)

    fiedler_matrix = np.array(all_fiedler)
    cov_matrix = np.array(all_cov)
    
    fiedler_mean = np.mean(fiedler_matrix, axis=0)
    fiedler_std = np.std(fiedler_matrix, axis=0)
    
    cov_mean = np.mean(cov_matrix, axis=0)
    cov_std = np.std(cov_matrix, axis=0)
    
    fig, ax1 = plt.subplots(figsize=(10, 6))

    color = 'tab:blue'
    ax1.set_xlabel('Mission Time (s)', fontweight='bold')
    ax1.set_ylabel('Fiedler Eigenvalue (λ₂)', color=color, fontweight='bold')
    ax1.plot(times, fiedler_mean, color=color, label='Mean λ₂ (Connectivity)')
    ax1.fill_between(times, fiedler_mean - fiedler_std, fiedler_mean + fiedler_std, color=color, alpha=0.2)
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.axhline(y=0.1, color='red', linestyle='--', label='Critical Connectivity Threshold')
    
    ax2 = ax1.twinx()  
    color = 'tab:orange'
    ax2.set_ylabel('Avg EKF Positional Covariance (m²)', color=color, fontweight='bold')  
    ax2.plot(times, cov_mean, color=color, label='Mean EKF Covariance')
    ax2.fill_between(times, cov_mean - cov_std, cov_mean + cov_std, color=color, alpha=0.2)
    ax2.tick_params(axis='y', labelcolor=color)

    fig.suptitle('Pillar 1 & 2: Resilience under Packet Loss & Battery Drain (30 Seeds)', fontsize=14, fontweight='bold')
    
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left')

    fig.tight_layout()  
    plt.savefig('fiedler_covariance_plot.png', dpi=300)
    print("Plot saved to fiedler_covariance_plot.png")

if __name__ == "__main__":
    main()

