const ENV_API = process.env.NEXT_PUBLIC_API;
export const API =
  ENV_API ||
  (typeof window !== "undefined"
    ? window.location.origin
    : "http://localhost:8000");

function wsBase() {
  if (API) return API.replace(/^http/, "ws");
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}`;
}

async function postBody(body) {
  const res = await fetch(`${API}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = ": " + ((await res.json()).error || "");
    } catch {
      /* body is not JSON; keep the status only */
    }
    throw new Error(`run failed: ${res.status}${detail}`);
  }
  return res.json();
}

export async function postRun(scenario, replay = true) {
  return postBody({ scenario, replay });
}

export async function getHealth() {
  const res = await fetch(`${API}/health`);
  if (!res.ok) throw new Error(`health failed: ${res.status}`);
  return res.json();
}

export async function getRuns(limit = 20) {
  const res = await fetch(`${API}/runs?limit=${limit}`);
  if (!res.ok) throw new Error(`runs failed: ${res.status}`);
  return res.json();
}

export async function postCustom(custom) {
  return postBody({ scenario: "custom", replay: false, custom });
}

export function connectFeed(onEvent) {
  const ws = new WebSocket(wsBase() + "/ws");
  ws.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      if (data.type !== "PING") onEvent(data);
    } catch {
      /* ignore malformed frames */
    }
  };
  return ws;
}
