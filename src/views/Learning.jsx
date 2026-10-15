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
            <b>{srcVoice ? "How should it say it instead?" : "How should this agent behave — what did you expect?"}</b>{" "}
            Pick one, or write your own.
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
  const [presets, setPresets] = useState({ voice: [], agent: [] });
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState("");
  const [showAdv, setShowAdv] = useState(false);

  const load = () => Promise.all([
    api.learning().then(setData),
    api.reviews().then((d) => setReviews(d.reviews)),
  ]);
  useEffect(() => { load(); api.feedbackPresets().then((d) => setPresets({ voice: d.voice || [], agent: d.agent || [] })).catch(() => {}); }, [nonce]);
  const presetsFor = (rv) => (rv.source === "voice" ? presets.voice : presets.agent);
  if (!data) return <div className="empty">Loading learning studio…</div>;

  const imps = data.improvements;
  // what you've trained THIS session = resolved reviews from this session
  const sessionTrained = reviews.filter((r) => r.status === "resolved" && r.instruction);

  async function applyCorrection(id, instruction) {
    setBusy(id); await api.correct(id, instruction); await load(); onChange && onChange(); setBusy("");
  }
  async function rejectCorrection(id) {
    setBusy(id); await api.correct(id, "", "reject"); await load(); onChange && onChange(); setBusy("");
  }
  async function act(fn, id) { setBusy(id); await fn(); await load(); onChange && onChange(); setBusy(""); }
  const doReview = (id, action, addendum = "") => act(() => api.review(id, action, addendum), id);
  async function clearAll() {
    if (!window.confirm("Clear the learning queue and reset what the agents have learned? This can't be undone.")) return;
    setBusy("clear"); await api.clearLearning(); await load(); onChange && onChange(); setBusy("");
  }

  const openReviews = reviews.filter((r) => r.status === "open");
  const voiceReviews = openReviews.filter((r) => r.source === "voice");
  const agentReviews = openReviews.filter((r) => r.source !== "voice");

  return (
    <div>
      <div className="view-head">
        <h1>Learning Studio</h1>
        <p>When you thumbs-down an answer anywhere in the app, it lands here. There are two separate
          queues: the <b>Voice AI replies</b> (fix how it answers) and the <b>supporting agents</b>
          (fix how they behave). A human decides every change; no model fine-tuning.</p>
      </div>

      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="section-title">To review · {openReviews.length} flagged{openReviews.length === 1 ? "" : "s"}</div>
        {reviews.length > 0 && (
          <button className="btn ghost sm" disabled={busy === "clear"} onClick={clearAll}
            style={{ color: "var(--muted)" }}>Clear all</button>
        )}
      </div>

      {openReviews.length === 0 && (
        <div className="card pad empty">
          Nothing to review yet. Thumbs-down a <b>Voice AI reply</b> or an <b>agent</b> in Live Voice
          or Scenarios and it appears here for you to correct. (Starts blank each session.)
        </div>
      )}

      {/* ---- queue 1: Voice AI messages ---- */}
      {voiceReviews.length > 0 && (
        <>
          <div className="section-title" style={{ marginTop: 18 }}>
            🎙 Voice AI replies to fix · {voiceReviews.length}
          </div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            For each reply you flagged: see what the customer asked and what it said, then tell it how it
            should have answered (edit the wording or add a comment) and approve.
          </div>
          {voiceReviews.map((rv) => (
            <ReviewCard key={rv.id} rv={rv} presets={presetsFor(rv)} busy={busy}
              onApply={applyCorrection} onReject={rejectCorrection} />
          ))}
        </>
      )}

      {/* ---- queue 2: supporting-agent behavior ---- */}
      {agentReviews.length > 0 && (
        <>
          <div className="section-title" style={{ marginTop: 18 }}>
            ⚙ Agent behavior to review · {agentReviews.length}
          </div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            For each agent you flagged: check whether it followed the right flow / acted properly, say what
            you expected, and approve so the agent learns.
          </div>
          {agentReviews.map((rv) => (
            <ReviewCard key={rv.id} rv={rv} presets={presetsFor(rv)} busy={busy}
              onApply={applyCorrection} onReject={rejectCorrection} />
          ))}
        </>
      )}

      {/* ---- what you've trained THIS session ---- */}
      {sessionTrained.length > 0 && (
        <>
          <div className="section-title">Trained this session · {sessionTrained.length}</div>
          <div className="card pad">
            {sessionTrained.map((r) => (
              <div key={r.id} style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
                <div className="row">
                  <span className={"src-tag " + (r.source === "voice" ? "voice" : "agent")}>
                    {r.source === "voice" ? "🎙 VOICE AI" : "⚙ " + (r.agent_name || r.agent)}
                  </span>
                  <span className="ver">{r.target} v{r.new_version}</span>
                </div>
                <div style={{ fontSize: 13, marginTop: 6 }}>
                  You taught it: <span className="muted">"{r.instruction}"</span>
                </div>
              </div>
            ))}
          </div>
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
