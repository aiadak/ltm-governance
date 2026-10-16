import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import LiveVoice from "./views/LiveVoice.jsx";
import ControlTower from "./views/ControlTower.jsx";
import Registry from "./views/Registry.jsx";
import Learning from "./views/Learning.jsx";
import Knowledge from "./views/Knowledge.jsx";
import DocViewer from "./components/DocViewer.jsx";

const TABS = [
  ["voice", "Live Voice"],
  ["tower", "Governance Command Center"],
  ["registry", "Agent Registry"],
  ["learn", "Learning Studio"],
  ["kb", "Knowledge Base"],
];

export default function App() {
  const [tab, setTab] = useState("voice");
  const [nonce, setNonce] = useState(0);

  useEffect(() => { api.health().catch(() => {}); }, []);
  const refresh = () => setNonce((n) => n + 1);

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">
          <span className="brand">LTM</span>
          <small>Governed Contact Center</small>
        </div>
        <nav className="nav">
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>
          ))}
        </nav>
        <span className="spacer" />
      </header>

      <main className="main">
        {/* LiveVoice stays mounted (just hidden) so an in-progress call, its
            transcript and agent activity survive switching to another tab. */}
        <div style={{ display: tab === "voice" ? "block" : "none" }}>
          <LiveVoice onChange={refresh} />
        </div>
        {tab === "tower" && <ControlTower nonce={nonce} />}
        {tab === "registry" && <Registry nonce={nonce} />}
        {tab === "learn" && <Learning nonce={nonce} onChange={refresh} />}
        {tab === "kb" && <Knowledge nonce={nonce} />}
      </main>
      <DocViewer />
    </div>
  );
}
