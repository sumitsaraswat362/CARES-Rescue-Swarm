# CARES: Communication-Aware Resilient Emergency Swarm 🚁📡

[![NIDAR 2.0 - Rescue Swarm](https://img.shields.io/badge/NIDAR_2.0-Rescue_Swarm_Track-orange.svg)](#)
[![iDEX Ready](https://img.shields.io/badge/iDEX-Swarm_Innovation-darkgreen.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Live Dashboard](https://img.shields.io/badge/Vercel-Live_Dashboard-black.svg)](https://uav-x-resilient-swarm.vercel.app)
[![Google Gen AI Elite](https://img.shields.io/badge/Google_GenAI-Top_75_of_196K+-blue.svg)](#)

> **Built for NIDAR 2.0 — "Rescue Swarm" Problem Statement (MeitY × Drone Federation of India)**
> 
> A flash flood has destroyed telecom infrastructure. Roads are blocked. Rescue teams have unverified reports of survivors across a 1 km² affected zone. No GPS relay. No cellular signal. No central command. 
> 
> **CARES deploys a fully autonomous UAV swarm that self-organizes, self-heals, and completes the rescue mission — without any external network.**

---

## 🎯 What CARES Solves

The NIDAR Rescue Swarm challenge requires a swarm of drones to autonomously:
- Locate survivors and deliver medical supplies in a GPS-degraded, comms-denied environment
- Maintain end-to-end mesh connectivity without telecom infrastructure
- Dynamically re-assign tasks when drones fail or run low on battery
- Operate safely with zero collisions and zero geofence violations

**CARES is built specifically for this.** Every algorithm in this codebase addresses one of the above requirements, backed by mathematical proofs and statistical validation.

---

## 📊 Live Interactive Dashboard
**[Launch CARES 3D Dashboard →](https://uav-x-resilient-swarm.vercel.app)**

Experience the swarm in your browser across 4 disaster terrain types:
Alpine, Volcanic, Canyon, and Archipelago (flood simulation).

---

## 🏆 Validated Performance (400-Run Monte Carlo)

| Metric | Result |
|---|---|
| Mission Completion | **100%** |
| Packet Delivery Ratio (PDR) | **97.9%** |
| Median Observation Latency | **700 ms** |
| Geofence Violations | **0** |
| Battery Depletion Violations | **0** |
| Minimum UAV Separation | **>20.0 m** (zero collisions) |
| MBB Relay Handoffs Completed | **8 / 8** |

> All results are cryptographically auditable. Each run is SHA-256 stamped and stored in `logs/audit-matrix/`.

---

## 🧠 Core Algorithms (The Math Behind the Swarm)

### 1. Decentralized Task Allocation — CA-CBBA
CARES uses the **Consensus-Based Bundle Algorithm (CBBA)** — the gold standard in aerospace multi-agent task assignment (used in real NASA and DARPA research). Each UAV independently bids on rescue POIs based on:
- Distance to survivor location
- Remaining battery
- Current network connectivity
- POI priority (medical emergency vs. general survey)

No central server. No single point of failure. The swarm self-organizes.

### 2. Connectivity Maintenance — Control Barrier Functions (CBF)
Using the **Fiedler eigenvalue** of the communication graph as a Control Barrier Function, CARES mathematically guarantees that the swarm mesh network **never partitions**. If a UAV starts drifting out of range, the CBF constraint actively pushes it back before the link drops.

$$h(x) = \lambda_2(L(x)) - \epsilon \geq 0$$

### 3. Collision Avoidance — ORCA
**Optimal Reciprocal Collision Avoidance (ORCA)** computes velocity-obstacle spaces for each UAV pair in real time. Combined with the CBF connectivity constraint, every UAV simultaneously avoids collisions AND maintains mesh links.

### 4. State Estimation — Extended Kalman Filter (EKF)
In GPS-degraded disaster environments, sensor data is noisy. CARES runs an **EKF Digital Twin** for each UAV to maintain accurate position estimates even under sensor failures or spoofing attacks.

### 5. Relay Handoff — Make-Before-Break (MBB)
When a relay drone's battery approaches critical threshold, CARES predicts the failure and dispatches a replacement to the exact network topology cut-vertex **before** the link drops — maintaining continuous GCS connectivity throughout the mission.

---

## 🚀 Quick Start (Reproducibility)

```bash
# 1. Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Run the NIDAR Rescue Swarm scenario (flash flood, telecom-denied)
python3 src/main.py --scenario scenarios/nidar_rescue_swarm.yaml

# 3. View results
cat logs/current/final_report.json
```

---

## 📂 Repository Structure

```
CARES-Rescue-Swarm/
├── src/
│   ├── algorithms/
│   │   ├── ca_cbba.py          # Decentralized task allocation (CBBA)
│   │   ├── orca.py             # Collision avoidance + CBF connectivity
│   │   ├── mbb_handoff.py      # Make-Before-Break relay prediction
│   │   └── consensus.py        # Fault detection & network reconfiguration
│   ├── core/
│   │   ├── uav.py              # UAV physics, battery, state machine
│   │   ├── mission.py          # Mission orchestrator
│   │   ├── ekf.py              # Extended Kalman Filter (GPS-denied nav)
│   │   └── world.py            # Environment, POIs, disaster zones
│   └── comms/
│       ├── mesh_network.py     # Multi-hop relay mesh
│       └── link_model.py       # Log-distance path loss + shadow fading
├── scenarios/
│   ├── nidar_rescue_swarm.yaml # 🆕 NIDAR flash flood scenario
│   ├── techfest_sample.yaml    # Original 1000x1000m, 10 POI scenario
│   └── earthquake_hard.yaml    # Adversarial stress-test scenario
├── dashboard/                  # Next.js live WebSocket visualization
├── tests/                      # Unit + adversarial red-team test suite
├── validation/                 # Monte Carlo run logs (cryptographically stamped)
└── logs/audit-matrix/          # SHA-256 verified evidence matrix
```

---

## 🏅 Creator Credentials

This system was built by **Sumit Saraswat**, selected as part of:
- 🥇 **Google Gen AI Elite Club — Top 75 / 196,000+ developers across 12 APAC countries** (Cohort 2, 2026)
- 🥇 **Meta PyTorch OpenEnv Hackathon — Top 100 Globally** (Multi-Agent RL)

---

## 📄 License
MIT License — open source for research and academic use.
