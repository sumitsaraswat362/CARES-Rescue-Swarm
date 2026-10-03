import matplotlib.pyplot as plt
from typing import List, Dict, Any
import numpy as np

class MetricsDashboard:
    def __init__(self, metrics_history: List[dict], final_report: dict):
        self.metrics_history = metrics_history
        self.final_report = final_report

    def plot(self, save_path: str = None):
        if self.final_report.get('schema') == 'cares-evidence/v2':
            raise ValueError('Legacy plotter does not support v2 metrics; use the web dashboard and raw evidence audit')
        plt.style.use('dark_background')
        fig, axes = plt.subplots(2, 3, figsize=(15, 10), dpi=300)
        
        times = range(len(self.metrics_history))
        
        # Safely extract metrics; default to 0 if key is missing
        completion_pct = [m.get('completion_pct', 0) for m in self.metrics_history]
        connectivity_ratio = [m.get('connectivity_ratio', 0) * 100 for m in self.metrics_history]
        fiedler_values = [m.get('fiedler_value', 0) for m in self.metrics_history]
        active_uavs = [m.get('connected_uavs', 0) for m in self.metrics_history]
        
        # 1. Mission Completion %
        ax1 = axes[0, 0]
        ax1.plot(times, completion_pct, color='#00ff00', linewidth=2)
        ax1.set_title('Mission Completion %', fontweight='bold')
        ax1.set_xlabel('Time Steps')
        ax1.set_ylabel('% Completed')
        ax1.set_ylim(0, 105)
        ax1.grid(True, alpha=0.3)
        
        # 2. Connectivity % and Fiedler Value
        ax2 = axes[0, 1]
        line1, = ax2.plot(times, connectivity_ratio, color='#00aaff', linewidth=2, label='Connectivity %')
        ax2.set_xlabel('Time Steps')
        ax2.set_ylabel('Connectivity %')
        ax2.set_ylim(0, 105)
        
        ax2_twin = ax2.twinx()
        line2, = ax2_twin.plot(times, fiedler_values, color='#ffaa00', linewidth=2, label='Fiedler Value')
        ax2_twin.set_ylabel('Fiedler Value')
        
        ax2.set_title('Network Connectivity', fontweight='bold')
        lines = [line1, line2]
        ax2.legend(lines, [l.get_label() for l in lines], loc='best')
        ax2.grid(True, alpha=0.3)
        
        # 3. Active UAVs
        ax3 = axes[0, 2]
        ax3.step(times, active_uavs, color='#ff3366', linewidth=2, where='post')
        ax3.set_title('Active UAVs', fontweight='bold')
        ax3.set_xlabel('Time Steps')
        ax3.set_ylabel('Count')
        if active_uavs:
            ax3.set_ylim(0, max(active_uavs) + 2)
        ax3.grid(True, alpha=0.3)
        
        # 4. Battery levels
        ax4 = axes[1, 0]
        if self.metrics_history and 'battery_levels' in self.metrics_history[0]:
            num_uavs = len(self.metrics_history[0]['battery_levels'])
            for i in range(num_uavs):
                batt = [m.get('battery_levels', [])[i] if i < len(m.get('battery_levels', [])) else 0 for m in self.metrics_history]
                ax4.plot(times, batt, label=f'UAV {i}')
        
        ax4.set_title('Battery Levels', fontweight='bold')
        ax4.set_xlabel('Time Steps')
        ax4.set_ylabel('Battery %')
        ax4.set_ylim(0, 105)
        if self.metrics_history and 'battery_levels' in self.metrics_history[0] and len(self.metrics_history[0]['battery_levels']) <= 10:
            ax4.legend(loc='best', fontsize='small')
        ax4.grid(True, alpha=0.3)
        
        # 5. Tasks completed per UAV
        ax5 = axes[1, 1]
        tasks_per_uav = self.final_report.get('tasks_per_uav', {})
        if tasks_per_uav:
            # Handle list or dict format
            if isinstance(tasks_per_uav, dict):
                uav_ids = list(tasks_per_uav.keys())
                counts = list(tasks_per_uav.values())
            elif isinstance(tasks_per_uav, list):
                uav_ids = [str(i) for i in range(len(tasks_per_uav))]
                counts = tasks_per_uav
            
            ax5.bar(uav_ids, counts, color='#aa00ff')
            ax5.set_xticks(range(len(uav_ids)))
            ax5.set_xticklabels(uav_ids)
        
        ax5.set_title('Tasks Completed per UAV', fontweight='bold')
        ax5.set_xlabel('UAV ID')
        ax5.set_ylabel('Tasks Completed')
        ax5.grid(True, alpha=0.3, axis='y')
        
        # 6. Final Report Summary
        ax6 = axes[1, 2]
        ax6.axis('off')
        
        summary_text = "Final Report Summary\n"
        summary_text += "-" * 20 + "\n"
        for k, v in self.final_report.items():
            if k not in ['tasks_per_uav', 'battery_levels']:
                clean_k = k.replace('_', ' ').title()
                if isinstance(v, float):
                    summary_text += f"{clean_k}: {v:.2f}\n"
                else:
                    summary_text += f"{clean_k}: {v}\n"
                
        ax6.text(0.05, 0.95, summary_text, transform=ax6.transAxes,
                 fontsize=12, verticalalignment='top',
                 fontfamily='monospace', color='white')
                 
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, bbox_inches='tight')
            print(f"Dashboard saved to {save_path}")
        else:
            plt.show()

def generate_report(final_report: dict):
    print("\n" + "="*50)
    print("FINAL MISSION REPORT".center(50))
    print("="*50)
    for k, v in final_report.items():
        if isinstance(v, dict):
            print(f"{k.replace('_', ' ').title()}:")
            for sub_k, sub_v in v.items():
                print(f"  - {sub_k}: {sub_v}")
        elif isinstance(v, float):
            print(f"{k.replace('_', ' ').title().ljust(25)}: {v:.2f}")
        else:
            print(f"{k.replace('_', ' ').title().ljust(25)}: {v}")
    print("="*50 + "\n")
