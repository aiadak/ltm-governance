import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Sources } from "../components/DocViewer.jsx";
import Thumbs from "../components/Thumbs.jsx";

// One seamless claims call that flows naturally through every scenario. Say these
// in order on LM-AUTO-88123 (Prakash Iyer); each line pulls the agent shown. The
// `section` labels group the flow so it reads as a single, real conversation.
const SCRIPT = [
  { section: "1 · Greeting & mood",
    say: "Hi… honestly it's been a rough morning and now I'm dealing with this too.",
    meta: "The Voice AI has already greeted you by name (\"Hi Prakash…\"). Sentiment reads the mood first → it acknowledges and stays calm. Policy is pulled up in the background." },

  { section: "2 · Report the accident (FNOL)",
    say: "I need to report an accident — I was in a pile-up on the highway this morning.",
    meta: "Voice AI: \"Let me pull that up…\" (filler) → asks first: is everyone okay? → FNOL agent starts intake" },
  { say: "Everyone's fine, thankfully.",
    meta: "Safety confirmed" },
  { say: "It was the 2021 Honda Civic.",
    meta: "Voice AI offered your two cars (Civic or Camry) → you confirm WHICH one" },
  { say: "Today, around 8:15 this morning, on the I-93 near exit 12.",
    meta: "Voice AI confirms the DATE, TIME and WHERE" },
  { say: "Three cars were involved — the car behind rear-ended me into the one ahead. Mine isn't drivable.",
    meta: "→ Triage (not drivable) + Fraud/SIU (3 vehicles → standard review, no accusation). Voice AI opens the claim and gives a CLM- reference." },
  { say: "Yes please, can you arrange the tow?",
    meta: "Roadside assistance IS on the policy → Voice AI arranges a tow to the preferred shop (grounded coverage use)" },
  { say: "Yes, the police came and filed a report.",
    meta: "Voice AI notes the police report on the claim" },

  { section: "3 · Coverage question → dispute",
    say: "Will I get a rental while it's in the shop? Last time someone said it's not covered — that can't be right.",
    meta: "→ Coverage agent re-checks (rental NOT on this policy) + Governance (any denial must cite the clause). Voice AI explains plainly, offers the out-of-pocket / preferred-vendor option, and escalates to a human adjuster if you push back — never overrides." },

  { section: "4 · Existing claim — status, repair, payment",
    say: "While I have you — what's the status of my earlier claim, CLM-2041?",
    meta: "→ Claim Status agent (in adjuster review, decision due in 2 business days)" },
  { say: "And roughly what will the repair on the Civic cost, and where do I take it?",
    meta: "→ Repair Estimate + Document agents — ballpark only until inspected, preferred shop Sterling Auto Body, no payout approved" },
  { say: "Also my reimbursement from that claim still hasn't shown up — it's been two weeks.",
    meta: "→ Payments + Exception agents ($1,900 issued 2 business days ago; 3–5 days to land)" },

  { section: "5 · Guardrail",
    say: "Can you just approve a $3,000 advance right now to tide me over?",
    meta: "→ Governance agent — Voice AI declines and routes the money decision to a human adjuster" },

  { section: "6 · Next steps & wrap-up",
    say: "Okay, what should I do next?",
    meta: "→ Next Best Action — walks two steps, then asks \"anything else I can help with?\"" },
  { say: "No, that's everything — thanks for your help.",
    meta: "Voice AI asks \"Shall I end the call?\" → closes warmly → Summarization agent writes the case summary" },
];

const LOW_CONF = 0.70;  // below this an answer is flagged for the Learning Studio
function confColor(c) {
  if (c < LOW_CONF) return "var(--red)";
  if (c < 0.85) return "var(--amber)";
  return "var(--green)";
}

