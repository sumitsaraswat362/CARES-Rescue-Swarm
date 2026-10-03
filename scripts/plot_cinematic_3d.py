"""
CARES Cinematic 3D Mission Replay
Generates MATLAB-style and Python-style high-fidelity 3D visualisations
that match the competitor's aesthetic: complex terrain, 3D buildings,
comm-mesh lines, green dashed assignment lines, right-panel HUD.
"""

import os
import json
import math
import yaml
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from mpl_toolkits.mplot3d import Axes3D          # noqa: F401  (side-effect import)
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import imageio.v2 as imageio

# ─────────────────────────────────────────
#  Terrain generation
# ─────────────────────────────────────────

def make_terrain(width, height, res=100, seed=7):
    """Generate a geologically plausible, richly varied terrain."""
    rng = np.random.default_rng(seed)
    xs = np.linspace(0, width, res)
    ys = np.linspace(0, height, res)
    X, Y = np.meshgrid(xs, ys)
    Z = np.zeros_like(X)

    # Many varied Gaussian peaks — some tall and sharp, some wide and rolling
    hills = [
        # (cx, cy, amplitude, sigma_x, sigma_y, rotation_deg)
        (700,  300, 90,  250, 180, 20),
        (500,  900, 70,  200, 300, -15),
        (1300, 500, 110, 300, 200, 45),
        (1700, 900, 80,  250, 220, 10),
        (2100, 400, 60,  180, 150, 30),
        (2500, 800, 95,  220, 280, -5),
        (2800, 300, 50,  150, 120, 60),
        (900,  1500, 75, 280, 200, -20),
        (1500, 1700, 65, 300, 180, 35),
        (2200, 1600, 85, 240, 300, -30),
        (400,  1800, 55, 200, 160, 15),
        (1100, 1100, 40, 180, 200, 0),
        (2700, 1400, 60, 200, 150, 25),
        (1800, 200,  45, 150, 130, -10),
        (600,  600,  35, 120, 100, 50),
        (2000, 1300, 55, 170, 200, -40),
    ]

    for cx, cy, amp, sx, sy, rot_deg in hills:
        rot = math.radians(rot_deg)
        dx = (X - cx) * math.cos(rot) + (Y - cy) * math.sin(rot)
        dy = -(X - cx) * math.sin(rot) + (Y - cy) * math.cos(rot)
        Z += amp * np.exp(-(dx**2 / (2 * sx**2) + dy**2 / (2 * sy**2)))

    # Add fine-scale ridge noise
    for _ in range(10):
        nx = rng.uniform(0, width)
        ny = rng.uniform(0, height)
        na = rng.uniform(5, 20)
        ns = rng.uniform(80, 200)
        Z += na * np.exp(-((X - nx)**2 + (Y - ny)**2) / (2 * ns**2))

    return X, Y, Z


# ─────────────────────────────────────────
#  3-D box (building / obstacle)
# ─────────────────────────────────────────

def draw_box(ax, x, y, z_base, width, depth, height, facecolor, edgecolor='#aaaaaa', alpha=0.88):
    """Draw a solid 3-D rectangular box."""
    x2, y2, z2 = x + width, y + depth, z_base + height
    verts = np.array([
        [x,  y,  z_base], [x2, y,  z_base], [x2, y2, z_base], [x,  y2, z_base],
        [x,  y,  z2],     [x2, y,  z2],     [x2, y2, z2],     [x,  y2, z2],
    ])
    faces = [
        [verts[0], verts[1], verts[5], verts[4]],  # front
        [verts[2], verts[3], verts[7], verts[6]],  # back
        [verts[1], verts[2], verts[6], verts[5]],  # right
        [verts[0], verts[3], verts[7], verts[4]],  # left
        [verts[4], verts[5], verts[6], verts[7]],  # top
        [verts[0], verts[1], verts[2], verts[3]],  # bottom
    ]
    poly = Poly3DCollection(faces, alpha=alpha, facecolor=facecolor,
                            edgecolor=edgecolor, linewidth=0.6)
    ax.add_collection3d(poly)


# ─────────────────────────────────────────
#  UAV quadcopter icon (4 arms + centre)
# ─────────────────────────────────────────

