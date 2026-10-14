import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import Thumbs from "../components/Thumbs.jsx";

function confColor(c, low) {
  if (c < low) return "var(--red)";
  if (c < 0.85) return "var(--amber)";
  return "var(--green)";
}

export default function Scenarios({ go, onChange }) {
  const [list, setList] = useState(null);
  const [low, setLow] = useState(0.7);
  const [active, setActive] = useState(null);
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.scenarios().then((d) => { setList(d.scenarios); setLow(d.low_conf); });
  }, []);

  async function play(id) {
    setActive(id); setBusy(true);
    const r = await api.runScenario(id);
    setRun(r); setBusy(false);
  }

  if (!list) return <div className="empty">Loading scenarios…</div>;

  return (
    <div>
      <div className="view-head">
        <h1>Scenarios — run &amp; train</h1>
        <p>Pick a claim situation. The supporting agents answer with a <b>confidence score</b>. If
          you're not satisfied, send it to the Learning Studio — the low-confidence answers go to the
          top of the human-in-the-loop queue for correction, and the agent learns.</p>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "340px 1fr", gap: 14, alignItems: "start" }}>
        {/* scenario list */}
        <div className="card">
          <div className="col-head"><h3>Claim scenarios</h3><span className="tag">{list.length}</span></div>
          <div style={{ maxHeight: 620, overflowY: "auto" }}>
            {list.map((s, i) => (
              <div key={s.id} onClick={() => play(s.id)}
                style={{ padding: "11px 15px", borderBottom: "1px solid var(--line)", cursor: "pointer",
                         background: active === s.id ? "var(--bg-3)" : "transparent" }}>
                <div className="row" style={{ gap: 8 }}>
                  <span className="mono muted" style={{ fontSize: 11 }}>{i + 1}</span>
                  <b style={{ fontSize: 13 }}>{s.title}</b>
                </div>
                <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>"{s.utterance}"</div>
                <div className="pill-roles" style={{ marginTop: 6 }}>
                  {s.agents.map((a, k) => <span key={k} className="role-pill">{a}</span>)}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* run result */}
        <div>
          {!run && <div className="card pad empty">Pick a scenario on the left to run it.</div>}
          {run && (
            <div className="card pad">
              <div className="row">
                <span className="chip">{run.customer}</span>
                <h3 style={{ margin: 0 }}>{run.title}</h3>
              </div>
              <div className="bubble customer" style={{ marginTop: 10, maxWidth: "100%" }}>
                <div className="who">Customer · {run.customer}</div>{run.utterance}
              </div>
              <div className="muted" style={{ fontSize: 12, margin: "10px 0 4px" }}>Goal: {run.goal}</div>

              <div className="section-title" style={{ fontSize: 13, margin: "14px 0 8px" }}>Agent activity</div>
              <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                👍 if the answer is good, 👎 to send that answer to the Learning Studio for a fix.
              </div>
              <div className="grid" style={{ gap: 8 }}>
                {run.activities.map((a, i) => (
                  <div key={i} className="fire">
                    <div className="top">
                      <span className="chip agent">{a.agent}</span>
                      <span className="chip">{a.name}</span>
                      <span className="mono" style={{ marginLeft: "auto", color: confColor(a.confidence, low) }}>
                        conf {Math.round(a.confidence * 100)}%
                      </span>
                    </div>
                    <div className="detail" style={{ color: "var(--text)" }}>{a.answer}</div>
                    <div className="row" style={{ marginTop: 7, justifyContent: "space-between" }}>
                      <span>
                        <span className="meter" style={{ width: 120 }}>
                          <span style={{ width: Math.round(a.confidence * 100) + "%", background: confColor(a.confidence, low) }} />
                        </span>
                        {a.confidence < low && <span className="flag" style={{ marginLeft: 8 }}>low confidence</span>}
                      </span>
                      <Thumbs source="agent" agent={a.agent} agentName={a.name}
                        context={run.utterance} answer={a.answer} confidence={a.confidence}
                        scenarioId={run.scenario_id} onFlag={onChange} />
                    </div>
                  </div>
                ))}
              </div>
              <div className="banner" style={{ marginTop: 12 }}>
                Flagged an answer? Open the <a href="#" onClick={(e) => { e.preventDefault(); go && go("learn"); }}
                  style={{ color: "var(--coral)" }}>Learning Studio →</a> to correct it (make it crisper,
                cite the clause, etc.) and the agent learns.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
