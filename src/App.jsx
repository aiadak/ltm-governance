import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import LiveOps from "./views/LiveOps.jsx";
import LiveVoice from "./views/LiveVoice.jsx";
import Scenarios from "./views/Scenarios.jsx";
import ControlTower from "./views/ControlTower.jsx";
import Registry from "./views/Registry.jsx";
import Learning from "./views/Learning.jsx";
import Knowledge from "./views/Knowledge.jsx";
import DocViewer from "./components/DocViewer.jsx";

const TABS = [
  ["voice", "Live Voice"],
  ["ops", "Live Ops"],
  ["scenarios", "Scenarios"],
  ["tower", "Control Tower"],
  ["registry", "Agent Registry"],
  ["learn", "Learning Studio"],
  ["kb", "Knowledge Base"],
];

export default function App() {
  const [tab, setTab] = useState("ops");
  const [health, setHealth] = useState(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => { api.health().then(setHealth).catch(() => setHealth({ ok: false })); }, []);
  const refresh = () => setNonce((n) => n + 1);

  const brains = health?.llm?.brains || [];
  const live = brains.length > 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">
          <span className="mark">L</span>
          <div>LTM
            <small>Governed Contact Center</small>
          </div>
        </div>
        <nav className="nav">
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>
          ))}
        </nav>
        <span className="spacer" />
        {health && (
          <span className="status-pill" title="Agent brains">
            <span className={"dot" + (live ? "" : " sim")} />
            {live ? `LLM: ${brains.join(" + ")}` : "LLM: simulated"}
            {" · "}emb: {health.embeddings} · db: {health.db?.mode}
            {health.observability?.configured ? " · braintrust ✓" : ""}
          </span>
        )}
      </header>

      <main className="main">
        {/* LiveVoice stays mounted (just hidden) so an in-progress call, its
            transcript and agent activity survive switching to another tab. */}
        <div style={{ display: tab === "voice" ? "block" : "none" }}>
          <LiveVoice onChange={refresh} />
        </div>
        {tab === "ops" && <LiveOps onChange={refresh} />}
        {tab === "scenarios" && <Scenarios go={setTab} onChange={refresh} />}
        {tab === "tower" && <ControlTower nonce={nonce} />}
        {tab === "registry" && <Registry nonce={nonce} />}
        {tab === "learn" && <Learning nonce={nonce} onChange={refresh} />}
        {tab === "kb" && <Knowledge nonce={nonce} />}
      </main>
      <DocViewer />
    </div>
  );
}