def draw_uav(ax, x, y, z, arm=18, color='white'):
    """Draw a simple top-down quad-copter symbol at (x,y,z)."""
    arm_dx = [arm, -arm, 0, 0]
    arm_dy = [0, 0, arm, -arm]
    for ddx, ddy in zip(arm_dx, arm_dy):
        ax.plot([x, x + ddx], [y, y + ddy], [z, z],
                color=color, linewidth=1.4, zorder=30)
    ax.scatter(x, y, z, s=25, c=color, edgecolors='black', linewidths=0.8,
               zorder=31, depthshade=False)
    # rotor discs
    theta = np.linspace(0, 2*np.pi, 20)
    for ddx, ddy in zip(arm_dx, arm_dy):
        rx, ry = x + ddx + 8 * np.cos(theta), y + ddy + 8 * np.sin(theta)
        ax.plot(rx, ry, z, color=color, linewidth=0.8, alpha=0.7)


# ─────────────────────────────────────────
#  Core render function
# ─────────────────────────────────────────

def render(snapshot, config, X, Y, Z, out_path,
           elev=22, azim=230, dpi=160):
    """Render one frame to out_path."""
    BG   = '#080d1a'
    plt.style.use('dark_background')
    fig  = plt.figure(figsize=(15, 8.5), facecolor=BG)
    fig.patch.set_facecolor(BG)

    # ── Layout: 3-D axis on left 73%, text panel on right 27% ──
    ax   = fig.add_axes([0.01, 0.04, 0.65, 0.88], projection='3d')
    ax.set_facecolor(BG)

    W    = config['world']['width']
    H    = config['world']['height']
    ALT  = 160  # z ceiling

    # ── Axis styling ──
    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.set_facecolor((0.05, 0.07, 0.15, 0.6))
        pane.set_edgecolor('#334466')
    ax.grid(True)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis._axinfo['grid']['color']     = '#1a2a44'
        axis._axinfo['grid']['linewidth'] = 0.6

    ax.tick_params(colors='#aabbcc', labelsize=7)
    ax.xaxis.label.set_color('#aabbcc')
    ax.yaxis.label.set_color('#aabbcc')
    ax.zaxis.label.set_color('#aabbcc')
    ax.set_xlabel('East (m)',     labelpad=6, fontsize=9)
    ax.set_ylabel('North (m)',    labelpad=6, fontsize=9)
    ax.set_zlabel('Altitude (m)', labelpad=4, fontsize=9)

    # Reduce tick density
    ax.xaxis.set_major_locator(ticker.MultipleLocator(500))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(500))
    ax.zaxis.set_major_locator(ticker.MultipleLocator(50))

    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_zlim(0, ALT)
    ax.view_init(elev=elev, azim=azim)

    # ── Terrain surface ──
    surf = ax.plot_surface(
        X, Y, Z,
        cmap='gist_earth',      # exactly like the competitor — deep blue to bright ochre
        alpha=0.72,
        rstride=1, cstride=1,
        linewidth=0,
        antialiased=True,
        shade=True,
    )

    # ── Geofence: orange dashed rectangle at z≈2 ──
    gf_z  = 2.0
    gf_xs = [0, W, W, 0, 0]
    gf_ys = [0, 0, H, H, 0]
    gf_zs = [gf_z] * 5
    ax.plot(gf_xs, gf_ys, gf_zs,
            color='#ffaa00', linewidth=1.4, linestyle='--', zorder=5)

    # ── Buildings (obstacles) ──
    # Use two styles: collapsed rubble (dark brown) and intact structure (steel grey)
    obs_styles = [
        ('#5c3a1e', '#7a5030'),  # brown rubble
        ('#445566', '#6677aa'),  # grey building
        ('#aa3300', '#dd4400'),  # fire/red
        ('#334455', '#4466aa'),  # grey
        ('#5c3a1e', '#7a5030'),  # brown
    ]
    for i, obs in enumerate(config['world']['obstacles']):
        fc, ec = obs_styles[i % len(obs_styles)]
        r      = obs['radius']
        bw     = r * 1.8
        bd     = r * 1.5
        bh     = r * 0.9 + 30
        draw_box(ax,
                 obs['x'] - bw / 2, obs['y'] - bd / 2, 0,
                 bw, bd, bh,
                 facecolor=fc, edgecolor=ec, alpha=0.82)

    t       = snapshot['time']
    uavs_d  = snapshot['uavs']
    metrics = snapshot.get('metrics', {})

    # ── GCS marker ──
    gx = config['gcs']['position']['x']
    gy = config['gcs']['position']['y']
    ax.scatter(gx, gy, 0, s=90, c='red', marker='*',
               edgecolors='white', linewidths=0.8, zorder=20, depthshade=False)
    ax.text(gx + 30, gy + 30, 8,
            'GCS | command + data sink',
            color='cyan', fontsize=7.5, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#000d1a',
                      edgecolor='cyan', alpha=0.75))

    # ── PoIs ──
    poi_list   = config.get('points_of_interest', []) + config.get('hidden_pois', [])
    surveyed   = {p for p in range(30)}   # mark all as pending in static frame
    for poi in poi_list:
        col = '#ff4444' if poi.get('priority', 1) >= 5 else '#ffcc00'
        ax.scatter(poi['x'], poi['y'], 3,
                   s=55, c=col, marker='*',
                   edgecolors='white', linewidths=0.5,
                   zorder=15, depthshade=False)

    # ── UAVs ──
    positions = np.array([[u['pos'][0], u['pos'][1], u['altitude']]
                          for u in uavs_d])

    for i, u in enumerate(uavs_d):
        px, py, pz = positions[i]
        draw_uav(ax, px, py, pz, arm=20)

        # Green dashed assignment line to nearest PoI (scout role)
        role = u.get('role', '').lower()
        if 'scout' in role or 'survey' in role:
            if poi_list:
                dists = [math.hypot(px - p['x'], py - p['y']) for p in poi_list]
                bp    = poi_list[int(np.argmin(dists))]
                ax.plot([px, bp['x']], [py, bp['y']], [pz, 3],
                        color='#00ff88', linestyle='--',
                        linewidth=1.2, alpha=0.8, zorder=12)

    # ── Communication mesh (cyan lines, only short links) ──
    all_nodes = np.vstack([positions, [[gx, gy, 0]]])
    n         = len(all_nodes)
    for i in range(n):
        for j in range(i + 1, n):
            d = np.linalg.norm(all_nodes[i] - all_nodes[j])
            if d < 700:
                alpha_val = max(0.3, 1.0 - d / 700)
                ax.plot([all_nodes[i, 0], all_nodes[j, 0]],
                        [all_nodes[i, 1], all_nodes[j, 1]],
                        [all_nodes[i, 2], all_nodes[j, 2]],
                        color='cyan', linewidth=1.2,
                        alpha=alpha_val, zorder=10)

    # ── Camera-footprint rings under each UAV ──
    theta = np.linspace(0, 2 * np.pi, 40)
    r_fp  = 40
    for pos in positions:
        fx = pos[0] + r_fp * np.cos(theta)
        fy = pos[1] + r_fp * np.sin(theta)
        fz = np.zeros(40)
        ax.plot(fx, fy, fz, color='#00dd88', linewidth=0.8, alpha=0.55)

    # ── Titles and status bar ──
    n_uav   = len(uavs_d)
    conn    = metrics.get('any_uav_connectivity_pct', 100)
    n_conn  = round(conn / 100 * n_uav)
    surv    = metrics.get('surveyed_pois', 0)
    tot_p   = metrics.get('total_pois', len(poi_list))
    map_pct = metrics.get('mission_completion_pct', 0)

    fig.text(0.325, 0.955,
             f'UAV-X RESILIENT BVLOS SWARM  |  t = {t:.1f} s',
             color='white', fontsize=13, fontweight='bold', ha='center')
    fig.text(0.17, 0.905,
             f'Connected: {n_conn}/{n_uav}  |  Surveyed: {surv}/{tot_p}'
             f'  |  Mapped: {map_pct:.1f}%',
             color='white', fontsize=10, fontweight='bold')

    fig.text(0.325, 0.028,
             'GREEN dashed = survey assignment  |  CYAN = relay/data  |'
             '  GREEN ring = camera footprint',
             color='white', fontsize=8.5, ha='center',
             bbox=dict(boxstyle='round', facecolor='#000d1a',
                       edgecolor='cyan', alpha=0.7, pad=0.4))

    # ── Right HUD panel ──
    panel_ax = fig.add_axes([0.68, 0.10, 0.30, 0.78])
    panel_ax.set_facecolor('#000d1a')
    for spine in panel_ax.spines.values():
        spine.set_edgecolor('cyan')
        spine.set_linewidth(1.4)
    panel_ax.set_xticks([])
    panel_ax.set_yticks([])

    lines  = [
        'UAV-X MISSION STATUS',
        f'Connected: {n_conn}/{n_uav}',
        f'Surveyed:  {surv}/{tot_p}',
        f'Mapped:    {map_pct:.1f}%',
        '',
        f"{'UAV':<7}{'ROLE / TASK':<14}{'BATT':>6}",
    ]
    for u in uavs_d:
        uid  = u['id'] + 1
        role = u.get('role', 'IDLE').upper()[:10]
        batt = u.get('battery', 1.0) * 100
        task = u.get('mode', '--').upper()[:5]
        lines.append(f"UAV-{uid:02d}  {role:<12}{batt:5.1f}%")

    lines += [
        '',
        'PoI colours:',
        '  green  = surveyed',
        '  yellow = pending',
        '  red    = emergency',
    ]

    panel_ax.text(
        0.05, 0.97, '\n'.join(lines),
        transform=panel_ax.transAxes,
        color='white', fontsize=8.5,
        va='top', ha='left',
        family='monospace',
        linespacing=1.55,
    )

    plt.savefig(out_path, dpi=dpi,
                facecolor=BG, edgecolor='none')
    plt.close(fig)


