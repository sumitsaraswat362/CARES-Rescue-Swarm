import os
import sys
import json
import yaml
import argparse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from mpl_toolkits.mplot3d import Axes3D

def get_scenario_file(scenario_name):
    for f in os.listdir('scenarios'):
        if f.endswith('.yaml'):
            with open(os.path.join('scenarios', f), 'r') as yaml_file:
                cfg = yaml.safe_load(yaml_file)
                if cfg.get('scenario', {}).get('name') == scenario_name:
                    return os.path.join('scenarios', f)
    return 'scenarios/earthquake_hard.yaml'

def draw_cylinder(ax, x, y, radius, height, color='red', alpha=0.2):
    z = np.linspace(0, height, 2)
    theta = np.linspace(0, 2*np.pi, 20)
    theta_grid, z_grid = np.meshgrid(theta, z)
    x_grid = radius * np.cos(theta_grid) + x
    y_grid = radius * np.sin(theta_grid) + y
    ax.plot_surface(x_grid, y_grid, z_grid, color=color, alpha=alpha)

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
        
    traj = []
    for line in traj_lines:
        snapshot = json.loads(line)
        time_s = snapshot['time']
        for uav_data in snapshot['uavs']:
            traj.append({
                'time': time_s,
                'uav_id': uav_data['id'],
                'x': uav_data['pos'][0],
                'y': uav_data['pos'][1],
                'z': uav_data['altitude'],
                'role': uav_data['role']
            })

    times = sorted(list(set([entry['time'] for entry in traj])))
    
    # Sub-sample time for faster gif (e.g. 1 frame every 5 sim seconds)
    times = times[::50]
    
    if not times:
        print("No trajectory data.")
        sys.exit(0)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    def setup_axes():
        ax.clear()
        ax.set_xlim(0, config['world']['width'])
        ax.set_ylim(0, config['world']['height'])
        ax.set_zlim(0, 150)
        ax.set_title("CARES 3D Mission Replay")
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.set_zlabel("Altitude (m)")

        # Obstacles
        for obs in config['world']['obstacles']:
            draw_cylinder(ax, obs['x'], obs['y'], obs['radius'], 100)

        # GCS
        gcs = config['gcs']['position']
        ax.scatter(gcs['x'], gcs['y'], 0, c='black', marker='s', s=100)
        
        # PoIs
        for poi in config['points_of_interest']:
            ax.scatter(poi['x'], poi['y'], 0, c='purple', marker='*', s=50)

    # For the static mid-mission frame
    mid_time = times[len(times)//2]
    
    def update(frame_time):
        setup_axes()
        
        # Gather all past positions up to this time for trailing
        past = [entry for entry in traj if entry['time'] <= frame_time and entry['time'] > frame_time - 30]
        current = [entry for entry in traj if entry['time'] == frame_time]
        
        uav_paths = {}
        for entry in past:
            uid = entry['uav_id']
            if uid not in uav_paths:
                uav_paths[uid] = {'x': [], 'y': [], 'z': [], 'role': entry['role']}
            uav_paths[uid]['x'].append(entry['x'])
            uav_paths[uid]['y'].append(entry['y'])
            uav_paths[uid]['z'].append(entry['z'])
            uav_paths[uid]['role'] = entry['role']
            
        for uid, data in uav_paths.items():
            color = 'orange' if data['role'] == 'Relay' else 'blue'
            ax.plot(data['x'], data['y'], data['z'], color=color, alpha=0.4)
            
        for entry in current:
            color = 'orange' if entry['role'] == 'Relay' else 'blue'
            ax.scatter(entry['x'], entry['y'], entry['z'], c=color, s=40)
            
    # Save the static overview
    update(mid_time)
    os.makedirs('artifacts', exist_ok=True)
    plt.savefig('artifacts/cares_3d_overview.png', dpi=300)
    
    # Save the animation
    ani = FuncAnimation(fig, update, frames=times, interval=100)
    ani.save('artifacts/cares_3d_replay.gif', writer=PillowWriter(fps=10))

if __name__ == "__main__":
    main()
