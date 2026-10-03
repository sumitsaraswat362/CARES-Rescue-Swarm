"use client";

import React, { useState, useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import {
  Play, Pause, RotateCcw, Sun, Moon,
  Activity, Radio, ShieldAlert, CheckCircle2, Battery, Route,
  Mountain, Building2, Flame, Waves, ChevronRight, Gauge, Timer, Zap
} from "lucide-react";

import worldsData from "./data/worlds.json";
import dynamic from "next/dynamic";

const Scene3D = dynamic(() => import("../components/Scene3D"), { ssr: false });

const WORLD_KEYS = ["alpine", "canyon", "volcanic", "archipelago"] as const;
type WorldKey = (typeof WORLD_KEYS)[number];

const WORLD_ICONS: Record<WorldKey, any> = {
  alpine: Mountain,
  canyon: Building2,
  volcanic: Flame,
  archipelago: Waves,
};

const WORLD_COLORS: Record<WorldKey, string> = {
  alpine: "cyan",
  canyon: "orange",
  volcanic: "red",
  archipelago: "blue",
};

const worlds = worldsData as any;

// ─── Metric Card ─────────────────────────────────────────────────
function MetricCard({ label, value, icon: Icon, accent }: any) {
  return (
    <div className="bg-white/50 dark:bg-white/[0.03] backdrop-blur-xl rounded-2xl p-4 border border-gray-200/60 dark:border-white/[0.06] hover:border-gray-300 dark:hover:border-white/10 transition-all group">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center bg-${accent}-500/10 dark:bg-${accent}-500/20 group-hover:scale-110 transition-transform`}>
          <Icon className={`w-5 h-5 text-${accent}-500`} />
        </div>
        <div>
          <div className="text-[10px] font-semibold tracking-[0.15em] text-gray-400 dark:text-gray-500 uppercase">{label}</div>
          <div className="text-xl font-bold text-gray-900 dark:text-white mt-0.5">{value}</div>
        </div>
      </div>
    </div>
  );
}

// ─── UAV Row ─────────────────────────────────────────────────────
function UAVRow({ uav }: { uav: any }) {
  const pct = Math.round(uav.battery * 100);
  const isRelay = uav.role === "relay";
  return (
    <div className="flex items-center gap-3 py-2.5 px-3 rounded-xl bg-gray-50/80 dark:bg-white/[0.02] border border-transparent hover:border-gray-200 dark:hover:border-white/[0.06] transition-all">
      <div className={`w-2.5 h-2.5 rounded-full ${isRelay ? "bg-cyan-500 shadow-[0_0_10px_rgba(6,182,212,0.7)]" : "bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.7)]"}`} />
      <span className="text-sm font-semibold text-gray-800 dark:text-gray-100 w-14">UAV-{uav.id + 1}</span>
      <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${isRelay ? "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400" : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"}`}>
        {uav.role}
      </span>
      <div className="flex-1 flex items-center gap-2">
        <Battery className="w-3.5 h-3.5 text-gray-400" />
        <div className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-500 ${pct > 60 ? "bg-green-500" : pct > 30 ? "bg-amber-500" : "bg-red-500"}`}
            style={{ width: `${pct}%` }} />
        </div>
        <span className="text-[11px] font-mono font-semibold text-gray-500 dark:text-gray-400 w-10 text-right">{pct}%</span>
      </div>
      <span className="text-[11px] font-mono text-gray-400 w-10 text-right">{Math.round(uav.altitude)}m</span>
    </div>
  );
}

// ─── Timeline Chart ──────────────────────────────────────────────
function MiniChart({ data, currentIdx, color, label }: { data: any[]; currentIdx: number; color: string; label: string }) {
  const vals = data.map((s: any) => s.metrics.mission_completion_pct);
  const max = Math.max(...vals, 1);
  const w = 280, h = 50;
  return (
    <div className="bg-white/50 dark:bg-white/[0.03] backdrop-blur rounded-xl p-3 border border-gray-200/60 dark:border-white/[0.06]">
      <div className="text-[9px] font-semibold tracking-[0.15em] text-gray-400 uppercase mb-1">{label}</div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
        <path d={`M0,${h} ${vals.map((v: number, i: number) => `L${(i / vals.length) * w},${h - (v / max) * (h - 4)}`).join(" ")} L${w},${h} Z`}
          fill={`${color}15`} />
        <path d={vals.map((v: number, i: number) => `${i === 0 ? "M" : "L"}${(i / vals.length) * w},${h - (v / max) * (h - 4)}`).join(" ")}
          fill="none" stroke={color} strokeWidth="1.5" />
        <line x1={(currentIdx / vals.length) * w} y1={0} x2={(currentIdx / vals.length) * w} y2={h}
          stroke="white" strokeWidth="1" strokeDasharray="2,2" opacity={0.4} />
      </svg>
    </div>
  );
}

// ─── Tab Button ──────────────────────────────────────────────────
function Tab({ active, label, icon: Icon, onClick, color }: any) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${active
        ? `bg-${color}-500/10 text-${color}-600 dark:text-${color}-400 border border-${color}-500/30 shadow-sm`
        : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/5"
      }`}>
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );
}

