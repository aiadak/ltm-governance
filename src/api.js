// Thin API client. Uses relative /api (Vite proxy in dev, serverless in prod).
const base = "";

// A per-browser-session id so the Learning Studio only shows THIS session's
// flagged answers (blank at start; past sessions never appear). sessionStorage
// survives a refresh in the same tab, resets on a new tab / close.
export function sessionId() {
  try {
    let s = sessionStorage.getItem("ltm_sid");
    if (!s) { s = "S-" + Math.random().toString(36).slice(2, 10); sessionStorage.setItem("ltm_sid", s); }
    return s;
  } catch { return "S-mem"; }
}

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
  document: (id) => j(`/api/document/${id}`),
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
  scenarios: () => j("/api/scenarios"),
  runScenario: (id) => j("/api/scenario/run", { method: "POST", body: JSON.stringify({ id }) }),
  feedbackPresets: () => j("/api/feedback/presets"),
  feedback: (payload) => j("/api/feedback", { method: "POST", body: JSON.stringify({ ...payload, session_id: sessionId() }) }),
  reviews: () => j(`/api/learning/reviews?session=${encodeURIComponent(sessionId())}`),
  clearLearning: () => j("/api/learning/clear", { method: "POST" }),
  correct: (item_id, instruction, action) =>
    j("/api/learning/correct", { method: "POST", body: JSON.stringify({ item_id, instruction, action }) }),
  realtimeToken: (policy_id) =>
    j("/api/realtime/token", { method: "POST", body: JSON.stringify({ policy_id }) }),
  voiceTool: (policy_id, name, args) =>
    j("/api/voice/tool", { method: "POST", body: JSON.stringify({ policy_id, name, arguments: args }) }),
  summarize: (policy_id, transcript, fires) =>
    j("/api/voice/summarize", { method: "POST", body: JSON.stringify({ policy_id, transcript, fires }) }),
  voiceTurn: (policy_id, text) =>
    j("/api/voice/turn", { method: "POST", body: JSON.stringify({ policy_id, text }) }),
};
