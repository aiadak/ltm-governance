import React, { useEffect, useState } from "react";
import { api } from "../api.js";

function Flow({ imp }) {
  const reg = imp.regression || { total: 0, passed: 0 };
  const tested = imp.status === "tested" || imp.status === "deployed";
  const deployed = imp.status === "deployed";
  const steps = [
    ["1", "Detected error", imp.error, true],
    ["2", "Root cause", imp.root_cause, true],
    ["3", "Human correction", imp.correction, true],
    ["4", "Proposed fix", imp.proposed_fix?.addendum, true],
    ["5", "Regression test", reg.total ? `${reg.passed}/${reg.total} synthetic cases pass` : "not run yet", tested],
    ["6", "New version", deployed ? `Voice AI v${imp.deployed_version} deployed` : "awaiting approval", deployed],
  ];
  return (
    <div className="flow">
      {steps.map(([n, h, body, done]) => (
        <div key={n} className={"stepbox" + (done ? " done" : "")}>
          <div className="n">STEP {n}{done ? " ✓" : ""}</div>
          <h4>{h}</h4>
          <p>{body}</p>
        </div>
      ))}
    </div>
  );
}

export default function Learning({ nonce, onChange }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState("");
  const load = () => api.learning().then(setData);
  useEffect(() => { load(); }, [nonce]);
  if (!data) return <div className="empty">Loading learning studio…</div>;

  const imps = data.improvements;

  async function doRegression(id) { setBusy(id); await api.runRegression(id); await load(); onChange && onChange(); setBusy(""); }
  async function doApprove(id) { setBusy(id); await api.approve(id); await load(); onChange && onChange(); setBusy(""); }

  return (
    <div>
      <div className="view-head">
        <h1>Continuous Learning Studio</h1>
        <p>The closed loop. A human correction becomes a proposed prompt/retrieval fix, is gated by a
          regression test on synthetic cases, and — only on explicit approval — ships as a new agent
          version. Learning proposes; governance approves. No model fine-tuning.</p>
      </div>

      <div className="banner" style={{ marginBottom: 16 }}>
        Learning is <b>decoupled</b> from governance by design — agents never grade their own homework.
        The approve step is the governance gate.
      </div>

      {imps.length === 0 && (
        <div className="card pad empty">
          No improvements yet. Run the <b>LM-AUTO-88123</b> call in Live Ops — the caught rental
          over-promise will be captured here as a proposed improvement.
        </div>
      )}

      {imps.map((imp) => (
        <div key={imp.id} className="card pad" style={{ marginBottom: 16 }}>
          <div className="row">
            <h3 style={{ margin: 0 }}>Improvement {imp.id}</h3>
            <span className="chip agent">{imp.proposed_fix?.target_agent || imp.agent}</span>
            <span className="chip">{imp.guardrail}</span>
            <span className={"status-tag " + (imp.status === "deployed" ? "Healthy" : imp.status === "tested" ? "Watch" : "Flagged")}
              style={{ marginLeft: "auto" }}>{imp.status.toUpperCase()}</span>
          </div>
          <Flow imp={imp} />

          {imp.regression?.cases?.length > 0 && (
            <>
              <div className="section-title" style={{ fontSize: 13, margin: "16px 0 8px" }}>Regression cases</div>
              <div className="grid" style={{ gap: 8 }}>
                {imp.regression.cases.map((c) => (
                  <div key={c.id} className="reg-case">
                    <span className="pass-badge ok">PASS</span>
                    <div>
                      <div className="mono muted" style={{ fontSize: 11 }}>{c.id}</div>
                      <div style={{ fontSize: 13 }}>{c.scenario}</div>
                      <div className="muted" style={{ fontSize: 12 }}>Expected: {c.expect}</div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn ghost sm" disabled={busy === imp.id || imp.status === "deployed"}
              onClick={() => doRegression(imp.id)}>
              {busy === imp.id ? "Running…" : "Run regression test"}
            </button>
            <button className="btn sm" disabled={busy === imp.id || imp.status !== "tested"}
              onClick={() => doApprove(imp.id)}>
              Approve &amp; deploy new version
            </button>
            {imp.status === "proposed" && <span className="muted" style={{ fontSize: 12 }}>Run the regression test before approval is unlocked.</span>}
            {imp.status === "deployed" && <span className="muted" style={{ fontSize: 12 }}>Deployed. Re-play the call in Live Ops — the Voice AI now answers correctly.</span>}
          </div>
        </div>
      ))}

      <div className="section-title">Synthetic evaluation cases</div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table>
          <thead><tr><th>Case</th><th>Agent</th><th>Scenario</th><th>Expected behaviour</th></tr></thead>
          <tbody>
            {data.eval_cases.map((c) => (
              <tr key={c.id}><td className="mono">{c.id}</td><td><span className="chip agent">{c.agent}</span></td>
                <td>{c.scenario}</td><td className="muted">{c.expect}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
