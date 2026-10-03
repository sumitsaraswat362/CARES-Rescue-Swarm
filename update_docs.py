import re

# 1. REWRITE README.md
new_readme = """# CARES: Communication-Aware Resilient Emergency Swarm 🚁📡
[![Techfest UAV-X](https://img.shields.io/badge/IIT_Bombay-Techfest_UAV--X-blue.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**CARES** is a decentralized, mathematically rigorous UAV swarm framework designed for disaster response operations. 
Developed for the **IIT Bombay Techfest UAV-X Resilient Swarm Challenge (Stage 1)**.

## 🌟 Key Innovations
* **Connectivity-Aware Planning:** Uses Fiedler eigenvalue and Control Barrier Functions (CBF) to strictly prevent network partitions.
* **Make-Before-Break (MBB) Relaying:** Predicts battery depletion and dispatches replacement relays to exact topological cut-vertices *before* the active link drops.
* **Decentralized Task Allocation:** Employs a Communication-Aware Consensus-Based Bundle Algorithm (CA-CBBA) over a strict 100m multi-hop mesh.
* **Interactive 3D Dashboard:** Features a stunning Next.js dashboard built with React Three Fiber for real-time fleet telemetry and 3D terrain visualization.

## 🚀 Quick Start (Reproducibility)
We have made running the official Techfest Sample Scenario (1000x1000m, 10 PoIs, 45-min mission, 100m comm limit) extremely simple and deterministic.

### Prerequisites
* Python 3.12+ (Tested on macOS/Linux)

### 3-Step Execution
```bash
# 1. Setup virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. Install required physics and routing packages
pip install -r requirements.txt

# 3. Run the official Techfest evaluation scenario
python3 src/main.py --scenario scenarios/techfest_sample.yaml
```
*The simulation runs headlessly and automatically outputs trajectory logs, metrics, and JSON replays to the `logs/current/` directory.*

## 📊 Interactive 3D Web Dashboard
To visualize the 3D multi-hop routing, geofence, and topological mesh across different environments (Alpine, Volcanic, Archipelago):
```bash
cd dashboard
npm install
npm run dev
```
*Open `http://localhost:3000` in your browser.*

## ⚙️ System Architecture

<details>
<summary><b>Click to expand System Flow & Logic Architecture</b></summary>

```mermaid
flowchart TB
    SCEN[Scenario Config] --> RUN[Mission Manager]
    RUN --> WRLD[World Environment]
    WRLD --> MESH[MeshNetwork: 100m Path Loss]
    MESH --> EKF[ORCA+CBF: Adjacency Estimation]
    EKF --> CBBA[CA-CBBA: Gossip Routing]
    CBBA --> MBB[MBB Handoff Manager]
    MBB --> DYN[UAV Dynamics]
    DYN --> LOG[Telemetry Logging]
```
</details>

## 🖼️ Proof of Concept Visuals

### Simulation Snapshot
<img src="artifacts/cares_python_overview.png" width="800">

### Network Resilience Metrics
<img src="artifacts/cares_metrics.png" width="800">

## 📂 Repository Map
- `src/core/`: Mission manager, UAV state machine, World environment.
- `src/algorithms/`: CA-CBBA allocation, ORCA collision avoidance, EKF/CBF connectivity.
- `src/comms/`: Mesh network simulation and link quality models.
- `dashboard/`: Next.js Web3D UI for mission playback and telemetry visualization.
- `scenarios/`: YAML configuration files defining constraints and environments.

## 👥 Team
* **Sumit Saraswat** (Team Leader)
* **Tanmay Kaushal**
"""

with open("README.md", "w") as f:
    f.write(new_readme)

# 2. REWRITE PROPOSAL SECTION 11
with open("docs/Techfest_Proposal_Draft.md", "r") as f:
    proposal = f.read()

old_repro = """## 11. Reproducibility

### 11.1 Source code
**Repository:** https://github.com/sumitsaraswat362/UAV-X-Resilient-Swarm
**Structure:** Modular architecture separating src/core/ (logic), src/algorithms/ (CBF, CA-CBBA), src/comms/, and scripts/ (cinematic visualization). Licensed under MIT.

### 11.2 Installation & run instructions
1. python3 -m venv .venv && source .venv/bin/activate
2. pip install -r requirements.txt
3. python3 src/main.py --scenario scenarios/techfest_sample.yaml

### 11.3 Demonstration video
[ Link to be provided upon final recording ]
*Demonstrates cinematic 3D visualization, dynamic re-tasking, and autonomous MBB failure recovery.*"""

new_repro = """## 11. Reproducibility & Transparency

### 11.1 Source code availability
**GitHub Repository:** https://github.com/sumitsaraswat362/UAV-X-Resilient-Swarm
Our codebase is open-source (MIT License) and strictly organized to separate core mission logic (`src/core`), decision-making algorithms (`src/algorithms`), and topological communications (`src/comms`). It also features a fully interactive Next.js 3D web dashboard for telemetry visualization (`dashboard/`).

### 11.2 Installation & run instructions
We have ensured that recreating the official Techfest validation results requires zero complex dependencies (only standard Python packages).
From the root of the repository, execute the following three commands:
```bash
1. python3 -m venv .venv && source .venv/bin/activate
2. pip install -r requirements.txt
3. python3 src/main.py --scenario scenarios/techfest_sample.yaml
```
This triggers the headless, deterministic execution of the mission. Final empirical metrics are logged directly to `logs/current/final_report.json`.

### 11.3 Interactive 3D visualization
To launch the Web3D Interactive Dashboard and visually inspect the topological mesh, multi-hop routing, and terrain interactions:
```bash
1. cd dashboard
2. npm install
3. npm run dev
```
Navigate to `http://localhost:3000` to interact with the mission replay.

### 11.4 Demonstration video
[ Link to be provided upon final recording ]
*Demonstrates 3D visualization, dynamic CA-CBBA re-tasking, and autonomous MBB failure recovery.*"""

proposal = proposal.replace(old_repro, new_repro)

with open("docs/Techfest_Proposal_Draft.md", "w") as f:
    f.write(proposal)
