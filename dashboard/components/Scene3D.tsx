"use client";

import React, { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Line, Html, Stars } from "@react-three/drei";
import * as THREE from "three";

function getTerrainColor(z: number, maxZ: number): THREE.Color {
  const n = z / Math.max(maxZ, 1);
  const c = new THREE.Color();
  if (n < 0.05) return c.set("#1a3a5c");      // deep water
  if (n < 0.15) return c.set("#2a6e9e");       // shallow water
  if (n < 0.25) return c.set("#3d8c5c");       // coastal green
  if (n < 0.40) return c.set("#5aad4e");       // lush green
  if (n < 0.55) return c.set("#8bc34a");       // light green
  if (n < 0.70) return c.set("#cddc39");       // yellow-green
  if (n < 0.80) return c.set("#d4a017");       // brown-gold
  if (n < 0.90) return c.set("#8b6914");       // dark brown
  return c.set("#f5f5dc");                     // snow cap
}

function terrainHeight(x: number, y: number, peaks: number[][]) {
  let h = 0;
  for (const [px, py, spread, height] of peaks) {
    const distSq = (x - px) ** 2 + (y - py) ** 2;
    h += height * Math.exp(-distSq / (2 * spread ** 2));
  }
  return Math.max(0, h);
}

// ─── Terrain ─────────────────────────────────────────────────────
function Terrain({ width, height, peaks }: { width: number; height: number; peaks: number[][] }) {
  const geoRef = useRef<THREE.PlaneGeometry>(null);

  useMemo(() => {
    if (!geoRef.current) return;
    const pos = geoRef.current.attributes.position;
    const colors: number[] = [];
    let maxZ = 0;
    
    for (let i = 0; i < pos.count; i++) {
      const rx = pos.getX(i) + width / 2;
      const ry = pos.getY(i) + height / 2;
      const z = terrainHeight(rx, ry, peaks);
      pos.setZ(i, z);
      if (z > maxZ) maxZ = z;
    }
    for (let i = 0; i < pos.count; i++) {
      const color = getTerrainColor(pos.getZ(i), maxZ);
      colors.push(color.r, color.g, color.b);
    }
    geoRef.current.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geoRef.current.computeVertexNormals();
  }, [width, height, peaks]);

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <planeGeometry ref={geoRef} args={[width, height, 150, 150]} />
      <meshStandardMaterial vertexColors flatShading roughness={0.85} metalness={0.05} />
    </mesh>
  );
}

// ─── Drone Model ─────────────────────────────────────────────────
function DroneModel({ color }: { color: string }) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (groupRef.current) {
      // Spin rotors
      groupRef.current.children.forEach((child, i) => {
        if (i >= 2) { // rotors start at index 2
          child.rotation.y = state.clock.elapsedTime * 25;
        }
      });
    }
  });

  return (
    <group ref={groupRef} scale={2.5}>
      {/* Body */}
      <mesh castShadow>
        <cylinderGeometry args={[1.2, 1.8, 1.2, 6]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.6} metalness={0.3} />
      </mesh>
      {/* Arms */}
      {[0, Math.PI / 2].map((rot, i) => (
        <mesh key={`arm-${i}`} rotation={[0, rot, 0]} castShadow>
          <boxGeometry args={[14, 0.5, 0.7]} />
          <meshStandardMaterial color="#e0e0e0" metalness={0.4} roughness={0.3} />
        </mesh>
      ))}
      {/* Rotors */}
      {[
        [5, 0.8, 5], [-5, 0.8, 5], [5, 0.8, -5], [-5, 0.8, -5],
      ].map(([rx, ry, rz], i) => (
        <mesh key={`rotor-${i}`} position={[rx, ry, rz]}>
          <torusGeometry args={[2.2, 0.15, 4, 16]} />
          <meshStandardMaterial color="#444" transparent opacity={0.7} />
        </mesh>
      ))}
      {/* LED light under body */}
      <pointLight color={color} intensity={30} distance={60} position={[0, -2, 0]} />
    </group>
  );
}

