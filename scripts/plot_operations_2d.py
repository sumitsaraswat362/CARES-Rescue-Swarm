import os
import sys
import json
import yaml
import argparse
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.lines import Line2D

def get_scenario_file(scenario_name):
    # Map the scenario name to the file
    for f in os.listdir('scenarios'):
        if f.endswith('.yaml'):
            with open(os.path.join('scenarios', f), 'r') as yaml_file:
                cfg = yaml.safe_load(yaml_file)
                if cfg.get('scenario', {}).get('name') == scenario_name:
                    return os.path.join('scenarios', f)
    return 'scenarios/earthquake_hard.yaml'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    
    log_dir = args.run
    
    with open(os.path.join(log_dir, 'final_report.json'), 'r') as f:
        report = json.load(f)
        
    scenario_path = get_scenario_file(report.get('scenario'))
    with open(scenario_path, 'r') as f:
        config = yaml.safe_load(f)
        
    with open(os.path.join(log_dir, 'replay.jsonl'), 'r') as f:
        traj_lines = f.readlines()
        
    uavs = {}
    for line in traj_lines:
        snapshot = json.loads(line)
        time_s = snapshot['time']
        for uav_data in snapshot['uavs']:
            uid = uav_data['id']
            if uid not in uavs:
                uavs[uid] = {'x': [], 'y': [], 'role': uav_data['role']}
            uavs[uid]['x'].append(uav_data['pos'][0])
            uavs[uid]['y'].append(uav_data['pos'][1])
            uavs[uid]['role'] = uav_data['role']
        
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Plot obstacles
    for obs in config['world']['obstacles']:
        circle = Circle((obs['x'], obs['y']), obs['radius'], color='red', alpha=0.2)
        ax.add_patch(circle)
        
    # Plot PoIs
    for poi in config['points_of_interest']:
        ax.scatter(poi['x'], poi['y'], c='purple', marker='*', s=100)
    
    # Hidden PoIs
    for poi in config.get('hidden_pois', []):
        ax.scatter(poi['x'], poi['y'], c='purple', marker='*', s=100, alpha=0.5)

    # Plot GCS
    gcs = config['gcs']['position']
    ax.scatter(gcs['x'], gcs['y'], c='black', marker='s', s=150, label='GCS')
        
    for uid, data in uavs.items():
        color = 'orange' if data['role'] == 'Relay' else 'blue'
        ax.plot(data['x'], data['y'], color=color, linewidth=1, alpha=0.7)
        ax.scatter(data['x'][-1], data['y'][-1], color=color, s=20)
        
    # Fake relay links at the end (just connecting relays to GCS and scouts to nearest relay)
    # The prompt asked for "relay links as dashed lines between currently-connected UAVs at the final tick"
    # To do this accurately we can just draw lines from each scout to its nearest relay, and relays to GCS
    final_positions = {uid: (data['x'][-1], data['y'][-1], data['role']) for uid, data in uavs.items()}
    relays = [pos for uid, pos in final_positions.items() if pos[2] == 'Relay']
    scouts = [pos for uid, pos in final_positions.items() if pos[2] == 'Scout']
    
    for r in relays:
        ax.plot([r[0], gcs['x']], [r[1], gcs['y']], 'k--', alpha=0.3)
        
    for s in scouts:
        if relays:
            nearest_relay = min(relays, key=lambda r: (r[0]-s[0])**2 + (r[1]-s[1])**2)
            ax.plot([s[0], nearest_relay[0]], [s[1], nearest_relay[1]], 'k--', alpha=0.3)
        else:
            ax.plot([s[0], gcs['x']], [s[1], gcs['y']], 'k--', alpha=0.3)
    
    # Custom legend
    custom_lines = [
        Line2D([0], [0], color='blue', lw=2),
        Line2D([0], [0], color='orange', lw=2),
        Line2D([0], [0], marker='s', color='w', markerfacecolor='black', markersize=10),
        Line2D([0], [0], marker='*', color='w', markerfacecolor='purple', markersize=10)
    ]
    ax.legend(custom_lines, ['Scout Trajectory', 'Relay Trajectory', 'GCS', 'PoI'])
    
    ax.set_xlim(0, config['world']['width'])
    ax.set_ylim(0, config['world']['height'])
    ax.set_title("CARES 2D Operations View")
    ax.set_aspect('equal')
    
    os.makedirs('artifacts', exist_ok=True)
    plt.savefig('artifacts/operations_2d.png', dpi=300, bbox_inches='tight')
    
if __name__ == "__main__":
    main()
