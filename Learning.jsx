import React, { useEffect, useState } from "react";
import { api } from "../api.js";

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

export default function Learning({ nonce, onChange }) {
  const [reviews, setReviews] = useState([]);
  const [presets, setPresets] = useState({ voice: [], agent: [] });
  const [busy, setBusy] = useState("");
  const [loaded, setLoaded] = useState(false);

  const load = () => api.reviews().then((d) => { setReviews(d.reviews); setLoaded(true); });
  useEffect(() => { load(); api.feedbackPresets().then((d) => setPresets({ voice: d.voice || [], agent: d.agent || [] })).catch(() => {}); }, [nonce]);
  const presetsFor = (rv) => (rv.source === "voice" ? presets.voice : presets.agent);
  if (!loaded) return <div className="empty">Loading learning studio…</div>;

  // what you've trained THIS session = resolved reviews from this session
  const sessionTrained = reviews.filter((r) => r.status === "resolved" && r.instruction);

  async function applyCorrection(id, instruction) {
    setBusy(id); await api.correct(id, instruction); await load(); onChange && onChange(); setBusy("");
  }
  async function rejectCorrection(id) {
    setBusy(id); await api.correct(id, "", "reject"); await load(); onChange && onChange(); setBusy("");
  }
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

    </div>
  );
}
