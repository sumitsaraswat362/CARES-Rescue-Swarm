#!/usr/bin/env python3
"""CARES — FastAPI WebSocket Server v2
Simulation bridge between the engine and 3D web frontend."""

import asyncio
import anyio
import json
import os
import sys
import random
import logging
import glob
import traceback
import uuid
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
import numpy as np

# Ensure imports work from project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from src.core.mission import MissionManager
from src.algorithms.ca_cbba import CACBBA
from src.algorithms.orca import ORCAManager
from src.algorithms.consensus import FaultDetector
from src.algorithms.mbb_handoff import MBBHandoffManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("CARES")

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(advance_simulation())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

app = FastAPI(title="CARES Swarm Command Server", lifespan=lifespan)

# ── Config ───────────────────────────────────────────────────────────────────
SCENARIO = os.environ.get("CARES_SCENARIO",
                          os.path.join(PROJECT_ROOT, "scenarios", "earthquake_basic.yaml"))
CONFIG   = os.environ.get("CARES_CONFIG",
                          os.path.join(PROJECT_ROOT, "config", "swarm_config.yaml"))

# ── Simulation State ─────────────────────────────────────────────────────────

from src.algorithms.path_planner import PathPlanner
from src.comms.link_model import LinkModel
from src.comms.mesh_network import MeshNetwork

class SimState:
    """Holds the global simulation state for the server."""
    def __init__(self):
        self.mission = None
        self.allocator = None
        self.orca = None
        self.fault_detector = None
        self.path_planner = None
        self.mesh = None
        self.mbb_manager = None
        self.speed = 5.0
        self.last_metrics = {}
        self.lock = asyncio.Lock()
        self.generation = 0
        self.clients = 0
        self.command_receipts = OrderedDict()
        self.command_events = deque(maxlen=20)

    def init(self, scenario=None, config=None):
        scenario = scenario or SCENARIO
        config = config or CONFIG
        self.scenario, self.config = scenario, config
        from src.resilience.runtime import Runtime
        self.runtime = Runtime(scenario, config, int(os.environ.get('CARES_SEED',42)))
        self.mission = self.runtime.mission
        self.mesh = self.runtime.transport
        self.path_planner = self.runtime.planner
        self.speed = 5.0
        self.last_metrics = {}
        self._explain_cursors = {}
        self.generation += 1
        logger.info(f"Simulation initialized (gen {self.generation}): {self.mission.world.name}")

sim = SimState()

# ── Serialization ────────────────────────────────────────────────────────────

def _float(v):
    """Safe float conversion for numpy types."""
    if v is None:
        return None
    return float(v)