// ─── UAV ─────────────────────────────────────────────────────────
function UAV({ data, cx, cy, peaks }: { data: any; cx: number; cy: number; peaks: number[][] }) {
  const [x, y] = data.pos;
  const z = data.altitude;
  const px = x - cx;
  const py = z;
  const pz = y - cy;
  const color = data.role === "relay" ? "#00e5ff" : "#76ff03";

  // Camera footprint on ground
  const groundZ = terrainHeight(x, y, peaks);
  const footprintPts = Array.from({ length: 33 }).map((_, i) => {
    const angle = (i / 32) * Math.PI * 2;
    const r = 25;
    return new THREE.Vector3(
      px + Math.cos(angle) * r,
      groundZ + 2,
      pz + Math.sin(angle) * r
    );
  });

  // Trail
  const trailPts = [
    new THREE.Vector3(px, py, pz),
    new THREE.Vector3(px, groundZ + 2, pz),
  ];

  return (
    <group position={[px, py, pz]}>
      <DroneModel color={color} />
      <Html distanceFactor={250} position={[0, 12, 0]} center zIndexRange={[100, 0]}>
        <div className="bg-black/70 backdrop-blur text-white text-[10px] font-mono px-2 py-1 rounded-lg border border-white/20 whitespace-nowrap shadow-lg">
          <span style={{ color }}>{data.role === "relay" ? "◆" : "●"}</span> UAV-{data.id + 1} | {Math.round(data.battery * 100)}% | {Math.round(z)}m
        </div>
      </Html>
      {/* Ground footprint */}
      <Line points={footprintPts} color={color} lineWidth={1} transparent opacity={0.3} />
      {/* Vertical line to ground */}
      <Line points={trailPts} color={color} lineWidth={0.5} transparent opacity={0.15} dashed dashSize={5} gapSize={5} />
    </group>
  );
}

// ─── Comm Links ──────────────────────────────────────────────────
function CommLinks({ uavs, cx, cy, gcs, peaks }: any) {
  const lines: any[] = [];
  const nodes = uavs.map((u: any) =>
    new THREE.Vector3(u.pos[0] - cx, u.altitude, u.pos[1] - cy)
  );
  const gcsH = terrainHeight(gcs.x, gcs.y, peaks);
  nodes.push(new THREE.Vector3(gcs.x - cx, gcsH + 5, gcs.y - cy));

  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const d = nodes[i].distanceTo(nodes[j]);
      if (d < 100) {
        lines.push(
          <Line key={`${i}-${j}`} points={[nodes[i], nodes[j]]}
            color="#00e5ff" lineWidth={2} transparent opacity={Math.max(0.2, 1 - d / 100)} />
        );
      }
    }
  }
  return <>{lines}</>;
}

// ─── Geofence Box ────────────────────────────────────────────────
function GeofenceBox({ w, h }: { w: number; h: number }) {
  const hx = w / 2, hy = 200, hz = h / 2;
  const pts: THREE.Vector3[] = [
    // bottom
    new THREE.Vector3(-hx, 0, -hz), new THREE.Vector3(hx, 0, -hz),
    new THREE.Vector3(hx, 0, hz), new THREE.Vector3(-hx, 0, hz),
    new THREE.Vector3(-hx, 0, -hz),
    // up
    new THREE.Vector3(-hx, hy, -hz),
    // top
    new THREE.Vector3(hx, hy, -hz), new THREE.Vector3(hx, hy, hz),
    new THREE.Vector3(-hx, hy, hz), new THREE.Vector3(-hx, hy, -hz),
  ];
  const verticals = [
    [new THREE.Vector3(hx, 0, -hz), new THREE.Vector3(hx, hy, -hz)],
    [new THREE.Vector3(hx, 0, hz), new THREE.Vector3(hx, hy, hz)],
    [new THREE.Vector3(-hx, 0, hz), new THREE.Vector3(-hx, hy, hz)],
  ];
  return (
    <>
      <Line points={pts} color="#ff9800" lineWidth={1.5} dashed dashSize={15} gapSize={8} transparent opacity={0.6} />
      {verticals.map((v, i) => (
        <Line key={i} points={v} color="#ff9800" lineWidth={1} dashed dashSize={15} gapSize={8} transparent opacity={0.4} />
      ))}
    </>
  );
}

