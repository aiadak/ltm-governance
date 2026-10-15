import React, { useState, useRef } from "react";
import { api } from "../api.js";

export default function LiveOps({ onChange }) {
  const [policy, setPolicy] = useState("LM-AUTO-88123");
  const [playing, setPlaying] = useState(false);
  const [conv, setConv] = useState([]);
  const [fires, setFires] = useState([]);
  const [gov, setGov] = useState([]);
  const [meta, setMeta] = useState(null);
  const timers = useRef([]);

  function clearTimers() { timers.current.forEach(clearTimeout); timers.current = []; }

  async function play() {
    clearTimers();
    setConv([]); setFires([]); setGov([]); setMeta(null);
    setPlaying(true);
    let res;
    try { res = await api.runCall(policy); }
    catch (e) { setPlaying(false); return; }
    setMeta(res);
    const steps = res.steps;
    steps.forEach((s, i) => {
      const t = setTimeout(() => {
        if (s.kind === "caller") {
          setConv((c) => [...c, { who: "customer", text: s.text }]);
        } else if (s.kind === "agent" && s.speaker === "va") {
          const cls = s.flags && s.flags.length ? "err" : (s.text.toLowerCase().includes("correct") ? "corrected" : "va");
          setConv((c) => [...c, { who: "va", text: s.text, cls }]);
        }
        (s.fires || []).forEach((f) =>
          setFires((x) => [...x, { ...f, step: s.n }]));
        (s.governance || []).forEach((g) =>
          setGov((x) => [...x, { ...g, flags: s.flags, speaker: s.speaker }]));
        if (i === steps.length - 1) { setPlaying(false); onChange && onChange(); }
      }, i * 1150);
      timers.current.push(t);
    });
  }

  async function reset() {
    clearTimers(); setPlaying(false);
    await api.reset();
    setConv([]); setFires([]); setGov([]); setMeta(null);
    onChange && onChange();
  }

  return (
    <div>
      <div className="view-head">
        <h1>Live Claims Conversation</h1>
        <p>A LTM Insurance auto-accident call runs through the governed ecosystem. Watch the
          Voice AI talk to the customer (left), supporting agents fire (middle), and governance
          check every agent in real time (right).</p>
      </div>

      <div className="row" style={{ marginBottom: 16 }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>Policy on the call</label>
          <select value={policy} onChange={(e) => setPolicy(e.target.value)} disabled={playing}>
            <option value="LM-AUTO-88123">LM-AUTO-88123 — Prakash Iyer (NO rental coverage)</option>
            <option value="LM-AUTO-55900">LM-AUTO-55900 — Rob Castellano (HAS rental coverage)</option>
          </select>
        </div>
        <button className="btn" onClick={play} disabled={playing}>
          {playing ? "Call in progress…" : "▶ Play governed call"}
        </button>
        <button className="btn ghost sm" onClick={reset} disabled={playing}>Reset demo</button>
        {meta && (
          <span className="status-pill" style={{ marginLeft: "auto" }}>
            <span className={"dot" + (meta.llm_source === "simulated" ? " sim" : "")} />
            {meta.claim_id} · Voice AI v{meta.va_version} · {meta.llm_source === "simulated" ? "simulated brain" : meta.llm_source}
          </span>
        )}
      </div>

      <div className="ops">
        {/* conversation */}
        <div className="card">
          <div className="col-head"><h3>🎧 Voice AI ↔ Customer</h3><span className="tag">transcript</span></div>
          <div className="col-body">
            {conv.length === 0 && <div className="empty">Press play to start the call.</div>}
            {conv.map((m, i) => (
              <div key={i} className={"bubble " + (m.cls || m.who)}>
                <div className="who">{m.who === "va" ? "Voice AI" : "Customer"}</div>
                {m.text}
              </div>
            ))}
          </div>
        </div>

        {/* agents firing */}
        <div className="card">
          <div className="col-head"><h3>⚙ Supporting agents</h3><span className="tag">firing</span></div>
          <div className="col-body">
            {fires.length === 0 && <div className="empty">Agent activity appears here.</div>}
            {fires.map((f, i) => (
              <div key={i} className="fire">
                <div className="top">
                  <span className="chip agent">{f.agent}</span>
                  <span className="chip">{f.metric}</span>
                  <span className={"pass-badge " + (f.pass ? "ok" : "no")} style={{ marginLeft: "auto" }}>
                    {f.pass ? "PASS" : "FAIL"} {Math.round((f.score || 0) * 100)}
                  </span>
                </div>
                <div className="detail">{f.detail}</div>
              </div>
            ))}
          </div>
        </div>

        {/* governance */}
        <div className="card">
          <div className="col-head"><h3>🛡 Governance (real-time)</h3><span className="tag">audit</span></div>
          <div className="col-body">
            {gov.length === 0 && <div className="empty">Green checks and red flags appear here.</div>}
            {gov.map((g, i) => (
              <div key={i} className={"gov " + (g.pass ? "pass" : "fail")}>
                <div className="icn">{g.pass ? "✓" : "✕"}</div>
                <div>
                  <div className="who">{g.agent}</div>
                  <div>{g.label}</div>
                  {!g.pass && g.flags && g.flags.map((fl, k) => <div key={k} className="flag">⚑ {fl}</div>)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
