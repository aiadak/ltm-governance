import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const STATUS_CLASS = {
  proposed: "Watch", reviewed: "Watch", tested: "Watch",
  deployed: "Healthy", rejected: "Flagged", failed: "Flagged",
};

// ---- the readable per-answer review card ----
function ReviewCard({ rv, presets, busy, onApply, onReject }) {
  const [instr, setInstr] = useState("");
  const [sel, setSel] = useState("");
  const open = rv.status === "open";
  const resolved = rv.status === "resolved";
  const srcVoice = rv.source === "voice";

  return (
    <div className={"rev " + rv.status}>
      <div className="row">
        <span className={"src-tag " + (srcVoice ? "voice" : "agent")}>
          {srcVoice ? "🎙 VOICE AI" : "⚙ " + (rv.agent_name || rv.agent)}
        </span>
        {rv.confidence != null && (
          <span className="mono muted" style={{ fontSize: 11 }}>was {Math.round(rv.confidence * 100)}% confident</span>
        )}
        <span className={"status-tag " + (open ? "Flagged" : resolved ? "Healthy" : "Watch")}
          style={{ marginLeft: "auto" }}>
          {open ? "NEEDS REVIEW" : resolved ? "TRAINED ✓" : "DISMISSED"}
        </span>
      </div>

      {rv.context && (
        <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>The customer said:
          <span style={{ color: "var(--text)" }}> "{rv.context}"</span></div>
      )}
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        {srcVoice ? "The Voice AI" : rv.agent_name || "The agent"} answered:
      </div>
      <div className="said">{rv.answer}</div>

      {open && (
        <>
          <div className="muted" style={{ fontSize: 13, margin: "12px 0 8px", color: "var(--text)" }}>
            <b>How should it answer instead?</b> Pick one, or write your own.
          </div>
          <div className="row" style={{ gap: 8, marginBottom: 10 }}>
            {presets.map((p) => (
              <span key={p.id} className={"preset-chip" + (sel === p.id ? " sel" : "")}
                onClick={() => { setSel(p.id); setInstr(p.instruction); }}>{p.label}</span>
            ))}
          </div>
          <textarea value={instr} placeholder="e.g. Make this crisper — one short sentence, then offer the next step."
            onChange={(e) => { setInstr(e.target.value); setSel(""); }} style={{ minHeight: 64, width: "100%" }} />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn sm" disabled={busy === rv.id || !instr.trim()}
              onClick={() => onApply(rv.id, instr)}>
              {busy === rv.id ? "Training…" : "✓ Apply & train"}
            </button>
            <button className="btn ghost sm" disabled={busy === rv.id}
              onClick={() => onReject(rv.id)}>Answer was fine — dismiss</button>
          </div>
        </>
      )}

      {resolved && (
        <div className="banner" style={{ marginTop: 10, borderColor: "#22402e" }}>
          ✓ Trained: <span style={{ color: "var(--text)" }}>"{rv.instruction}"</span> — applied to{" "}
          <b>{rv.target}</b> (now v{rv.new_version}). Future answers follow this.
        </div>
      )}
    </div>
  );
}

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
    ["4", "Human review", decision ? `${decision.toUpperCase()} by ${imp.human_decision.by}` : "awaiting human", reviewed],
    ["5", "Regression test", reg.total ? `${reg.passed}/${reg.total} cases pass` : "not run", tested],
    ["6", "New version", deployed ? `Voice AI v${imp.deployed_version}` : "not approved", deployed],
  ];
  return (
    <div className="flow">
      {steps.map(([n, h, body, done]) => (
        <div key={n} className={"stepbox" + (done ? " done" : "")}>
          <div className="n">STEP {n}{done ? " ✓" : ""}</div><h4>{h}</h4><p>{body}</p>
        </div>
      ))}
    </div>
  );
}