def serialize_state(sim: SimState) -> dict:
    """Convert the full simulation state to a JSON-serializable dict."""
    m = sim.mission
    if m is None:
        return {"type": "error", "message": "Simulation not initialized"}

    # UAVs
    uavs = []
    for u in m.uavs:
        uavs.append({
            "id": u.id,
            "label": u.label,
            "x": _float(u.pos[0]),
            "y": _float(u.pos[1]),
            "altitude": _float(u.altitude),
            "vx": _float(u.vel[0]),
            "vy": _float(u.vel[1]),
            "heading": _float(u.heading),
            "state": u.state.value,
            "role": u.role.value,
            "battery": _float(u.battery.level),
            "battery_warning": bool(u.battery.is_warning),
            "battery_critical": bool(u.battery.is_critical),
            "assigned_task": u.assigned_task_id,
            "target_x": _float(u.target_pos[0]) if u.target_pos is not None else None,
            "target_y": _float(u.target_pos[1]) if u.target_pos is not None else None,
            "tasks_done": u.tasks_completed_count if hasattr(u, 'tasks_completed_count') else len(getattr(u, 'tasks_completed', [])),
        })

    # PoIs
    pois = []
    for p in m.world.pois:
        pois.append({
            "id": p.id, "x": _float(p.x), "y": _float(p.y),
            "priority": int(p.priority), "label": p.label,
            "surveyed": bool(p.surveyed),
        })

    # Obstacles
    obstacles = [{"x": _float(o.x), "y": _float(o.y), "radius": _float(o.radius), "label": o.label}
                 for o in m.world.obstacles]

    # Recharge stations
    recharge = [{"x": _float(r.x), "y": _float(r.y), "label": r.label}
                for r in m.world.recharge_stations]

    # Physical links are an evaluator overlay, not inputs to agent policy.
    links = [[a,b] for (a,b),q in sim.runtime.transport.edges.items() if a<b and q>0]
    report = sim.runtime.report()
    metrics = {**report, "mission_completion":round(report['delivered_completion_pct'],1),
               "priority_completion":round(report['priority_weighted_pct'],1),
               "connectivity":round(report['all_uav_connectivity_pct'],1),
               "active_uavs":sum(u.state.value!='failed' for u in m.uavs),
               "pdr":round(report['hop_pdr_pct'],1) if report['hop_pdr_pct'] is not None else None}
    for item in uavs:
        a=sim.runtime.agents[item['id']]
        item.update(route=list(a.route), pending=len(a.pending), custody=len(a.custody),
                    radio_failed=bool(getattr(a.uav,'radio_failed',False)),
                    oldest_pending_age_s=max((m.sim_time-d['acquired_at'] for d in a.pending.values()),default=0), mode=a.mode,
                    return_margin_wh=a.return_margin)

    # Events (last 20 mission-level events)
    events = m.mission_log[-20:] if m.mission_log else []

    # Return a snapshot so one viewer cannot consume another viewer's events.
    explain_events = []
    # High-value event keywords that judges should see
    EXPLAIN_KEYWORDS = (
        "FAILURE", "ASSIGNED_SCOUT", "ASSIGNED_RELAY", "BATTERY_CRITICAL",
        "NPNT_BLOCK", "REPLAN", "SENSOR", "SPOOFED_GPS", "RECHARGE_COMPLETE",
        "SENT_TO_RECHARGE"
    )
    for u in m.uavs:
        for entry in u.log[-50:]:
            if any(kw in entry.get('event', '') for kw in EXPLAIN_KEYWORDS):
                explain_events.append(entry)
    # Cap at 10 newest per tick to avoid flooding
    explain_events = sorted(explain_events, key=lambda e: e['time'])[-10:]

    return {
        "type": "state",
        "sim_time": round(m.sim_time, 1),
        "duration": m.world.duration_s,
        "running": m.running,
        "paused": m.paused,
        "speed": sim.speed,
        "generation": sim.generation,
        "command_receipts": list(sim.command_events),
        "uavs": uavs,
        "pois": pois,
        "obstacles": obstacles,
        "recharge_stations": recharge,
        "gcs": {"x": _float(m.world.gcs_pos[0]), "y": _float(m.world.gcs_pos[1]),
                "label": m.gcs.label},
        "world": {"width": _float(m.world.width), "height": _float(m.world.height),
                  "name": m.world.name},
        "links": links,
        "metrics": metrics,
        "evidence": sim.runtime.evaluator.events[-20:],
        "events": events,
        "explain": explain_events,
    }

def handle_command(sim: SimState, cmd: dict):
    """A bounded idempotency window shared by every viewer, including resets."""
    def publish(receipt):
        sim.command_events.append(receipt)
        return receipt
    if not isinstance(cmd, dict):
        cmd = {}
    cid = cmd.get('command_id') or str(uuid.uuid4())
    if not isinstance(cid, str) or len(cid) > 128:
        cid = str(uuid.uuid4())
        cmd = {}  # Reject malformed IDs rather than executing without protection.
    fingerprint = json.dumps(cmd, sort_keys=True, separators=(',', ':'))
    if cid in sim.command_receipts:
        old_fingerprint, receipt = sim.command_receipts[cid]
        if old_fingerprint == fingerprint:
            return publish(receipt)
        return publish({**receipt, 'status': 'rejected', 'reason': 'command_id reused with different content'})
    action = cmd.get('action')
    allowed = {'pause','speed_up','speed_down','kill_uav','spoof_gps','trigger_outage',
               'inject_poi','reset','inject_failure'}
    reason = None
    if sim.mission is None:
        reason = 'mission not initialized'
    elif action not in allowed:
        reason = 'unknown action'
    elif cmd.get('generation', sim.generation) != sim.generation:
        reason = 'stale generation'
    elif action in ('kill_uav','spoof_gps'):
        uid = cmd.get('uav_id',0)
        target = next((u for u in sim.mission.uavs if type(uid) is int and u.id == uid), None)
        if target is None or target.state.name == 'FAILED':
            reason = 'UAV missing or already failed'
    before_generation = sim.generation
    before_time = sim.mission.sim_time if sim.mission else 0
    if reason is None:
        _apply_command(sim,cmd)
    receipt = {'command_id': cid, 'action': action, 'status': 'rejected' if reason else 'accepted',
               'reason': reason, 'generation': sim.generation, 'sim_time': before_time,
               'request_generation': before_generation}
    sim.command_receipts[cid] = (fingerprint, receipt)
    while len(sim.command_receipts) > 256:
        sim.command_receipts.popitem(last=False)
    return publish(receipt)