// ─── Main ────────────────────────────────────────────────────────
export default function Dashboard() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [worldKey, setWorldKey] = useState<WorldKey>("alpine");
  const [frameIdx, setFrameIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [activeTab, setActiveTab] = useState<"3d" | "metrics" | "fleet">("3d");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => setMounted(true), []);

  const world = worlds[worldKey];
  const replay = world.replay;
  const config = world.scenario;
  const snap = replay[frameIdx] || replay[0];
  const m = snap.metrics;
  const isDark = resolvedTheme === "dark";

  // Reset frame when changing world
  useEffect(() => { setFrameIdx(0); setPlaying(false); }, [worldKey]);

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(() => {
        setFrameIdx((prev) => {
          if (prev >= replay.length - 1) { setPlaying(false); return prev; }
          return prev + 1;
        });
      }, 100 / speed);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [playing, speed, replay.length]);

  if (!mounted) return null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#09090b] text-gray-900 dark:text-white transition-colors duration-300">
      {/* ─── Header ─── */}
      <header className="sticky top-0 z-50 bg-white/80 dark:bg-[#09090b]/80 backdrop-blur-2xl border-b border-gray-200/80 dark:border-white/[0.06]">
        <div className="max-w-[1700px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Radio className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight">CARES Mission Control</h1>
              <p className="text-[10px] text-gray-400 font-medium">Interactive Swarm Telemetry Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wider ${playing ? "bg-green-500/10 text-green-500 border border-green-500/30" : "bg-gray-100 dark:bg-white/5 text-gray-500 border border-transparent"}`}>
              {playing ? "● LIVE" : "◻ PAUSED"}
            </div>
            <button onClick={() => setTheme(isDark ? "light" : "dark")}
              className="p-2 rounded-full bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 transition-colors">
              {isDark ? <Sun className="w-4 h-4 text-yellow-500" /> : <Moon className="w-4 h-4 text-gray-600" />}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1700px] mx-auto p-6 space-y-5">

        {/* ─── World Selector ─── */}
        <div className="grid grid-cols-4 gap-3">
          {WORLD_KEYS.map((key) => {
            const Icon = WORLD_ICONS[key];
            const active = worldKey === key;
            const w = worlds[key].scenario;
            return (
              <button key={key} onClick={() => setWorldKey(key)}
                className={`relative p-4 rounded-2xl text-left transition-all border ${active
                  ? "bg-white dark:bg-white/[0.05] border-cyan-500/50 shadow-lg shadow-cyan-500/10 dark:shadow-cyan-500/5"
                  : "bg-white/50 dark:bg-white/[0.02] border-gray-200/60 dark:border-white/[0.06] hover:border-gray-300 dark:hover:border-white/10"
                }`}>
                <div className="flex items-center gap-3 mb-2">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${active ? "bg-cyan-500/20" : "bg-gray-100 dark:bg-white/5"}`}>
                    <Icon className={`w-4 h-4 ${active ? "text-cyan-500" : "text-gray-400"}`} />
                  </div>
                  <div>
                    <div className="text-sm font-bold">{w.name}</div>
                    <div className="text-[10px] text-gray-400">{w.desc}</div>
                  </div>
                </div>
                {active && <div className="absolute top-2 right-3 w-2 h-2 rounded-full bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.8)]" />}
              </button>
            );
          })}
        </div>

        {/* ─── Top Metrics ─── */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <MetricCard label="Mission Time" value={`${Math.floor(snap.time / 60)}:${String(Math.round(snap.time % 60)).padStart(2, "0")}`} icon={Timer} accent="blue" />
          <MetricCard label="Connectivity" value={`${m.any_uav_connectivity_pct}%`} icon={Radio} accent="cyan" />
          <MetricCard label="PoIs Surveyed" value={`${m.surveyed_pois} / ${m.total_pois}`} icon={CheckCircle2} accent="green" />
          <MetricCard label="Min Separation" value={`${m.minimum_separation_m}m`} icon={ShieldAlert} accent="amber" />
          <MetricCard label="Grid Bounds" value="1000x1000m" icon={Activity} accent="blue" />
          <MetricCard label="Comm Range" value="< 100m" icon={Radio} accent="purple" />
        </div>

        {/* ─── Tab Bar ─── */}
        <div className="flex items-center gap-2 bg-white/50 dark:bg-white/[0.02] p-1.5 rounded-2xl border border-gray-200/60 dark:border-white/[0.06] w-fit">
          <Tab active={activeTab === "3d"} label="3D World" icon={Mountain} onClick={() => setActiveTab("3d")} color="cyan" />
          <Tab active={activeTab === "fleet"} label="Fleet Telemetry" icon={Route} onClick={() => setActiveTab("fleet")} color="green" />
          <Tab active={activeTab === "metrics"} label="Mission Analytics" icon={Activity} onClick={() => setActiveTab("metrics")} color="purple" />
        </div>

        {/* ─── Content ─── */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-5">

          {/* Left Panel */}
          <div className="space-y-4">
            {/* 3D View */}
            {activeTab === "3d" && (
              <div className="relative w-full h-[580px] rounded-3xl overflow-hidden border border-gray-200/50 dark:border-white/[0.06] shadow-sm">
                <Scene3D snapshot={snap} config={config} isDark={isDark} />
                <div className="absolute top-4 left-4 bg-white/80 dark:bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-full border border-gray-200 dark:border-white/10 text-[11px] font-bold flex items-center gap-2 shadow">
                  <div className={`w-2 h-2 rounded-full ${playing ? "bg-red-500 animate-pulse" : "bg-gray-400"}`} />
                  {config.name} — t = {snap.time}s
                </div>
                <div className="absolute bottom-4 left-4 bg-white/80 dark:bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-lg border border-gray-200 dark:border-white/10 text-[10px] text-gray-500 dark:text-gray-400">
                  🖱 Drag to rotate · Scroll to zoom · Right-click to pan
                </div>
              </div>
            )}

            {/* Fleet Telemetry Full View */}
            {activeTab === "fleet" && (
              <div className="bg-white/50 dark:bg-white/[0.03] backdrop-blur rounded-3xl p-6 border border-gray-200/60 dark:border-white/[0.06]">
                <h2 className="text-base font-bold mb-4">Fleet Telemetry — {config.name}</h2>
                <div className="grid grid-cols-2 gap-3">
                  {snap.uavs.map((u: any) => (
                    <div key={u.id} className="bg-gray-50 dark:bg-white/[0.02] rounded-2xl p-4 border border-gray-200/60 dark:border-white/[0.06]">
                      <div className="flex items-center gap-2 mb-3">
                        <div className={`w-3 h-3 rounded-full ${u.role === "relay" ? "bg-cyan-500" : "bg-green-500"}`} />
                        <span className="font-bold">UAV-{u.id + 1}</span>
                        <span className="text-[10px] uppercase font-bold text-gray-400">{u.role}</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div><span className="text-gray-400">Position</span><br /><span className="font-mono">{u.pos[0].toFixed(0)}, {u.pos[1].toFixed(0)}</span></div>
                        <div><span className="text-gray-400">Altitude</span><br /><span className="font-mono">{u.altitude.toFixed(1)}m</span></div>
                        <div><span className="text-gray-400">Battery</span><br /><span className="font-mono" style={{ color: u.battery > 0.5 ? "#4caf50" : "#ff9800" }}>{Math.round(u.battery * 100)}%</span></div>
                        <div><span className="text-gray-400">State</span><br /><span className="font-mono">{u.state}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Analytics View */}
            {activeTab === "metrics" && (
              <div className="bg-white/50 dark:bg-white/[0.03] backdrop-blur rounded-3xl p-6 border border-gray-200/60 dark:border-white/[0.06] space-y-4">
                <h2 className="text-base font-bold">Mission Analytics — {config.name}</h2>
                <div className="grid grid-cols-2 gap-3">
                  <MiniChart data={replay} currentIdx={frameIdx} color="#00e5ff" label="Mission Completion %" />
                  <MiniChart data={replay} currentIdx={frameIdx} color="#76ff03" label="Connectivity Uptime %" />
                </div>
                <div className="bg-gray-50 dark:bg-white/[0.02] rounded-2xl p-4 border border-gray-200/60 dark:border-white/[0.06]">
                  <h3 className="text-sm font-bold mb-3">Performance Summary</h3>
                  <table className="w-full text-sm">
                    <tbody>
                      {[
                        ["Completion Rate", `${m.mission_completion_pct}%`],
                        ["Connectivity", `${m.any_uav_connectivity_pct}%`],
                        ["Min Separation", `${m.minimum_separation_m}m`],
                        ["Comms Downtime", `${m.communication_downtime_s}s`],
                        ["Total UAVs", `${snap.uavs.length}`],
                        ["Failed UAVs", `${m.failed_uavs}`],
                        ["PoIs Surveyed", `${m.surveyed_pois} / ${m.total_pois}`],
                        ["Mission Time", `${snap.time}s`],
                      ].map(([k, v]) => (
                        <tr key={k} className="border-b border-gray-100 dark:border-white/5">
                          <td className="py-2 text-gray-500">{k}</td>
                          <td className="py-2 text-right font-mono font-bold">{v}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ─── Playback Controls ─── */}
            <div className="bg-white/60 dark:bg-white/[0.03] backdrop-blur-xl rounded-2xl p-4 border border-gray-200/60 dark:border-white/[0.06] flex items-center gap-5">
              <div className="flex items-center gap-2">
                <button onClick={() => setPlaying(!playing)}
                  className="w-11 h-11 rounded-full bg-cyan-500 hover:bg-cyan-600 text-white flex items-center justify-center shadow-lg shadow-cyan-500/30 transition-transform active:scale-95">
                  {playing ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
                </button>
                <button onClick={() => { setFrameIdx(0); setPlaying(false); }}
                  className="w-9 h-9 rounded-full bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 text-gray-600 dark:text-gray-300 flex items-center justify-center transition">
                  <RotateCcw className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 flex items-center gap-3">
                <span className="text-xs font-mono text-gray-400 w-10">{snap.time}s</span>
                <input type="range" min={0} max={replay.length - 1} value={frameIdx}
                  onChange={(e) => setFrameIdx(Number(e.target.value))}
                  className="flex-1 h-1.5 accent-cyan-500 cursor-pointer" />
                <span className="text-xs font-mono text-gray-400 w-10">{replay[replay.length - 1].time}s</span>
              </div>
              <div className="flex items-center gap-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl">
                {[1, 2, 4, 8].map((s) => (
                  <button key={s} onClick={() => setSpeed(s)}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${speed === s ? "bg-white dark:bg-white/10 shadow text-gray-900 dark:text-white" : "text-gray-400 hover:text-gray-600"}`}>
                    {s}x
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* ─── Right Sidebar ─── */}
          <div className="space-y-4">
            <div className="bg-white/50 dark:bg-white/[0.03] backdrop-blur-xl rounded-2xl p-4 border border-gray-200/60 dark:border-white/[0.06]">
              <h2 className="text-xs font-bold tracking-[0.15em] text-gray-400 uppercase mb-3">Swarm Telemetry</h2>
              <div className="space-y-1.5">
                {snap.uavs.map((u: any) => <UAVRow key={u.id} uav={u} />)}
              </div>
            </div>

            <div className="bg-white/50 dark:bg-white/[0.03] backdrop-blur-xl rounded-2xl p-4 border border-gray-200/60 dark:border-white/[0.06]">
              <h2 className="text-xs font-bold tracking-[0.15em] text-gray-400 uppercase mb-3">Active Parameters</h2>
              <ul className="space-y-2.5 text-sm">
                {[
                  ["Map Extent", `${config.world.width}x${config.world.height}m`],
                  ["Max Comm Range", "100m"],
                  ["Min Separation", "20m"],
                  ["Flight Limit", "20 mins"],
                  ["Mission Limit", "45 mins"],
                  ["Max Speed", "5 m/s"],
                  ["Terrain", config.name],
                ].map(([k, v]) => (
                  <li key={k} className="flex justify-between">
                    <span className="text-gray-500">{k}</span>
                    <span className="font-medium">{v}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-white/50 dark:bg-white/[0.03] backdrop-blur-xl rounded-2xl p-4 border border-gray-200/60 dark:border-white/[0.06]">
              <h2 className="text-xs font-bold tracking-[0.15em] text-gray-400 uppercase mb-3">PoI Status</h2>
              <div className="space-y-1">
                {config.pois.map((poi: any) => {
                  const done = m.surveyed_pois >= poi.id;
                  return (
                    <div key={poi.id} className="flex items-center gap-2 text-xs py-1">
                      <span className={`w-2 h-2 rounded-full ${done ? "bg-green-500" : poi.priority >= 4 ? "bg-red-500" : "bg-amber-500"}`} />
                      <span className="font-mono text-gray-500">P{poi.id}</span>
                      <span className="text-gray-400 flex-1 truncate">{poi.label}</span>
                      <span className={`font-bold ${done ? "text-green-500" : "text-gray-400"}`}>{done ? "✓" : "○"}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