export default function Learning({ nonce, onChange }) {
  const [data, setData] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [presets, setPresets] = useState([]);
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState("");
  const [showAdv, setShowAdv] = useState(false);

  const load = () => Promise.all([
    api.learning().then(setData),
    api.reviews().then((d) => setReviews(d.reviews)),
  ]);
  useEffect(() => { load(); api.feedbackPresets().then((d) => setPresets(d.presets)).catch(() => {}); }, [nonce]);
  if (!data) return <div className="empty">Loading learning studio…</div>;

  const imps = data.improvements;
  const versions = data.versions || {};
  const learned = Object.entries(versions).filter(([, v]) => (v.version || 1) > 1);

  async function applyCorrection(id, instruction) {
    setBusy(id); await api.correct(id, instruction); await load(); onChange && onChange(); setBusy("");
  }
  async function rejectCorrection(id) {
    setBusy(id); await api.correct(id, "", "reject"); await load(); onChange && onChange(); setBusy("");
  }
  async function act(fn, id) { setBusy(id); await fn(); await load(); onChange && onChange(); setBusy(""); }
  const doReview = (id, action, addendum = "") => act(() => api.review(id, action, addendum), id);

  const openReviews = reviews.filter((r) => r.status === "open");
  const doneReviews = reviews.filter((r) => r.status !== "open");

  return (
    <div>
      <div className="view-head">
        <h1>Learning Studio</h1>
        <p>When you thumbs-down an answer anywhere in the app, it lands here. Tell the agent (or the
          Voice AI) how to do better — pick a quick fix or write your own — and it learns for next time.
          A human decides every change; no model fine-tuning.</p>
      </div>

      {/* ---- the main event: answers you flagged ---- */}
      <div className="section-title">To review · {openReviews.length} flagged answer{openReviews.length === 1 ? "" : "s"}</div>
      {openReviews.length === 0 && (
        <div className="card pad empty">
          Nothing to review. Thumbs-down any answer in <b>Live Voice</b>, <b>Live Ops</b> or
          <b> Scenarios</b> and it appears here for you to correct.
        </div>
      )}
      {openReviews.map((rv) => (
        <ReviewCard key={rv.id} rv={rv} presets={presets} busy={busy}
          onApply={applyCorrection} onReject={rejectCorrection} />
      ))}

      {/* ---- what the agents have learned so far ---- */}
      {learned.length > 0 && (
        <>
          <div className="section-title">What your agents have learned</div>
          <div className="card pad">
            {learned.map(([agent, v]) => (
              <div key={agent} style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
                <div className="row">
                  <span className="chip agent">{agent === "VA" ? "VOICE AI" : agent}</span>
                  <span className="ver">v{v.version}</span>
                  <span className="muted" style={{ fontSize: 12 }}>{(v.history || []).length} lesson(s) learned</span>
                </div>
                <ul style={{ margin: "8px 0 0", paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>
                  {(v.history || []).map((h, i) => <li key={i}>{h.delta || h.addendum}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}

      {doneReviews.length > 0 && (
        <>
          <div className="section-title">Recently trained</div>
          {doneReviews.slice(0, 6).map((rv) => (
            <ReviewCard key={rv.id} rv={rv} presets={presets} busy={busy}
              onApply={applyCorrection} onReject={rejectCorrection} />
          ))}
        </>
      )}

      {/* ---- advanced: the scripted governance pipeline (rental demo) ---- */}
      <div className="section-title" style={{ cursor: "pointer" }} onClick={() => setShowAdv(!showAdv)}>
        {showAdv ? "▾" : "▸"} Advanced · scripted governance pipeline &amp; eval cases
      </div>
      {showAdv && (
        <>
          {imps.length === 0 && (
            <div className="card pad empty">No scripted improvements yet. Play the LM-AUTO-88123 call in Live Ops.</div>
          )}
          {imps.map((imp) => (
            <div key={imp.id} className="card pad" style={{ marginBottom: 16 }}>
              <div className="row">
                <h3 style={{ margin: 0 }}>Improvement {imp.id}</h3>
                <span className="chip agent">{imp.proposed_fix?.target_agent || imp.agent}</span>
                <span className={"status-tag " + (STATUS_CLASS[imp.status] || "Watch")} style={{ marginLeft: "auto" }}>
                  {imp.status.toUpperCase()}</span>
              </div>
              <Flow imp={imp} />
              {imp.status === "proposed" && (
                <div className="row" style={{ marginTop: 12 }}>
                  <button className="btn sm" disabled={busy === imp.id} onClick={() => doReview(imp.id, "accept")}>✓ Accept</button>
                  <button className="btn ghost sm" disabled={busy === imp.id}
                    onClick={() => { setEditing(imp.id); setDraft(imp.proposed_fix?.addendum || ""); }}>✎ Edit</button>
                  <button className="btn ghost sm" disabled={busy === imp.id}
                    style={{ color: "var(--red)", borderColor: "var(--red)" }}
                    onClick={() => doReview(imp.id, "reject")}>✕ Reject</button>
                </div>
              )}
              {editing === imp.id && (
                <div className="field" style={{ marginTop: 10 }}>
                  <label>Edit the guardrail before approving</label>
                  <textarea value={draft} onChange={(e) => setDraft(e.target.value)} style={{ minHeight: 80 }} />
                  <div className="row" style={{ marginTop: 8 }}>
                    <button className="btn sm" onClick={async () => { await doReview(imp.id, "edit", draft); setEditing(null); }}>Save &amp; accept</button>
                    <button className="btn ghost sm" onClick={() => setEditing(null)}>Cancel</button>
                  </div>
                </div>
              )}
              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn ghost sm" disabled={busy === imp.id || !["reviewed", "tested"].includes(imp.status)}
                  onClick={() => act(() => api.runRegression(imp.id), imp.id)}>Run regression test</button>
                <button className="btn sm" disabled={busy === imp.id || imp.status !== "tested"}
                  onClick={() => act(() => api.approve(imp.id), imp.id)}>Approve &amp; deploy</button>
                {imp.status === "deployed" && <span className="muted" style={{ fontSize: 12 }}>Deployed as v{imp.deployed_version}.</span>}
              </div>
            </div>
          ))}
          <div className="section-title" style={{ fontSize: 13 }}>Synthetic evaluation cases</div>
          <div className="card" style={{ overflowX: "auto" }}>
            <table>
              <thead><tr><th>Case</th><th>Agent</th><th>Scenario</th><th>Expected</th></tr></thead>
              <tbody>
                {data.eval_cases.map((c) => (
                  <tr key={c.id}><td className="mono">{c.id}</td><td><span className="chip agent">{c.agent}</span></td>
                    <td>{c.scenario}</td><td className="muted">{c.expect}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
