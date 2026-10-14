import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const STATUS_CLASS = {
  proposed: "Watch", reviewed: "Watch", tested: "Watch",
  deployed: "Healthy", rejected: "Flagged", failed: "Flagged",
};

function Flow({ imp }) {
  const reg = imp.regression || { total: 0, passed: 0 };
  const reviewed = ["reviewed", "tested", "deployed"].includes(imp.status);
  const tested = ["tested", "deployed"].includes(imp.status);
  const deployed = imp.status === "deployed";
  const decision = imp.human_decision?.action;
  const steps = [
    ["1", "Detected error", imp.error, true],
    ["2", "Root cause", imp.root_cause, true],
    ["3", "Proposed fix", imp.proposed_fix?.addendum, true],
    ["4", "Human review (HITL)",
      decision ? `${decision.toUpperCase()} by ${imp.human_decision.by}` : "awaiting human decision",
      reviewed],
    ["5", "Regression test", reg.total ? `${reg.passed}/${reg.total} synthetic cases pass` : "not run yet", tested],
    ["6", "New version", deployed ? `Voice AI v${imp.deployed_version} deployed` : "not yet approved", deployed],
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
  const [editing, setEditing] = useState(null); // improvement id being edited
  const [draft, setDraft] = useState("");
  const load = () => api.learning().then(setData);
  useEffect(() => { load(); }, [nonce]);
  if (!data) return <div className="empty">Loading learning studio…</div>;

  const imps = data.improvements;
  const vaHist = data.versions?.VA;

  async function act(fn, id) { setBusy(id); await fn(); await load(); onChange && onChange(); setBusy(""); }
  const doReview = (id, action, addendum = "") => act(() => api.review(id, action, addendum), id);
  const doRegression = (id) => act(() => api.runRegression(id), id);
  const doApprove = (id) => act(() => api.approve(id), id);

  function startEdit(imp) { setEditing(imp.id); setDraft(imp.proposed_fix?.addendum || ""); }
  async function saveEdit(id) { await doReview(id, "edit", draft); setEditing(null); }

  return (
    <div>
      <div className="view-head">
        <h1>Continuous Learning Studio</h1>
        <p>The closed loop. A detected error becomes a proposed fix, a <b>human</b> accepts / edits /
          rejects it, a regression test gates it, and only then does it ship as a new agent version.
          Learning proposes; a human + governance approve. No model fine-tuning.</p>
      </div>

      <div className="banner" style={{ marginBottom: 16 }}>
        <b>Human-in-the-loop + decoupled:</b> the system never deploys its own fix. A person must
        Accept, Edit, or Reject it, and only a human-accepted, regression-passing fix can be deployed.
      </div>

      {/* Recursive learning: version history + accumulated memory */}
      {vaHist && (
        <div className="card pad" style={{ marginBottom: 16 }}>
          <div className="row">
            <h3 style={{ margin: 0 }}>Voice AI — learning history</h3>
            <span className="ver" style={{ marginLeft: "auto" }}>current: v{vaHist.version}</span>
          </div>
          <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <span className="status-tag Healthy">v1 — baseline</span>
            {(vaHist.history || []).map((h, i) => (
              <React.Fragment key={i}>
                <span className="muted">→</span>
                <span className="status-tag Healthy" title={h.delta || h.addendum}>
                  v{h.to} — learned fix
                </span>
              </React.Fragment>
            ))}
          </div>
          {vaHist.prompt_addendum && (
            <>
              <div className="section-title" style={{ fontSize: 13, margin: "14px 0 6px" }}>
                Accumulated agent memory (applied to the Voice AI)
              </div>
              <div className="banner mono" style={{ fontSize: 12, whiteSpace: "pre-wrap", color: "var(--muted)" }}>
                {vaHist.prompt_addendum}
              </div>
            </>
          )}
        </div>
      )}

      {imps.length === 0 && (
        <div className="card pad empty">
          No improvements yet. Run the <b>LM-AUTO-88123</b> call in Live Ops — the caught rental
          over-promise is captured here for human review.
        </div>
      )}

      {imps.map((imp) => (
        <div key={imp.id} className="card pad" style={{ marginBottom: 16 }}>
          <div className="row">
            <h3 style={{ margin: 0 }}>Improvement {imp.id}</h3>
            <span className="chip agent">{imp.proposed_fix?.target_agent || imp.agent}</span>
            <span className="chip">{imp.guardrail}</span>
            <span className={"status-tag " + (STATUS_CLASS[imp.status] || "Watch")}
              style={{ marginLeft: "auto" }}>{imp.status.toUpperCase()}</span>
          </div>
          <Flow imp={imp} />

          {/* HITL review controls */}
          {imp.status === "proposed" && (
            <div className="card pad" style={{ marginTop: 14, background: "var(--bg-2)" }}>
              <div className="row" style={{ marginBottom: editing === imp.id ? 10 : 0 }}>
                <b style={{ fontSize: 13 }}>👤 Human-in-the-loop review</b>
                <span className="muted" style={{ fontSize: 12 }}>Accept the proposed fix, edit it, or reject it.</span>
              </div>
              {editing === imp.id ? (
                <div className="field">
                  <label>Edit the proposed guardrail before approving</label>
                  <textarea value={draft} onChange={(e) => setDraft(e.target.value)} style={{ minHeight: 90 }} />
                  <div className="row" style={{ marginTop: 8 }}>
                    <button className="btn sm" disabled={busy === imp.id} onClick={() => saveEdit(imp.id)}>Save edit &amp; accept</button>
                    <button className="btn ghost sm" onClick={() => setEditing(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div className="row">
                  <button className="btn sm" disabled={busy === imp.id} onClick={() => doReview(imp.id, "accept")}>✓ Accept</button>
                  <button className="btn ghost sm" disabled={busy === imp.id} onClick={() => startEdit(imp)}>✎ Edit</button>
                  <button className="btn ghost sm" disabled={busy === imp.id}
                    style={{ color: "var(--red)", borderColor: "var(--red)" }}
                    onClick={() => doReview(imp.id, "reject")}>✕ Reject</button>
                </div>
              )}
            </div>
          )}

          {imp.human_decision && (
            <div className="row" style={{ marginTop: 12 }}>
              <span className="pass-badge ok">HITL: {imp.human_decision.action.toUpperCase()}</span>
              <span className="muted" style={{ fontSize: 12 }}>by {imp.human_decision.by}</span>
              {imp.proposed_fix?.original_addendum &&
                <span className="muted" style={{ fontSize: 12 }}>(fix was edited by the human)</span>}
            </div>
          )}

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
            <button className="btn ghost sm"
              disabled={busy === imp.id || !["reviewed", "tested"].includes(imp.status)}
              onClick={() => doRegression(imp.id)}>
              {busy === imp.id ? "Running…" : "Run regression test"}
            </button>
            <button className="btn sm" disabled={busy === imp.id || imp.status !== "tested"}
              onClick={() => doApprove(imp.id)}>
              Approve &amp; deploy new version
            </button>
            {imp.status === "proposed" && <span className="muted" style={{ fontSize: 12 }}>A human must review (above) before testing.</span>}
            {imp.status === "reviewed" && <span className="muted" style={{ fontSize: 12 }}>Accepted — run the regression test to unlock deploy.</span>}
            {imp.status === "rejected" && <span className="muted" style={{ fontSize: 12 }}>Rejected by the human reviewer — not deployed.</span>}
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
