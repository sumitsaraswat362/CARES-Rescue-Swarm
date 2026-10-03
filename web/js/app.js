/**
 * CARES — 3D Swarm Command Center
 * Three.js visualization with post-processing, particle effects, and real-time WebSocket state.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// ────────────────────────────────────────────────────────────────────────────
// Constants
// ────────────────────────────────────────────────────────────────────────────

const SCALE = 0.1; // 1 sim meter = 0.1 three.js unit
const FLIGHT_HEIGHT = 4.0;
const TRAIL_LENGTH = 50;

const STATE_COLORS = {
  idle:             0x667788,
  takeoff:          0x00ddff,
  scout:            0x00ddff,
  relay:            0xff9900,
  return_to_launch: 0xffdd00,
  recharge:         0x00ff66,
  failed:           0xff0033,
};

// ────────────────────────────────────────────────────────────────────────────
// Scene Setup
// ────────────────────────────────────────────────────────────────────────────

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x060a12, 0.003);

const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 2000);
camera.position.set(100, 100, 150);
camera.lookAt(100, 0, 75);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.3;
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.prepend(renderer.domElement);

const labelRenderer = new CSS2DRenderer();
labelRenderer.setSize(window.innerWidth, window.innerHeight);
labelRenderer.domElement.style.position = 'absolute';
labelRenderer.domElement.style.top = '0';
labelRenderer.domElement.style.pointerEvents = 'none';
document.body.appendChild(labelRenderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.minDistance = 10;
controls.maxDistance = 500;
controls.maxPolarAngle = Math.PI / 2.05;
controls.target.set(100, 0, 75);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloomPass = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight),
  0.7, 0.5, 0.85
);
composer.addPass(bloomPass);

// Raycaster for hover interactions
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  labelRenderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
});

// ────────────────────────────────────────────────────────────────────────────
// Lighting & Environment
// ────────────────────────────────────────────────────────────────────────────

scene.add(new THREE.AmbientLight(0x112244, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.5);
dirLight.position.set(100, 200, 50);
scene.add(dirLight);
scene.add(new THREE.HemisphereLight(0x0a1a3a, 0x060a12, 0.5));

function createStars() {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(4000 * 3);
  for (let i = 0; i < 4000; i++) {
    pos[i*3]   = (Math.random() - 0.5) * 1000;
    pos[i*3+1] = Math.random() * 300 + 50;
    pos[i*3+2] = (Math.random() - 0.5) * 1000;
  }
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({ color: 0x88aaff, size: 0.15, transparent: true, opacity: 0.6 });
  scene.add(new THREE.Points(geo, mat));
}
createStars();

function createGround(w, h) {
  const gw = w * SCALE;
  const gh = h * SCALE;
  
  // Floor
  const groundGeo = new THREE.PlaneGeometry(gw + 50, gh + 50);
  const groundMat = new THREE.MeshStandardMaterial({
    color: 0x040810, roughness: 0.8, metalness: 0.2
  });
  const ground = new THREE.Mesh(groundGeo, groundMat);
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(gw/2, -0.1, gh/2);
  scene.add(ground);

  // Grid
  const grid = new THREE.GridHelper(Math.max(gw, gh) + 40, 50, 0x00ffc8, 0x112233);
  grid.material.opacity = 0.15;
  grid.material.transparent = true;
  grid.position.set(gw/2, 0, gh/2);
  scene.add(grid);
  
  // Borders
  const borderGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(gw, 0.2, gh));
  const borderMat = new THREE.LineBasicMaterial({ color: 0x00ffc8, transparent: true, opacity: 0.2 });
  const border = new THREE.LineSegments(borderGeo, borderMat);
  border.position.set(gw/2, 0.1, gh/2);
  scene.add(border);
}

// ────────────────────────────────────────────────────────────────────────────
// 3D Object Creators
// ────────────────────────────────────────────────────────────────────────────

function createUAVModel() {
  const group = new THREE.Group();

  // Core body
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.8, 0.3, 0.8),
    new THREE.MeshStandardMaterial({ color: 0x223344, metalness: 0.6, roughness: 0.2 })
  );
  group.add(body);

  // Rotors
  const rotorMat = new THREE.MeshStandardMaterial({ color: 0x00ffcc, emissive: 0x00ffcc, emissiveIntensity: 0.8 });
  const rotors = [];
  const positions = [[0.6, 0.6], [0.6, -0.6], [-0.6, 0.6], [-0.6, -0.6]];
  
  positions.forEach(([x, z]) => {
    // Arm
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, Math.hypot(x,z), 8), body.material);
    arm.rotation.x = Math.PI/2;
    arm.rotation.z = Math.atan2(z, x);
    arm.position.set(x/2, 0, z/2);
    group.add(arm);

    // Motor housing
    const motor = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.2, 12), body.material);
    motor.position.set(x, 0.1, z);
    group.add(motor);

    // Blade ring
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.25, 0.3, 16), rotorMat.clone());
    ring.rotation.x = -Math.PI/2;
    ring.position.set(x, 0.22, z);
    group.add(ring);
    rotors.push(ring);
    
    // Blur disc
    const disc = new THREE.Mesh(
      new THREE.CircleGeometry(0.28, 12),
      new THREE.MeshBasicMaterial({ color: 0x00ffcc, transparent: true, opacity: 0.15, side: THREE.DoubleSide })
    );
    disc.rotation.x = -Math.PI/2;
    disc.position.set(x, 0.24, z);
    group.add(disc);
    rotors.push(disc);
  });

  // Light & Camera Cone
  const light = new THREE.PointLight(0x00ddff, 1.0, 10);
  light.position.y = -0.2;
  group.add(light);
  
  const cone = new THREE.Mesh(
    new THREE.ConeGeometry(0.1, 0.4, 8),
    new THREE.MeshStandardMaterial({ color: 0x111111 })
  );
  cone.position.y = -0.3;
  group.add(cone);

  group.userData = { rotors, light, rotorMats: rotors.map(r => r.material) };
  return group;
}

function createLabel(text, cssClass) {
  const div = document.createElement('div');
  div.className = cssClass;
  div.textContent = text;
  div.style.cssText = `
    font-family: 'Orbitron', monospace; font-size: 9px; font-weight: 700;
    color: #fff; text-shadow: 0 0 4px rgba(0,0,0,0.8);
    pointer-events: none; margin-top: -15px;
  `;
  const obj = new CSS2DObject(div);
  obj.position.set(0, 1.5, 0);
  return { obj, div };
}

// ────────────────────────────────────────────────────────────────────────────
// State Management
// ────────────────────────────────────────────────────────────────────────────

let uavObjects = {};      
let poiObjects = {};       
let obstacleObjects = {};  
let linkLines = [];
let gcsObject = null;
let rechargeObjects = [];
let worldSize = { w: 2000, h: 1500 };

let currentGeneration = -1;
let followUAV = null;
let selectedUAV = null;
const clock = new THREE.Clock();

function clearScene() {
  Object.values(uavObjects).forEach(e => {
    scene.remove(e.group); scene.remove(e.trail); scene.remove(e.targetLine);
    if (e.labelObj && e.labelObj.element) e.labelObj.element.remove();
  });
  Object.values(poiObjects).forEach(e => {
    scene.remove(e.group);
    if (e.labelObj && e.labelObj.element) e.labelObj.element.remove();
  });
  Object.values(obstacleObjects).forEach(m => {
    scene.remove(m.group);
    if (m.labelObj && m.labelObj.element) m.labelObj.element.remove();
  });
  rechargeObjects.forEach(o => {
    scene.remove(o.group);
    if (o.labelObj && o.labelObj.element) o.labelObj.element.remove();
  });
  if (gcsObject) {
    scene.remove(gcsObject.group);
    if (gcsObject.labelObj && gcsObject.labelObj.element) gcsObject.labelObj.element.remove();
  }
  linkLines.forEach(l => scene.remove(l));
  
  uavObjects = {}; poiObjects = {}; obstacleObjects = {};
  linkLines = []; gcsObject = null; rechargeObjects = [];
  followUAV = null; selectedUAV = null;
}

// ────────────────────────────────────────────────────────────────────────────
// Builders
// ────────────────────────────────────────────────────────────────────────────

function getOrCreateUAV(uavData) {
  if (uavObjects[uavData.id]) return uavObjects[uavData.id];

  const group = createUAVModel();
  scene.add(group);

  const trail = new THREE.Line(
    new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(new Float32Array(TRAIL_LENGTH*3), 3)),
    new THREE.LineBasicMaterial({ color: 0x00ddff, transparent: true, opacity: 0.5 })
  );
  scene.add(trail);

  const targetLine = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
    new THREE.LineDashedMaterial({ color: 0x00ddff, dashSize: 0.5, gapSize: 0.3, transparent: true, opacity: 0.4 })
  );
  targetLine.computeLineDistances();
  targetLine.visible = false;
  scene.add(targetLine);

  const { obj: labelObj, div: labelDiv } = createLabel(uavData.label, 'uav-label');
  group.add(labelObj);

  // Interaction Hitbox
  const hitbox = new THREE.Mesh(new THREE.SphereGeometry(1.5), new THREE.MeshBasicMaterial({visible:false}));
  hitbox.userData = { type: 'uav', id: uavData.id };
  group.add(hitbox);

  const entry = { group, trail, targetLine, labelObj, labelDiv, positions: [], hitbox };
  uavObjects[uavData.id] = entry;
  return entry;
}

function buildStaticWorld(state) {
  if (gcsObject) return; // Already built
  
  worldSize = { w: state.world.width, h: state.world.height };
  createGround(worldSize.w, worldSize.h);

  // GCS
  const gcsGrp = new THREE.Group();
  const base = new THREE.Mesh(new THREE.BoxGeometry(3, 0.5, 3), new THREE.MeshStandardMaterial({ color: 0x334455 }));
  gcsGrp.add(base);
  
  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(1.2, 16, 16, 0, Math.PI*2, 0, Math.PI/2),
    new THREE.MeshStandardMaterial({ color: 0x00ffc8, transparent: true, opacity: 0.2, wireframe: true })
  );
  dome.position.y = 0.25;
  gcsGrp.add(dome);

  // Range ring
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(49, 50, 64),
    new THREE.MeshBasicMaterial({ color: 0x00ffc8, transparent: true, opacity: 0.1, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI/2;
  gcsGrp.add(ring);

  const { obj: gLbl, div: gDiv } = createLabel(state.gcs.label, 'gcs-label');
  gLbl.position.y = 3;
  gcsGrp.add(gLbl);
  gcsGrp.position.set(state.gcs.x * SCALE, 0, state.gcs.y * SCALE);
  scene.add(gcsGrp);
  gcsObject = { group: gcsGrp, labelObj: gLbl };

  // Recharge Stations
  (state.recharge_stations || []).forEach((rs, i) => {
    const rGrp = new THREE.Group();
    rGrp.add(new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.2, 2.5), new THREE.MeshStandardMaterial({color: 0x223322})));
    rGrp.add(new THREE.PointLight(0x00ff66, 0.8, 5));
    const { obj: rLbl } = createLabel(rs.label, 'rs-label');
    rGrp.add(rLbl);
    rGrp.position.set(rs.x * SCALE, 0, rs.y * SCALE);
    scene.add(rGrp);
    rechargeObjects.push({ group: rGrp, labelObj: rLbl });
  });

  // Obstacles
  (state.obstacles || []).forEach((obs, i) => {
    const r = obs.radius * SCALE;
    const oGrp = new THREE.Group();
    oGrp.add(new THREE.Mesh(
      new THREE.SphereGeometry(r, 24, 16, 0, Math.PI*2, 0, Math.PI/2),
      new THREE.MeshStandardMaterial({ color: 0xff2222, transparent: true, opacity: 0.15, side: THREE.DoubleSide })
    ));
    const { obj: oLbl } = createLabel(obs.label, 'obs-label');
    oLbl.position.y = r + 1;
    oGrp.add(oLbl);
    oGrp.position.set(obs.x * SCALE, 0, obs.y * SCALE);
    scene.add(oGrp);
    obstacleObjects[i] = { group: oGrp, labelObj: oLbl };
  });
}

function getOrCreatePOI(poiData) {
  if (poiObjects[poiData.id]) return poiObjects[poiData.id];

  const group = new THREE.Group();
  const pillar = new THREE.Mesh(
    new THREE.CylinderGeometry(0.15, 0.3, 3, 8),
    new THREE.MeshStandardMaterial({ color: 0xff5500, emissive: 0xff3300, emissiveIntensity: 0.5, transparent: true, opacity: 0.8 })
  );
  pillar.position.y = 1.5;
  group.add(pillar);

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(1.5, 1.6 + poiData.priority*0.2, 32),
    new THREE.MeshBasicMaterial({ color: 0xff8800, transparent: true, opacity: 0.2, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI/2;
  ring.position.y = 0.1;
  group.add(ring);

  const light = new THREE.PointLight(0xff5500, 1.0, 12);
  light.position.y = 3;
  group.add(light);

  const { obj: labelObj, div: labelDiv } = createLabel(`${poiData.label} [P${poiData.priority}]`, 'poi-label');
  labelObj.position.y = 4.5;
  group.add(labelObj);

  group.position.set(poiData.x * SCALE, 0, poiData.y * SCALE);
  scene.add(group);

  group.userData = { pillarMat: pillar.material, ringMat: ring.material, ring, light };
  const entry = { group, labelObj, labelDiv };
  poiObjects[poiData.id] = entry;
  return entry;
}

// ────────────────────────────────────────────────────────────────────────────
// Main Update Loop
// ────────────────────────────────────────────────────────────────────────────

let frameCount = 0;

function updateScene(state) {
  if (!state || state.type === 'error') return;
  const receipt = state.command_receipts?.at(-1);
  if (receipt) document.getElementById('command-status').textContent = `${receipt.action}: ${receipt.status}${receipt.reason ? ' — ' + receipt.reason : ''} (generation ${receipt.generation}, ${receipt.sim_time.toFixed(1)} s)`;
  
  // Handle server resets cleanly
  if (currentGeneration !== state.generation) {
    if (currentGeneration !== -1) {
      console.log("Server generation changed. Resetting scene.");
      clearScene();
    }
    currentGeneration = state.generation;
  }

  frameCount++;
  const t = clock.getElapsedTime();

  buildStaticWorld(state);

  // ── UAVs ──
  let fleetHTML = '';
  (state.uavs || []).forEach(u => {
    const entry = getOrCreateUAV(u);
    const { group, trail, targetLine, labelDiv } = entry;

    const tx = u.x * SCALE;
    const tz = u.y * SCALE;
    const ty = u.altitude * SCALE;

    group.position.x += (tx - group.position.x) * 0.15;
    group.position.y += (ty - group.position.y) * 0.15;
    group.position.z += (tz - group.position.z) * 0.15;

    if (Math.abs(u.vx) > 0.1 || Math.abs(u.vy) > 0.1) {
      group.rotation.y += (Math.atan2(u.vx, u.vy) - group.rotation.y) * 0.1;
    }

    if (u.state === 'failed') {
      group.rotation.z += (0.6 - group.rotation.z) * 0.05;
      group.rotation.x += (0.4 - group.rotation.x) * 0.05;
    } else {
      group.rotation.z *= 0.9;
      group.rotation.x *= 0.9;
    }

    const col = STATE_COLORS[u.state] || 0x667788;
    group.userData.light.color.setHex(col);
    group.userData.light.intensity = u.state === 'failed' ? 0 : 0.8;
    
    group.userData.rotorMats.forEach(m => {
      m.color.setHex(col); m.emissive.setHex(col);
      m.emissiveIntensity = u.state === 'failed' ? 0 : 0.7;
    });

    if (u.state !== 'failed') {
      group.userData.rotors.forEach((r, i) => r.rotation.z += (i%2===0 ? 0.4 : -0.4));
    }

    // Trail
    entry.positions.push(new THREE.Vector3(group.position.x, group.position.y, group.position.z));
    if (entry.positions.length > TRAIL_LENGTH) entry.positions.shift();
    if (entry.positions.length > 1) {
      trail.geometry.dispose();
      trail.geometry = new THREE.BufferGeometry().setFromPoints(entry.positions);
      trail.material.color.setHex(col);
    }

    // Target Line
    if (u.target_x !== null && u.state !== 'idle' && u.state !== 'failed') {
      targetLine.visible = true;
      targetLine.geometry.dispose();
      targetLine.geometry = new THREE.BufferGeometry().setFromPoints([
        group.position.clone(), new THREE.Vector3(u.target_x*SCALE, 0.5, u.target_y*SCALE)
      ]);
      targetLine.computeLineDistances();
      targetLine.material.color.setHex(col);
    } else {
      targetLine.visible = false;
    }

    labelDiv.style.color = '#' + col.toString(16).padStart(6, '0');

    // Fleet list HTML
    const isSel = selectedUAV === u.id ? 'selected' : '';
    fleetHTML += `
      <div class="fleet-item ${isSel}" data-id="${u.id}">
        <div class="fleet-dot ${u.state}"></div>
        <div class="fleet-name">${u.label}</div>
        <div class="fleet-state">${u.role.replace('_',' ')}</div>
        <div class="fleet-batt" style="color:${u.battery_critical?'#ff3355':u.battery_warning?'#ffaa00':'#00ff88'}">
          ${(u.battery*100).toFixed(0)}%
        </div>
      </div>
    `;
  });
  
  const fleetList = document.getElementById('fleet-list');
  if (fleetList.innerHTML !== fleetHTML) {
    fleetList.innerHTML = fleetHTML;
    document.querySelectorAll('.fleet-item').forEach(el => {
      el.addEventListener('click', () => {
        const id = parseInt(el.dataset.id);
        followUAV = id;
        selectedUAV = id;
      });
    });
  }

  // ── PoIs ──
  (state.pois || []).forEach(p => {
    const { group, labelDiv } = getOrCreatePOI(p);
    const ud = group.userData;
    if (p.surveyed) {
      ud.pillarMat.color.setHex(0x00cc66); ud.pillarMat.emissive.setHex(0x008844);
      ud.ringMat.color.setHex(0x00cc66); ud.ringMat.opacity = 0.1;
      ud.light.color.setHex(0x00cc66); ud.light.intensity = 0.3;
      labelDiv.style.color = '#00cc66';
      labelDiv.textContent = `${p.label} [CLEARED]`;
    } else {
      const pulse = Math.sin(t * 4 + p.id) * 0.5 + 0.5;
      ud.ring.scale.setScalar(1 + pulse * 0.4);
      ud.ringMat.opacity = 0.1 + pulse * 0.3;
    }
  });

  // ── Links ──
  if (frameCount % 4 === 0) {
    linkLines.forEach(l => scene.remove(l));
    linkLines = [];
    const umap = {}; (state.uavs || []).forEach(u => umap[u.id] = u);
    (state.links || []).forEach(([a, b]) => {
      const pA = a === -1 ? new THREE.Vector3(state.gcs.x*SCALE, 2, state.gcs.y*SCALE) : umap[a] ? new THREE.Vector3(umap[a].x*SCALE, umap[a].altitude*SCALE, umap[a].y*SCALE) : null;
      const pB = b === -1 ? new THREE.Vector3(state.gcs.x*SCALE, 2, state.gcs.y*SCALE) : umap[b] ? new THREE.Vector3(umap[b].x*SCALE, umap[b].altitude*SCALE, umap[b].y*SCALE) : null;
      if (!pA || !pB) return;
      const dist = pA.distanceTo(pB);
      const col = dist < 15 ? 0x00ff88 : dist < 35 ? 0xffaa00 : 0xff3344;
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([pA, pB]),
        new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.35 })
      );
      scene.add(line);
      linkLines.push(line);
    });
  }

  // ── Camera ──
  if (followUAV !== null && uavObjects[followUAV]) {
    const target = uavObjects[followUAV].group.position;
    controls.target.lerp(new THREE.Vector3(target.x, 0, target.z), 0.1);
  }

  updateHUD(state);
  updateMinimap(state);

  if (state.type === 'end' && state.report) {
    showEndOverlay(state.report);
  } else {
    document.getElementById('end-overlay').classList.remove('visible');
  }
}

// ────────────────────────────────────────────────────────────────────────────
// HUD & Minimap
// ────────────────────────────────────────────────────────────────────────────

function updateHUD(state) {
  document.getElementById('scenario-name').textContent = state.world.name || 'Scenario Running';
  document.getElementById('clock-cur').textContent = state.sim_time.toFixed(1) + 's';
  document.getElementById('clock-max').textContent = '/ ' + state.duration.toFixed(1) + 's';
  document.getElementById('m-speed').textContent = state.speed.toFixed(1) + 'x';
  
  const btnPause = document.getElementById('btn-pause');
  btnPause.innerHTML = `<span class="icon">${state.paused ? '▶' : '⏸'}</span> ${state.paused ? 'Resume' : 'Pause'} <span class="ctrl-key">Space</span>`;
  btnPause.style.borderColor = state.paused ? 'rgba(255,170,0,0.4)' : '';
  btnPause.style.color = state.paused ? 'var(--warning)' : '';

  const m = state.metrics || {};
  const evidence = document.getElementById('delivery-evidence');
  const number = (x) => x == null ? '—' : Number(x).toFixed(1);
  evidence.textContent = `DELIVERY EVIDENCE\nAcquired ${number(m.acquired_completion_pct)}% | GCS received ${number(m.delivered_completion_pct)}%\nPending ${m.pending_observations ?? 0} | Queue ${m.queue_bytes ?? 0} bytes\nDelivery p95 ${number(m.latency_p95_s)} s | Min separation ${number(m.minimum_separation_m)} m\nAll-UAV availability ${number(m.all_uav_connectivity_pct)}%\nHandoffs ${m.mbb_handoffs_completed ?? 0} | Contact losses ${m.contact_loss_detections ?? 0}`;

  document.getElementById('m-mission').textContent = (m.mission_completion || 0) + '%';
  document.getElementById('m-mission-bar').style.width = (m.mission_completion || 0) + '%';
  
  document.getElementById('m-priority').textContent = (m.priority_completion || 0) + '%';
  document.getElementById('m-priority-bar').style.width = (m.priority_completion || 0) + '%';

  document.getElementById('m-pois').textContent = `${m.surveyed_pois || 0} / ${m.total_pois || 0}`;
  document.getElementById('m-uavs').textContent = `${m.active_uavs || 0} / ${m.total_uavs || 0}`;

  const c = document.getElementById('m-conn');
  c.textContent = (m.connectivity || 0) + '%';
  c.className = 'value sm ' + (m.connectivity >= 80 ? 'good' : m.connectivity >= 50 ? 'warn' : 'danger');

  document.getElementById('m-fiedler').textContent = number(m.hop_pdr_pct) + '%';

  const logs = document.getElementById('log-list');
  logs.innerHTML = (state.events || []).map(e => 
    `<div class="log-entry"><span class="time">[${e.time.toFixed(1)}s]</span>${e.message}</div>`
  ).join('');
  logs.scrollTop = logs.scrollHeight;

  // Explainability Feed (Phase 3)
  const explainList = document.getElementById('explain-list');
  if (explainList) explainList.replaceChildren();
  if (explainList && state.explain && state.explain.length > 0) {
    const ICONS = {
      'FAILURE': '💥', 'ASSIGNED_SCOUT': '🎯', 'ASSIGNED_RELAY': '📡',
      'BATTERY_CRITICAL': '🪫', 'NPNT_BLOCK': '🚫', 'REPLAN': '🔄',
      'SENSOR': '👁️', 'SPOOFED_GPS': '⚠️', 'RECHARGE_COMPLETE': '🔋',
      'SENT_TO_RECHARGE': '⚡'
    };
    state.explain.forEach(e => {
      const icon = Object.entries(ICONS).find(([k]) => e.event.includes(k))?.[1] || '📋';
      const color = e.event.includes('FAILURE') || e.event.includes('CRITICAL') ? '#ff4444' :
                    e.event.includes('ASSIGNED') ? '#44ff88' :
                    e.event.includes('SENSOR') || e.event.includes('REPLAN') ? '#ffdd44' : '#aaa';
      const div = document.createElement('div');
      div.className = 'log-entry';
      div.style.color = color;
      div.innerHTML = `<span class="time">[${e.time.toFixed(1)}s]</span> ${icon} <b>${e.uav}</b> ${e.event}`;
      explainList.appendChild(div);
    });
    // Keep only last 50 entries
    while (explainList.children.length > 50) explainList.removeChild(explainList.firstChild);
    explainList.scrollTop = explainList.scrollHeight;
  }
}

function updateMinimap(state) {
  const cvs = document.getElementById('minimap');
  if (!cvs) return;
  const ctx = cvs.getContext('2d');
  cvs.width = cvs.parentElement.clientWidth;
  cvs.height = cvs.parentElement.clientHeight;
  const sx = cvs.width / state.world.width;
  const sy = cvs.height / state.world.height;

  ctx.clearRect(0,0,cvs.width,cvs.height);

  // Obstacles
  (state.obstacles || []).forEach(o => {
    ctx.fillStyle = 'rgba(255,50,50,0.15)';
    ctx.beginPath(); ctx.arc(o.x*sx, o.y*sy, o.radius*sx, 0, Math.PI*2); ctx.fill();
  });
  
  // GCS
  if (state.gcs) {
    ctx.fillStyle = '#00ffc8';
    ctx.fillRect(state.gcs.x*sx-3, state.gcs.y*sy-3, 6, 6);
  }

  // PoIs
  (state.pois || []).forEach(p => {
    ctx.fillStyle = p.surveyed ? '#00cc66' : '#ff5500';
    ctx.beginPath(); ctx.arc(p.x*sx, p.y*sy, 3, 0, Math.PI*2); ctx.fill();
  });

  // UAVs
  (state.uavs || []).forEach(u => {
    ctx.fillStyle = '#' + (STATE_COLORS[u.state] || 0x667788).toString(16).padStart(6,'0');
    ctx.beginPath(); ctx.arc(u.x*sx, u.y*sy, 2.5, 0, Math.PI*2); ctx.fill();
  });
}

function showEndOverlay(rep) {
  document.getElementById('end-overlay').classList.add('visible');
  document.getElementById('end-stats').innerHTML = `
    <div class="stat-row"><span class="stat-label">GCS Delivery</span><span class="stat-value" style="color:var(--success)">${rep.mission_completion_pct}%</span></div>
    <div class="stat-row"><span class="stat-label">Priority Weighted</span><span class="stat-value">${rep.priority_weighted_pct}%</span></div>
    <div class="stat-row"><span class="stat-label">Surveyed PoIs</span><span class="stat-value">${rep.surveyed_pois} / ${rep.total_pois}</span></div>
    <div class="stat-row"><span class="stat-label">All-UAV Connectivity</span><span class="stat-value">${rep.all_uav_connectivity_pct}%</span></div>
    <div class="stat-row"><span class="stat-label">Per-hop Packet Delivery</span><span class="stat-value">${rep.hop_pdr_pct}%</span></div>
    <div class="stat-row"><span class="stat-label">UAV Casualties</span><span class="stat-value" style="color:var(--danger)">${rep.failed_uavs}</span></div>
  `;
}

// ────────────────────────────────────────────────────────────────────────────
// WebSocket & Controls
// ────────────────────────────────────────────────────────────────────────────

let ws = null;
function connect() {
  const st = document.getElementById('connection-status');
  st.className = 'connecting'; st.textContent = '● CONNECTING';
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
  ws.onopen = () => { st.className = 'connected'; st.textContent = '● LIVE LINK ACTIVE'; };
  ws.onmessage = e => updateScene(JSON.parse(e.data));
  ws.onclose = () => { st.className = 'disconnected'; st.textContent = '● SIGNAL LOST'; setTimeout(connect, 2000); };
}

function sendCmd(action, data={}) { if (ws && ws.readyState===1) ws.send(JSON.stringify({action, ...data, command_id: crypto.randomUUID(), generation: currentGeneration})); }

document.getElementById('btn-pause').onclick = () => sendCmd('pause');
document.getElementById('btn-speed-up').onclick = () => sendCmd('speed_up');
document.getElementById('btn-speed-down').onclick = () => sendCmd('speed_down');
document.getElementById('btn-kill-uav').onclick = () => {
  const uavId = parseInt(document.getElementById('uav-select-kill').value) - 1; // 0-indexed internally
  sendCmd('kill_uav', { uav_id: uavId });
};
document.getElementById('btn-spoof-gps').onclick = () => {
  const uavId = parseInt(document.getElementById('uav-select-spoof').value) - 1;
  sendCmd('spoof_gps', { uav_id: uavId });
};
document.getElementById('btn-burst-outage').onclick = () => sendCmd('trigger_outage');
document.getElementById('btn-poi').onclick = () => sendCmd('inject_poi');
const resetAction = () => { sendCmd('reset'); clearScene(); };
document.getElementById('btn-reset').onclick = resetAction;
document.getElementById('btn-end-reset').onclick = resetAction;

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === ' ') { e.preventDefault(); sendCmd('pause'); }
  if (e.key === '=' || e.key === '+') sendCmd('speed_up');
  if (e.key === '-') sendCmd('speed_down');
  if (e.key.toLowerCase() === 'f') sendCmd('inject_failure');
  if (e.key.toLowerCase() === 'p') sendCmd('inject_poi');
  if (e.key.toLowerCase() === 'r') resetAction();
  if (e.key === '0') { followUAV = null; selectedUAV = null; controls.target.set(worldSize.w*SCALE/2, 0, worldSize.h*SCALE/2); }
  const n = parseInt(e.key);
  if (n >= 1 && n <= 8) { followUAV = n-1; selectedUAV = n-1; }
});

// ────────────────────────────────────────────────────────────────────────────
// Hover Interactions & Tooltips
// ────────────────────────────────────────────────────────────────────────────

window.addEventListener('mousemove', e => {
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  
  raycaster.setFromCamera(mouse, camera);
  const intersectables = Object.values(uavObjects).map(u => u.hitbox);
  const hits = raycaster.intersectObjects(intersectables);
  
  const tt = document.getElementById('tooltip');
  if (hits.length > 0) {
    const id = hits[0].object.userData.id;
    // Find uav state
    const el = document.querySelector(`.fleet-item[data-id="${id}"]`);
    if (el) {
      tt.style.display = 'block';
      tt.style.left = (e.clientX + 15) + 'px';
      tt.style.top = (e.clientY + 15) + 'px';
      document.getElementById('tt-title').textContent = el.querySelector('.fleet-name').textContent;
      document.getElementById('tt-content').innerHTML = `
        <div class="tt-row"><span class="tt-label">Role:</span><span class="tt-val">${el.querySelector('.fleet-state').textContent}</span></div>
        <div class="tt-row"><span class="tt-label">Battery:</span><span class="tt-val">${el.querySelector('.fleet-batt').textContent}</span></div>
      `;
    }
  } else {
    tt.style.display = 'none';
  }
});

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  composer.render();
  labelRenderer.render(scene, camera);
}

connect();
animate();