// ─── Main Scene ──────────────────────────────────────────────────
export default function Scene3D({ snapshot, config, isDark }: { snapshot: any; config: any; isDark: boolean }) {
  const W = config.world.width;
  const H = config.world.height;
  const cx = W / 2;
  const cy = H / 2;
  const peaks = config.world.peaks || [];

  return (
    <div className="w-full h-full">
      <Canvas
        camera={{ position: [500, 100, 550], fov: 50, near: 0.1, far: 20000 }}
        shadows
        gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: isDark ? 0.8 : 1.2 }}
        style={{ background: isDark ? "#050510" : "#c5dff8" }}
      >
        <OrbitControls makeDefault maxPolarAngle={Math.PI / 2 - 0.02} target={[0, 60, 0]}
          minDistance={10} maxDistance={5000} enableDamping dampingFactor={0.05} />

        <ambientLight intensity={isDark ? 0.25 : 0.7} />
        <directionalLight position={[300, 500, 200]} intensity={isDark ? 1.0 : 1.5} castShadow
          shadow-mapSize={4096} shadow-camera-left={-600} shadow-camera-right={600}
          shadow-camera-top={600} shadow-camera-bottom={-600} />
        <hemisphereLight color={isDark ? "#111133" : "#aaccff"} groundColor={isDark ? "#080808" : "#446622"} intensity={0.5} />

        {isDark && <Stars radius={800} depth={200} count={3000} factor={3} saturation={0.3} />}

        <group>
          <Terrain width={W} height={H} peaks={peaks} />
          <GeofenceBox w={W} h={H} />
          <gridHelper args={[W, 20, isDark ? 0x334455 : 0x8899aa, isDark ? 0x1a2233 : 0xbbccdd]}
            position={[0, 0.5, 0]} />

          {/* Buildings */}
          {(config.world.obstacles || []).map((obs: any, i: number) => (
            <mesh key={`obs-${i}`} position={[obs.x - cx, terrainHeight(obs.x, obs.y, peaks) + obs.z / 2, obs.y - cy]} castShadow receiveShadow>
              <boxGeometry args={[obs.w, obs.z, obs.h]} />
              <meshStandardMaterial color={obs.color} roughness={0.6} />
            </mesh>
          ))}

          {/* GCS */}
          <group position={[config.gcs.position.x - cx, terrainHeight(config.gcs.position.x, config.gcs.position.y, peaks) + 5, config.gcs.position.y - cy]}>
            <mesh castShadow>
              <boxGeometry args={[25, 12, 25]} />
              <meshStandardMaterial color="#00bcd4" emissive="#00bcd4" emissiveIntensity={0.3} />
            </mesh>
            <mesh position={[0, 12, 0]}>
              <cylinderGeometry args={[1, 1, 20, 8]} />
              <meshStandardMaterial color="#aaa" />
            </mesh>
            <pointLight color="#00e5ff" intensity={50} distance={80} position={[0, 25, 0]} />
            <Html distanceFactor={250} center position={[0, 35, 0]}>
              <div className="bg-cyan-600/90 text-white text-[10px] font-mono px-2 py-1 rounded shadow-lg border border-cyan-300/50">
                GCS | 75m offset boundary
              </div>
            </Html>
          </group>

          {/* POIs */}
          {config.pois.map((poi: any) => {
            const h = terrainHeight(poi.x, poi.y, peaks);
            const isSurveyed = snapshot.metrics.surveyed_pois >= poi.id;
            return (
              <group key={poi.id} position={[poi.x - cx, h + 3, poi.y - cy]}>
                {[0, 1, 2, 3].map((j) => (
                  <mesh key={j} rotation={[0, (j * Math.PI) / 4, 0]}>
                    <boxGeometry args={[14, 3, 3]} />
                    <meshStandardMaterial
                      color={isSurveyed ? "#4caf50" : poi.priority >= 4 ? "#ff1744" : "#ffab00"}
                      emissive={isSurveyed ? "#4caf50" : "#ffab00"}
                      emissiveIntensity={0.6}
                    />
                  </mesh>
                ))}
                <Html distanceFactor={100} position={[0, 12, 0]} center>
                  <div className={`text-[9px] font-bold px-1 rounded ${isSurveyed ? "text-green-400" : "text-yellow-400"}`}>
                    {isSurveyed ? "✓" : "★"} P{poi.id}
                  </div>
                </Html>
              </group>
            );
          })}

          {/* UAVs */}
          {snapshot.uavs.map((uav: any) => (
            <UAV key={uav.id} data={uav} cx={cx} cy={cy} peaks={peaks} />
          ))}

          {/* Comm Links */}
          <CommLinks uavs={snapshot.uavs} cx={cx} cy={cy} gcs={config.gcs.position} peaks={peaks} />
        </group>
      </Canvas>
    </div>
  );
}
