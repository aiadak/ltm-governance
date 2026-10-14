// Thin API client. Uses relative /api (Vite proxy in dev, serverless in prod).
const base = "";

async function j(path, opts) {
  const res = await fetch(base + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  health: () => j("/api/health"),
  agents: () => j("/api/agents"),
  policies: () => j("/api/policies"),
  documents: () => j("/api/documents"),
  addDocument: (doc) => j("/api/documents", { method: "POST", body: JSON.stringify(doc) }),
  retrieve: (query, role, k = 3) =>
    j("/api/retrieve", { method: "POST", body: JSON.stringify({ query, role, k }) }),
  runCall: (policy_id, brain = "") =>
    j("/api/call/run", { method: "POST", body: JSON.stringify({ policy_id, brain }) }),
  dashboard: () => j("/api/dashboard"),
  traces: (convId) => j(`/api/traces/${convId}`),
  learning: () => j("/api/learning"),
  review: (id, action, addendum = "") =>
    j(`/api/learning/${id}/review`, { method: "POST", body: JSON.stringify({ action, addendum }) }),
  runRegression: (id) => j(`/api/learning/${id}/regression`, { method: "POST" }),
  approve: (id) => j(`/api/learning/${id}/approve`, { method: "POST" }),
  reset: () => j("/api/reset", { method: "POST" }),
  realtimeToken: (policy_id) =>
    j("/api/realtime/token", { method: "POST", body: JSON.stringify({ policy_id }) }),
};