def _apply_command(sim: SimState, cmd: dict):
    """Process a control command from the frontend."""
    action = cmd.get("action", "")
    m = sim.mission
    if m is None:
        return

    sim.runtime.evaluator.record({'event': 'dashboard_command', 'time': m.sim_time,
                                  'action': action, 'uav_id': cmd.get('uav_id')})

    if action == "pause":
        m.paused = not m.paused
        logger.info(f"{'⏸ Paused' if m.paused else '▶ Resumed'}")

    elif action == "speed_up":
        sim.speed = min(50.0, sim.speed + 1.0)

    elif action == "speed_down":
        sim.speed = max(0.5, sim.speed - 1.0)

    elif action == "kill_uav":
        uav_id = cmd.get("uav_id", 0)
        uav = next((u for u in m.uavs if u.id == uav_id), None)
        if uav and uav.state.name != "FAILED":
            uav.inject_failure("Motor Failure (User Injected)", m.sim_time)
            m.needs_reallocation = True
            logger.info(f"💥 Injected kill on {uav.label}")

    elif action == "spoof_gps":
        uav_id = cmd.get("uav_id", 0)
        uav = next((u for u in m.uavs if u.id == uav_id), None)
        if uav and uav.state.name != "FAILED":
            # Just push the EKF variance up directly for the demo
            uav.estimator.P = np.eye(4) * 1000.0
            uav._log_event(m.sim_time, f"SPOOFED_GPS — variance inflated")
            logger.info(f"📡 Spoofed GPS on {uav.label}")

    elif action == "trigger_outage":
        sim.runtime.transport.outage_until = m.sim_time + 5.0

    elif action == "inject_poi":
        new_poi = {
            "id": max([899] + list(sim.runtime.tasks) + [p.id for p in m.world.hidden_pois]) + 1,
            "x": random.uniform(200, m.world.width - 200),
            "y": random.uniform(200, m.world.height - 200),
            "priority": random.randint(3, 5),
            "label": f"Emergency #{len(m.world.pois) + 1}",
        }
        m.world.add_poi(new_poi)
        from src.resilience.agent import Task
        sim.runtime.tasks[new_poi["id"]] = Task(new_poi["id"],new_poi["x"],new_poi["y"],new_poi["priority"])
        m.needs_reallocation = True
        logger.info(f"📍 Injected PoI '{new_poi['label']}' at ({new_poi['x']:.0f}, {new_poi['y']:.0f})")

    elif action == "reset":
        sim.init(sim.scenario, sim.config)

    elif action == "inject_failure":
        live = next((u for u in m.uavs if u.state.name != "FAILED"), None)
        if live:
            live.inject_failure("User injected failure", m.sim_time)


async def advance_simulation():
    """One clock for all viewers; connections never reset or accelerate a mission."""
    while True:
        async with sim.lock:
            m = sim.mission
            if sim.clients and m and m.running and not m.paused:
                sim.last_metrics = sim.runtime.step()
                if not m.running:
                    sim.runtime.save()
            delay = m.dt / sim.speed if m and m.running else 0.1
        await asyncio.sleep(delay)

# ── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")

    async with sim.lock:
        if sim.mission is None:
            sim.init()
        sim.clients += 1

    my_generation = sim.generation

    async def sim_loop():
        """Run simulation ticks and push state to client."""
        nonlocal my_generation
        try:
            while True:
                async with sim.lock:
                    m = sim.mission
                    if m is None:
                        await asyncio.sleep(0.5)
                        continue

                    # Detect if a reset happened
                    if sim.generation != my_generation:
                        my_generation = sim.generation

                    # Always send state (even when paused/ended)
                    state = serialize_state(sim)
                    if not m.running:
                        state["type"] = "end"
                        try:
                            state["report"] = sim.runtime.report()
                        except Exception:
                            pass

                await ws.send_json(state)

                # Sleep based on sim speed
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"sim_loop crashed: {e}\n{traceback.format_exc()}")

    async def recv_loop():
        """Listen for commands from the client."""
        try:
            while True:
                data = await ws.receive_json()
                async with sim.lock:
                    handle_command(sim, data)
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.warning(f"recv error: {e}")

    # Structured cancellation keeps disconnects from orphaning a sender or viewer count.
    try:
        async with anyio.create_task_group() as group:
            async def serve(loop):
                try:
                    await loop()
                finally:
                    group.cancel_scope.cancel()
            group.start_soon(serve, sim_loop)
            group.start_soon(serve, recv_loop)
    finally:
        with anyio.CancelScope(shield=True):
            async with sim.lock:
                sim.clients -= 1

# ── REST ─────────────────────────────────────────────────────────────────────

@app.get("/api/scenarios")
async def list_scenarios():
    files = glob.glob(os.path.join(PROJECT_ROOT, "scenarios", "*.yaml"))
    return [os.path.basename(f) for f in files]

@app.get("/api/status")
async def get_status():
    if sim.mission:
        return {
            "running": sim.mission.running,
            "paused": sim.mission.paused,
            "sim_time": sim.mission.sim_time,
            "generation": sim.generation,
        }
    return {"running": False}

# ── Static files ─────────────────────────────────────────────────────────────

web_dir = os.path.join(PROJECT_ROOT, "web")
if os.path.isdir(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
