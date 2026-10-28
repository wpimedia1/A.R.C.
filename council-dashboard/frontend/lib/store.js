import { create } from "zustand";
import { postRun, postCustom, connectFeed, getHealth, getRuns } from "./api";

export const useCouncil = create((set, get) => ({
  status: "idle",
  scenario: "reactor-failure",
  mode: null,
  telemetry: null,
  positions: {},
  counters: [],
  clusters: null,
  steer: [],
  consensus: null,
  action: null,
  dissent: [],
  mapUrl: null,
  error: null,
  paused: false,
  queue: [],
  ws: null,
  paths: [],

  setScenario: (scenario) => set({ scenario }),

  reset: () =>
    set({
      status: "idle", mode: null, telemetry: null, positions: {},
      counters: [], clusters: null, steer: [], consensus: null,
      action: null, dissent: [], mapUrl: null, error: null,
      paused: false, queue: [], ws: null, paths: [],
    }),

  setPaused: (paused) => {
    const { queue } = useCouncil.getState();
    set({ paused });
    if (!paused) {
      set({ queue: [] });
      queue.forEach((ev) => useCouncil.getState().applyEvent(ev));
    }
  },

  stopReplay: () => {
    const { ws } = useCouncil.getState();
    try { ws && ws.close(); } catch { /* already closed */ }
    useCouncil.getState().reset();
  },

  applyEvent: (ev) =>
    set((s) => {
      if (s.paused && ev.type !== "RUN_FINISHED") {
        return { queue: [...s.queue, ev] };
      }
      switch (ev.type) {
        case "MODE_SELECTED":
          return { mode: ev.payload.mode, status: "running", telemetry: ev.payload };
        case "ROUND_1_SUBMIT":
          return { positions: { ...s.positions, [ev.agent]: ev.payload } };
        case "COUNTERARGUE":
          return { counters: [...s.counters, { from: ev.agent, ...ev.payload }] };
        case "CLUSTER_FORMED":
          return { clusters: ev.payload };
        case "STEER_APPLIED":
          return { steer: [...s.steer, ev.payload], consensus: ev.payload.consensus };
        case "CONSENSUS_REACHED":
          return { action: ev.payload.action, consensus: ev.payload.consensus };
        case "DISSENT_LOGGED":
          return { dissent: [...s.dissent, { agent: ev.agent, ...ev.payload }] };
        case "WONDER_PATHS":
          return { paths: ev.payload.paths || [] };
        case "MAP_GENERATED":
          return {
            mapUrl: ev.payload.live_model ? ev.payload.map : "BACKEND_MAP",
          };
        case "RUN_FINISHED":
          return { status: "done" };
        default:
          return {};
      }
    }),

  applyResult: (res) =>
    set({
      status: "done",
      mode: res.mode,
      action: res.action,
      consensus: res.consensus,
      dissent: res.dissent_log,
      mapUrl: res.map ? "BACKEND_MAP" : null,
      paths: res.wonder_paths || [],
      steer: res.steering.map((intensity, step) => ({ step, intensity })),
    }),

  fail: (error) => set({ status: "error", error }),

  health: null,
  history: [],

  loadHealth: async () => {
    try {
      set({ health: await getHealth() });
    } catch (e) {
      set({ health: { ok: false, error: String(e.message || e) } });
    }
  },

  loadHistory: async () => {
    try {
      set({ history: await getRuns(20) });
    } catch {
      /* ledger unavailable; live view still works */
    }
  },

  runCustom: async (custom) => {
    const { reset, applyEvent, applyResult, fail, loadHistory } =
      useCouncil.getState();
    reset();
    useCouncil.setState({ status: "running" });
    const ws = connectFeed(applyEvent);
    useCouncil.setState({ ws });
    try {
      applyResult(await postCustom(custom));
    } catch (e) {
      fail(String(e.message || e));
    } finally {
      setTimeout(() => { try { ws.close(); } catch { /* already closed */ } }, 1500);
      loadHistory();
    }
  },
}));

const RUN_TIMEOUT_MS = 12 * 60 * 1000;

function withTimeout(promise, ms) {
  let timer = null;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(
      `run timed out after ${Math.round(ms / 60000)} min with no result; ` +
      `the server window shows how far the council got`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (timer) clearTimeout(timer);
  });
}

export async function runReplay() {
  const { scenario, status, reset, applyEvent, applyResult, fail, loadHistory } =
    useCouncil.getState();
  if (status === "running") return;
  reset();
  useCouncil.setState({ status: "running" });
  const ws = connectFeed(applyEvent);
  useCouncil.setState({ ws });
  try {
    const res = await withTimeout(postRun(scenario, true), RUN_TIMEOUT_MS);
    applyResult(res);
  } catch (e) {
    fail(String(e.message || e));
  } finally {
    setTimeout(() => { try { ws.close(); } catch { /* already closed */ } }, 1500);
    loadHistory();
  }
}
