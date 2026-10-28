"use client";

import { useEffect } from "react";
import { motion, MotionConfig } from "framer-motion";
import TrustGraph from "../components/TrustGraph";
import { API } from "../lib/api";
import { useCouncil, runReplay } from "../lib/store";

const SCENARIOS = ["reactor-failure", "water-contamination", "habitat-breach"];

function Arc({ value, color, label }) {
  const r = 44;
  const circ = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, value || 0));
  return (
    <div style={{ textAlign: "center" }}>
      <svg width="110" height="70" viewBox="0 0 110 70">
        <path d="M 10 60 A 44 44 0 0 1 100 60" fill="none"
          stroke="rgba(255,255,255,0.12)" strokeWidth="10"
          strokeLinecap="round" />
        <path d="M 10 60 A 44 44 0 0 1 100 60" fill="none" stroke={color}
          strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${circ / 2}`} strokeDashoffset={`${(circ / 2) * (1 - frac)}`} />
        <text x="55" y="52" textAnchor="middle" fill="#e8edf5"
          fontSize="15" fontFamily="monospace">{(frac).toFixed(2)}</text>
      </svg>
      <div className="mono" style={{ fontSize: 11, color: "#9aa6bb" }}>{label}</div>
    </div>
  );
}

const numOrNull = (x) => (typeof x === "number" && isFinite(x) ? x : null);

function AgentCard({ id, data }) {
  const scores = (data && data.scores) || {};
  const entries = Object.entries(scores).filter(
    ([, v]) => Array.isArray(v) && numOrNull(v[0]) !== null && numOrNull(v[1]) !== null);
  const hes = entries.length
    ? entries.reduce((a, [, v]) => a + (v[1] - v[0]), 0) / entries.length
    : 0;
  const role = id === "strategist" ? "strategist"
    : id === "devils_advocate" ? "devil" : "expert";
  return (
    <div className={`panel agent-card ${role}`}>
      <h2>{id.replace(/_/g, " ")}</h2>
      <div style={{ margin: "6px 0" }}>
        <span className="lockbadge">
          <svg width="10" height="12" viewBox="0 0 10 12" fill="none">
            <rect x="1" y="5" width="8" height="6" rx="1" stroke="#2dd4a8" />
            <path d="M3 5V3.5a2 2 0 0 1 4 0V5" stroke="#2dd4a8" />
          </svg>
          ZERO CROSS-INFLUENCE
        </span>
      </div>
      <div className="mono" style={{ fontSize: 11, color: "#9aa6bb" }}>
        {data.model || "unknown"} {data.live_model ? "● live" : "○ rehearsal"}
      </div>
      {entries.map(([opt, v]) => (
        <div key={opt} className="mono" style={{ fontSize: 11, marginTop: 4 }}>
          {opt}: [{v[0].toFixed(2)}, {v[1].toFixed(2)}]
        </div>
      ))}
      <div style={{ marginTop: 8 }}>
        <div className="mono" style={{ fontSize: 11 }}>hesitation {hes.toFixed(2)}</div>
        <div className="hesbar"><span style={{
          width: `${Math.round(hes * 100)}%`,
          background: hes > 0.35 ? "#ff4d5e" : "#2dd4a8",
        }} /></div>
      </div>
      <p style={{ color: "#9aa6bb" }}>{data.rationale}</p>
    </div>
  );
}

function HealthStrip({ health }) {
  if (!health) return <p className="mono">Checking server…</p>;
  if (!health.ok && !health.tiers)
    return <p className="mono">Server unreachable: {health.error}</p>;
  const dot = (on) => (on ? "●" : "○");
  const open = health.tiers.open;
  const smart = health.tiers.smart;
  return (
    <p className="mono" style={{ fontSize: 12 }}>
      server: {health.offline ? "REHEARSAL" : "LIVE"} · open {dot(open.configured)} {open.model} ·
      smart {dot(smart.configured)} {smart.model}
      {!open.configured && !smart.configured && !health.offline &&
        " — no keys seen: runs will 502"}
    </p>
  );
}

export default function Page() {
  const s = useCouncil();
  useEffect(() => { s.loadHealth(); s.loadHistory(); }, []);
  const mapSrc = s.mapUrl === "BACKEND_MAP" ? `${API}/map`
    : s.mapUrl && s.mapUrl.startsWith("http") ? s.mapUrl : null;
  const posList = Object.values(s.positions);
  const groupHes = posList.length
    ? posList.reduce((a, p) => {
        const vs = Object.values(p.scores || {});
        return a + (vs.length ? vs.reduce((x, v) => x + (v[1] - v[0]), 0) / vs.length : 0);
      }, 0) / posList.length
    : 0;

  return (
    <MotionConfig reducedMotion="user">
    <div className="wrap">
      <div className="grid" style={{ marginBottom: 14 }}>
        <div className="panel solid">
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <h1>Mars Council</h1>
            <span className={`badge ${s.mode === "council" ? "hot" : ""}`}>
              {s.mode === "council" ? "COUNCIL ACTIVATED" : s.mode === "single" ? "SINGLE AGENT" : s.mode === "devil" ? "DEVIL'S CHECK" : "STANDBY"}
            </span>
            {s.status === "running" && <span className="badge live pulse">LIVE</span>}
            <span style={{ flex: 1 }} />
            <select value={s.scenario} onChange={(e) => s.setScenario(e.target.value)}
              disabled={s.status === "running"}>
              {SCENARIOS.map((sc) => <option key={sc} value={sc}>{sc}</option>)}
            </select>
            <button onClick={runReplay} disabled={s.status === "running"}>
              {s.status === "running" ? "Running…" : "Simulate Mars Crisis"}
            </button>
            {s.status === "running" && (
              <button className="ghost" onClick={() => s.setPaused(!s.paused)}>
                {s.paused ? `Resume (${s.queue.length} held)` : "Pause"}
              </button>
            )}
            {(s.status === "running" || s.status === "done") && (
              <button className="ghost" onClick={s.stopReplay}>Stop</button>
            )}
          </div>
          {s.telemetry && (
            <div className="gauge-row" style={{ marginTop: 12 }}>
              <Arc value={s.telemetry.uncertainty} color="#4da3ff" label="uncertainty" />
              <Arc value={groupHes} color="#ffb020" label="hesitation" />
              <span className={`badge ${s.telemetry.irreversible ? "hot" : ""}`}>
                {s.telemetry.irreversible ? "HIGH-STAKES · IRREVERSIBLE" : "REVERSIBLE"}
              </span>
              <span className="badge">{s.telemetry.competing_paths} competing paths</span>
            </div>
          )}
          {s.status === "error" && <p style={{ color: "#ff4d5e" }}>{s.error}</p>}
          <div style={{ marginTop: 8 }}>
            <HealthStrip health={s.health} />
          </div>
        </div>
      </div>

      <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}>
      <div className="grid grid-3">
        {Object.entries(s.positions).map(([id, data]) => (
          <AgentCard key={id} id={id} data={data} />
        ))}
        {Object.keys(s.positions).length === 0 && (
          <div className="panel">
            <h2>Round 1 · Isolated positions</h2>
            <p className="mono">Agents form positions in isolation…</p>
          </div>
        )}
      </div>
      </motion.section>

      <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.1 }} style={{ marginTop: 14 }}>
      <div className="grid grid-2">
        <div className="panel">
          <h2>Round 2 · Trust-similarity network{s.clusters ? ` (silhouette ${s.clusters.silhouette})` : ""}</h2>
          <TrustGraph clusters={s.clusters} counters={s.counters} />
        </div>
        <div className="panel">
          <h2>Cross-examination stream</h2>
          <div className="log mono">
            {s.counters.map((c, i) => (
              <div key={i} className={i === s.counters.length - 1 ? "stream-row latest" : "stream-row"}>
                {i === s.counters.length - 1 && <span className="pulse-dot" />}
                <b>{c.from}</b> → {c.target}: {c.contradiction}
              </div>
            ))}
            {s.counters.length === 0 && <div>Awaiting cross-examination…</div>}
          </div>
        </div>
        <div className="panel" style={{ gridColumn: "1 / -1" }}>
          <h2>Wonder paths</h2>
          <div className="log mono">
            {(s.paths || []).filter((p) => p && typeof p === "object").map((p, i) => (
              <div key={i} className="stream-row">
                <b>{p.title || "unnamed path"}</b> ({Math.round((numOrNull(p.likelihood) || 0) * 100)}%) — {p.fallout || ""}
              </div>
            ))}
            {(s.paths || []).length === 0 && <div>No alternate paths predicted.</div>}
          </div>
        </div>
      </div>
      </motion.section>

      <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.2 }} style={{ marginTop: 14 }}>
      <div className="grid grid-2">
        <div className="panel">
          <h2>Round 3 · DDPG steering → consensus</h2>
          <div style={{ display: "flex", gap: 18, justifyContent: "center" }}>
            <Arc value={s.steer.length ? s.steer[s.steer.length - 1].intensity : 0}
              color="#ffb020" label="feedback intensity" />
            <Arc value={s.consensus} color="#2dd4a8" label="consensus / 0.9 target" />
          </div>
          {s.action && (
            <p className="mono">action: <b>{s.action}</b></p>
          )}
        </div>
        <div className="panel">
          <h2>Situation map</h2>
          {mapSrc
            ? <img src={mapSrc} alt="Situation map" style={{ width: "100%", borderRadius: 8 }} />
            : <p className="mono">Awaiting Round 3 consensus…</p>}
        </div>
      </div>
      </motion.section>

      <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.3 }}>
      <div className="dissent glow-crimson" style={{ marginTop: 14 }}>
        <h2>Choice impact: what we are choosing to ignore</h2>
        {(s.dissent || []).filter((d) => d && typeof d === "object").map((d, i) => (
          <div key={i} className="callout mono" style={{ fontSize: 12, marginTop: 8 }}>
            <b>{d.agent || "?"}</b> moved {numOrNull(d.moved) ?? "?"} — held{" "}
            {Object.entries(d.original || {}).map(([o, v]) => `${o} ${v}`).join(", ")}
          </div>
        ))}
        {s.dissent.length === 0 && (
          <p className="mono">No dissent logged yet.</p>
        )}
      </div>
      </motion.section>

      <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.4 }}>
      <div className="panel" style={{ marginTop: 14 }}>
        <h2>Run records · provenance ledger</h2>
        <div className="log mono" style={{ fontSize: 12 }}>
          {(s.history || []).filter((r) => r && typeof r === "object").map((r, i) => (
            <div key={i} className="stream-row">
              {typeof r.ts === "number" ? new Date(r.ts * 1000).toLocaleString() : "?"} · <b>{r.scenario || "?"}</b> · {r.mode || "?"} ·
              action <b>{r.action || "?"}</b> · consensus {numOrNull(r.consensus) ?? "?"} ·
              dissent {Array.isArray(r.dissent_log) ? r.dissent_log.length : 0} ·
              events {r.events || "?"} · {r.live_model ? "● live" : "○ rehearsal"}
            </div>
          ))}
          {s.history.length === 0 && <div>No runs recorded yet.</div>}
        </div>
      </div>
      </motion.section>
    </div>
    </MotionConfig>
  );
}