# ─────────────────────────────────────────
#  Main
# ─────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run',      default='logs/current')
    ap.add_argument('--scenario', default='scenarios/earthquake_hard.yaml')
    ap.add_argument('--fps',      type=int, default=6)
    args = ap.parse_args()

    with open(args.scenario) as f:
        config = yaml.safe_load(f)

    W = config['world']['width']
    H = config['world']['height']
    print(f"Generating terrain {W}×{H} …")
    X, Y, Z = make_terrain(W, H, res=100, seed=7)

    with open(os.path.join(args.run, 'replay.jsonl')) as f:
        snaps = [json.loads(l) for l in f]

    os.makedirs('artifacts', exist_ok=True)

    # ── Static mid-mission MATLAB-style overview ──
    mid = min(len(snaps) // 2 + 40, len(snaps) - 1)
    print(f"Rendering MATLAB overview (frame {mid}/{len(snaps)}) …")
    render(snaps[mid], config, X, Y, Z,
           'artifacts/cares_matlab_overview.png', elev=22, azim=230, dpi=160)
    print("  → artifacts/cares_matlab_overview.png")

    # ── Static early-mission Python-style overview ──
    early = min(80, len(snaps) - 1)
    print(f"Rendering Python overview (frame {early}/{len(snaps)}) …")
    render(snaps[early], config, X, Y, Z,
           'artifacts/cares_python_overview.png', elev=28, azim=210, dpi=160)
    print("  → artifacts/cares_python_overview.png")

    # ── Animated GIF (every 8th frame = 8 s per frame at 1-Hz replay) ──
    sub    = snaps[::8]
    frames = []
    print(f"Rendering GIF ({len(sub)} frames) …")
    for i, snap in enumerate(sub):
        tmp = f'/tmp/_cares_frame_{i:04d}.png'
        render(snap, config, X, Y, Z, tmp, elev=22, azim=230 - i * 0.3, dpi=110)
        frames.append(imageio.imread(tmp))
        os.remove(tmp)
        if i % 5 == 0:
            print(f"  {i}/{len(sub)}", flush=True)

    # Normalize all frames to same shape before writing GIF
    from PIL import Image as PILImage
    TARGET_W, TARGET_H = 1650, 935
    norm_frames = []
    for fr in frames:
        img = PILImage.fromarray(fr).resize((TARGET_W, TARGET_H), PILImage.LANCZOS)
        norm_frames.append(np.array(img))
    imageio.mimsave('artifacts/cares_matlab_replay.gif', norm_frames, fps=args.fps, loop=0)
    print("  → artifacts/cares_matlab_replay.gif")
    print("Done.")


if __name__ == '__main__':
    main()