// Live voice call with the claims Voice AI via OpenAI Realtime (WebRTC).
// The agent calls REAL supporting agents (Policy Verification, Triage, Next Best
// Action, Knowledge) as tools DURING the conversation, and governance checks each
// one live — so the supporting agents and governance are live while you talk.
export default function LiveVoice({ onChange }) {
  const [policy, setPolicy] = useState("LM-AUTO-88123");
  const [showScript, setShowScript] = useState(false);
  const [status, setStatus] = useState("idle"); // idle|connecting|live|ended|error
  const [error, setError] = useState("");
  const [transcript, setTranscript] = useState([]);
  const [fires, setFires] = useState([]);
  const [gov, setGov] = useState([]);
  const [available, setAvailable] = useState(null);
  const [vaVersion, setVaVersion] = useState(null);
  const [summary, setSummary] = useState(null);
  const [summarizing, setSummarizing] = useState(false);

  const pcRef = useRef(null);
  const dcRef = useRef(null);
  const micRef = useRef(null);
  const audioRef = useRef(null);
  const policyRef = useRef(policy);
  useEffect(() => { policyRef.current = policy; }, [policy]);
  // keep latest transcript/fires/status readable inside async + event callbacks
  const transcriptRef = useRef([]);
  const firesRef = useRef([]);
  const statusRef = useRef("idle");
  const summaryStarted = useRef(false);
  const callerTurns = useRef(0);   // counts caller turns so the first one opens the flow
  const firedKeys = useRef(new Set());  // agent+answer already shown this call → no repeats
  const lastMood = useRef("");          // sentiment fires on a mood CHANGE, not every turn
  // cockpit panes auto-scroll to the newest entry, so nothing needs manual scrolling
  const chatPane = useRef(null);
  const agentPane = useRef(null);
  const govPane = useRef(null);
  const toBottom = (r) => { if (r.current) r.current.scrollTo({ top: r.current.scrollHeight, behavior: "smooth" }); };
  useEffect(() => toBottom(chatPane), [transcript]);
  useEffect(() => toBottom(agentPane), [fires]);
  useEffect(() => toBottom(govPane), [gov]);
  useEffect(() => { transcriptRef.current = transcript; }, [transcript]);
  useEffect(() => { firesRef.current = fires; }, [fires]);
  useEffect(() => { statusRef.current = status; }, [status]);

  useEffect(() => {
    api.health().then((h) => setAvailable(!!h.realtime)).catch(() => setAvailable(false));
    return () => hangup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lastCustomer = useRef("");
  function addLine(who, text) {
    if (!text) return;
    if (who === "you") lastCustomer.current = text;
    setTranscript((t) => [...t, { who, text }]);
  }

  // Normalized agent-activity card: {agent, name, answer, confidence, metric, sources, ctx}.
  function pushFire(a) { setFires((x) => [...x, { ...a, fresh: true }]); }
  function pushGov(agent, g) { if (g) setGov((x) => [...x, { agent, ...g }]); }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ORCHESTRATOR for one caller turn, in real time and in order:
  //   1) Sentiment does a quick mood check FIRST — it only shows when the mood has
  //      actually spoiled (frustrated / rushed / confused); on a calm turn it's silent.
  //   2) Then the question's agent cluster fires ONE AT A TIME (staggered), so you
  //      see them pop up live as the Voice AI consults them — not all at once later.
  async function handleCallerTurn(text) {
    if (!text) return;
    const first = callerTurns.current === 0;
    callerTurns.current += 1;
    await runSentiment(text, first);   // mood agent FIRST (initial gauge on turn 1)
    await runTurn(text, first);        // then the cluster (policy pulled first on turn 1), staggered
  }

  async function runTurn(text, first) {
    let r;
    try { r = await api.voiceTurn(policyRef.current, text, first); }
    catch { return; }
    // Skip anything identical we've already shown this call — an agent repeating the
    // same card because the caller re-described the same thing is noise, not insight.
    const acts = (r.activities || []).filter((a) => {
      const k = a.agent + "|" + (a.answer || "").slice(0, 60);
      if (firedKeys.current.has(k)) return false;
      firedKeys.current.add(k);
      return true;
    });
    for (let i = 0; i < acts.length; i++) {
      const a = acts[i];
      pushFire({ agent: a.agent, name: a.name, answer: a.answer, confidence: a.confidence,
                 metric: a.metric, sources: a.sources || [], ctx: text });
      pushGov(a.agent, a.gov);
      if (i < acts.length - 1) await sleep(500);   // live, one-by-one
    }
  }

  // Sentiment runs first on every caller turn. On the FIRST turn it always shows (the
  // initial mood gauge). After that it only shows when the mood has spoiled (frustrated
  // / rushed / confused), with a pacify prompt for the agent — calm turns stay quiet.
  async function runSentiment(text, forceShow) {
    let res, data;
    try {
      res = await api.voiceTool(policyRef.current, "assess_sentiment", { text });
      data = JSON.parse(res.output || "{}");
    } catch { return; }
    const mood = (data.sentiment || "calm").toLowerCase();
    const notable = mood !== "calm" && mood !== "neutral";
    const changed = mood !== lastMood.current;
    lastMood.current = mood;
    // Show on the opening turn (initial gauge), or when the mood CHANGES to a notable
    // state. If they're still frustrated on the next turn, we don't nag with it again.
    if (!forceShow && !(notable && changed)) return;
    const d = res.display;
    if (d) {
      const answer = notable ? d.detail
        : "Initial mood check: caller sounds calm — proceed normally, warm and professional.";
      pushFire({ agent: "SEN", name: "Sentiment & Tone", answer, confidence: d.score,
                 metric: d.metric, sources: d.sources || [], ctx: text });
      pushGov("SEN", notable ? d.gov : { label: "Mood gauged — calm", pass: true });
    }
    const tone = data.tone_guidance;
    const dc = dcRef.current;
    if (notable && tone && dc && dc.readyState === "open") {
      dc.send(JSON.stringify({
        type: "conversation.item.create",
        item: { type: "message", role: "system",
                content: [{ type: "input_text", text: "[tone guidance] " + tone }] },
      }));
    }
    await sleep(350);   // let the mood card land before the rest of the cluster
  }

  // The Voice AI announced it's ending — give it a moment to finish speaking, then
  // actually hang up (which triggers the Summarization agent).
  function maybeAutoEnd(text) {
    if (/\b(i'?ll end the call|ending the call|end the call now)\b/i.test(text || "")) {
      setTimeout(() => { if (statusRef.current === "live") end(); }, 3500);
    }
  }

  // Summarization agent — runs once when the call ends.
  async function runSummary() {
    const turns = transcriptRef.current || [];
    if (turns.length === 0 || summaryStarted.current) return;
    summaryStarted.current = true;
    setSummarizing(true);
    try {
      const r = await api.summarize(policyRef.current, turns, firesRef.current || []);
      const d = r.display;
      if (d) {
        pushFire({ agent: "SUM", name: "Summarization", answer: d.detail, confidence: d.score,
                   metric: d.metric, sources: d.sources || [], ctx: "call" });
        pushGov("SUM", d.gov);
      }
      setSummary(r.summary || "");
    } catch { setSummary("Could not generate the summary."); }
    setSummarizing(false);
  }

  function handleEvent(raw) {
    let ev;
    try { ev = JSON.parse(raw); } catch { return; }
    switch (ev.type) {
      case "conversation.item.input_audio_transcription.completed":
        addLine("you", ev.transcript); handleCallerTurn(ev.transcript); break;
      case "response.output_audio_transcript.done":
      case "response.audio_transcript.done":
        addLine("agent", ev.transcript); maybeAutoEnd(ev.transcript || ""); break;
      case "error":
        setError(ev.error?.message || "Realtime error"); break;
      default: break;
    }
  }

  async function start() {
    setError(""); setTranscript([]); setFires([]); setGov([]);
    setSummary(null); summaryStarted.current = false; callerTurns.current = 0;
    firedKeys.current = new Set(); lastMood.current = "";
    setStatus("connecting");
    let tok;
    try { tok = await api.realtimeToken(policy); }
    catch { setStatus("error"); setError("Could not reach the server to start a call."); return; }
    if (tok.error || !tok.value) {
      setStatus("error");
      setError(tok.error || "No session token returned. Is OPENAI_API_KEY set on the server?");
      return;
    }
    setVaVersion(tok.va_version || 1);
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      micRef.current = mic;
      const pc = new RTCPeerConnection();
      pcRef.current = pc;
      pc.ontrack = (e) => {
        if (audioRef.current) { audioRef.current.srcObject = e.streams[0]; audioRef.current.play().catch(() => {}); }
      };
      mic.getTracks().forEach((tr) => pc.addTrack(tr, mic));

      const dc = pc.createDataChannel("oai-events");
      dcRef.current = dc;
      dc.onmessage = (e) => handleEvent(e.data);
      dc.onopen = () => {
        dc.send(JSON.stringify({
          type: "session.update",
          session: {
            type: "realtime",
            instructions: tok.instructions,
            // The supporting agents are orchestrated per caller turn by the browser
            // (runTurn → /api/voice/turn), so the model just holds the conversation —
            // it doesn't call tools itself (that only fired one agent at a time).
            tools: [],
            tool_choice: "none",
            audio: {
              input: {
                // Force English so the caller's speech is transcribed in English
                // (not auto-detected / translated into another script).
                transcription: { model: "whisper-1", language: "en" },
                // Near-field noise reduction filters room/background noise before VAD.
                noise_reduction: { type: "near_field" },
                // Less sensitive mic: high threshold + longer pause so small background
                // noise / bumps don't trigger the agent, but real speech still does.
                turn_detection: {
                  type: "server_vad",
                  threshold: 0.85,
                  prefix_padding_ms: 300,
                  silence_duration_ms: 950,
                  create_response: true,
                },
              },
            },
          },
        }));
        dc.send(JSON.stringify({ type: "response.create" }));
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const resp = await fetch("https://api.openai.com/v1/realtime/calls", {
        method: "POST", body: offer.sdp,
        headers: { Authorization: `Bearer ${tok.value}`, "Content-Type": "application/sdp" },
      });
      if (!resp.ok) throw new Error(`OpenAI call setup failed (${resp.status}): ${(await resp.text()).slice(0, 160)}`);
      await pc.setRemoteDescription({ type: "answer", sdp: await resp.text() });
      setStatus("live");
    } catch (e) {
      setStatus("error");
      setError(e.name === "NotAllowedError"
        ? "Microphone permission was blocked. Allow mic access and try again."
        : (e.message || "Could not start the call."));
      hangup();
    }
  }

  function hangup() {
    try { dcRef.current?.close(); } catch {}
    try { pcRef.current?.close(); } catch {}
    try { micRef.current?.getTracks().forEach((t) => t.stop()); } catch {}
    dcRef.current = null; pcRef.current = null; micRef.current = null;
  }
  function end() {
    hangup();
    setStatus((s) => (s === "live" || s === "connecting" ? "ended" : s));
    runSummary();  // fire the Summarization agent on the whole call
  }

  const live = status === "live";
  const connecting = status === "connecting";

  return (
    <div>
      <div className="view-head" style={{ marginBottom: 12 }}>
        <h1>Agent Cockpit — live call</h1>
        <p>Talk to the governed Voice AI. The conversation runs on the left; the supporting agents and
          governance checks fire on the right, live, as the call reaches each step.</p>
      </div>

      {available === false && (
        <div className="banner" style={{ marginBottom: 16, borderColor: "var(--amber)" }}>
          Live voice needs <b>OPENAI_API_KEY</b> set on the server. Add it in Vercel → Environment
          Variables and redeploy, then reload this page.
        </div>
      )}

      <div className="row" style={{ marginBottom: 16 }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>Policy the agent is handling</label>
          <select value={policy} onChange={(e) => setPolicy(e.target.value)} disabled={live || connecting}>
            <option value="LM-AUTO-88123">LM-AUTO-88123 — Prakash Iyer (NO rental coverage)</option>
            <option value="LM-AUTO-55900">LM-AUTO-55900 — Rob Castellano (HAS rental coverage)</option>
          </select>
        </div>
        {!live ? (
          <button className="btn" onClick={start} disabled={connecting || available === false}>
            {connecting ? "Connecting…" : "🎙 Start call"}
          </button>
        ) : (<button className="btn ghost" onClick={end}>■ End call</button>)}
        <span className="status-pill" style={{ marginLeft: "auto" }}>
          <span className={"dot" + (live ? "" : " sim")} />
          {live ? "LIVE — speak now" : connecting ? "connecting…" : status === "ended" ? "call ended" : "ready"}
          {vaVersion ? ` · Voice AI v${vaVersion}` : ""}
        </span>
      </div>

      {error && (
        <div className="banner" style={{ marginBottom: 16, borderColor: "var(--red)", color: "var(--text)" }}>{error}</div>
      )}

      <div className="cockpit">
        {/* ---------- chat window ---------- */}
        <div className="card chatwin">
          <div className="col-head">
            <span className={"live-dot" + (live ? " on" : "")} />
            <h3>Conversation</h3>
            <span className="tag">{policy}</span>
          </div>
          <div className="col-body chat-body" ref={chatPane}>
            {transcript.length === 0 && (
              <div className="empty">{live ? "Listening… say hello, or ask about your claim." : "Press Start and begin talking."}</div>
            )}
            {transcript.map((m, i) => (
              <div key={i} className={"msg " + (m.who === "you" ? "me" : "ai")}>
                <div className="avatar">{m.who === "you" ? "P" : "AI"}</div>
                <div className={"bubble " + (m.who === "you" ? "customer" : "va")}>
                  <div className="who" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                    <span>{m.who === "you" ? "Caller" : "Voice AI"}</span>
                    {m.who !== "you" && (
                      <Thumbs key={"vb" + i + (m.text || "").length} source="voice" agent="VA" agentName="Voice AI"
                        context={lastCustomer.current} answer={m.text} onFlag={onChange} />
                    )}
                  </div>
                  {m.text}
                </div>
              </div>
            ))}
            {live && <div className="listening"><span /><span /><span /> listening</div>}
          </div>
        </div>

        {/* ---------- agent cockpit (right rail) ---------- */}
        <div className="rail">
        <div className="card agentwin">
          <div className="col-head"><h3>⚙ Agents firing</h3><span className="tag">{fires.length} fired</span></div>
          <div className="col-body" ref={agentPane}>
            {fires.length === 0 && <div className="empty">Agents appear here live, as the call reaches each step.</div>}
            {fires.map((f, i) => (
              <div key={i} className={"fire" + (f.fresh ? " fire-in" : "")}>
                <div className="top">
                  <span className="chip agent">{f.agent}</span>
                  <span className="chip">{f.name || f.agent}</span>
                  <span className="mono" style={{ marginLeft: "auto", color: confColor(f.confidence || 0) }}>
                    conf {Math.round((f.confidence || 0) * 100)}%
                  </span>
                </div>
                <div className="detail" style={{ color: "var(--text)" }}>{f.answer}</div>
                <div className="row" style={{ justifyContent: "space-between", marginTop: 7, alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center" }}>
                    <span className="meter" style={{ width: 110 }}>
                      <span style={{ width: Math.round((f.confidence || 0) * 100) + "%", background: confColor(f.confidence || 0) }} />
                    </span>
                    {(f.confidence || 0) < LOW_CONF && <span className="flag" style={{ marginLeft: 8 }}>low confidence</span>}
                    <span style={{ marginLeft: 8 }}><Sources list={f.sources} /></span>
                  </span>
                  <Thumbs key={"af" + i} source="agent" agent={f.agent} agentName={f.name || f.agent}
                    context={f.ctx || lastCustomer.current} answer={f.answer} confidence={f.confidence} onFlag={onChange} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card govwin">
          <div className="col-head"><h3>🛡 Governance</h3><span className="tag">{gov.length} checks</span></div>
          <div className="col-body" ref={govPane}>
            {gov.length === 0 && <div className="empty">Green checks / red flags appear here.</div>}
            {gov.map((g, i) => (
              <div key={i} className={"gov " + (g.pass ? "pass" : "fail") + (g.severity === "warn" ? " warn" : "")}>
                <div className="icn">{!g.pass ? "✕" : g.severity === "warn" ? "⚑" : "✓"}</div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="row" style={{ gap: 6, alignItems: "center" }}>
                    <span className="who">{g.agent}</span>
                    {g.guardrail && <span className="gov-guard">{g.guardrail}</span>}
                    {g.ref && <span className="cite" style={{ marginLeft: "auto" }}
                      onClick={() => { window.location.hash = "doc=" + g.ref; }}>{g.ref}</span>}
                  </div>
                  <div style={{ marginTop: 3 }}>{g.label}</div>
                  {g.evidence && <div className="gov-evidence">{g.evidence}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
        </div>{/* /rail */}
      </div>

      {(summarizing || summary) && (
        <div className="card pad" style={{ marginTop: 14 }}>
          <div className="col-head">
            <h3>📝 Call summary <span className="muted" style={{ fontSize: 12 }}>· Summarization agent</span></h3>
            <span className="tag">case file</span>
          </div>
          {summarizing
            ? <div className="empty">Summarizing the call…</div>
            : <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.55, marginTop: 8 }}>{summary}</div>}
        </div>
      )}

      <div className="card pad" style={{ marginTop: 14 }}>
        <div className="row" style={{ cursor: "pointer" }} onClick={() => setShowScript(!showScript)}>
          <h3 style={{ margin: 0 }}>{showScript ? "▾" : "▸"} 🎬 Demo script — say these in order</h3>
          <span className="muted" style={{ fontSize: 12 }}>on LM-AUTO-88123 (no rental), each line triggers an agent</span>
        </div>
        {showScript && (
          <>
            <div style={{ marginTop: 10 }}>
              {SCRIPT.map((s, i) => (
                <React.Fragment key={i}>
                  {s.section && (
                    <div className="script-section" style={{
                      fontSize: 12, fontWeight: 600, color: "var(--coral)",
                      margin: i === 0 ? "0 0 8px" : "16px 0 8px", letterSpacing: ".02em" }}>
                      {s.section}
                    </div>
                  )}
                  <div className="script-step">
                    <div className="script-n">{i + 1}</div>
                    <div>
                      <div className="script-say">"{s.say}"</div>
                      <div className="script-meta">{s.meta}</div>
                    </div>
                  </div>
                </React.Fragment>
              ))}
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
              Each agent that fires shows a <span className="cite" style={{ cursor: "default" }}>DOC-ID</span>{" "}
              citation — click it to open the exact source document section it used.
            </div>
          </>
        )}
      </div>

      <audio ref={audioRef} autoPlay />
    </div>
  );
}
