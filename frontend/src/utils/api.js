const BASE = "http://localhost:8000";

async function get(path, params = {}) {
  const url = new URL(BASE + path);
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  getEvents: (homeId = "home_001", hours = 24) =>
    get("/events", { home_id: homeId, hours }),

  getPatterns: (homeId = "home_001", days = 7, flaggedOnly = false) =>
    get("/patterns", { home_id: homeId, days, flagged_only: flaggedOnly }),

  getPattern: (id) => get(`/patterns/${id}`),

  scorePattern: (homeId, events) =>
    post("/patterns/score", { home_id: homeId, events }),

  getBaseline: (homeId = "home_001") =>
    get("/baseline", { home_id: homeId }),
};
