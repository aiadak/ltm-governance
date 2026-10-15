import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Sources } from "../components/DocViewer.jsx";
import Thumbs from "../components/Thumbs.jsx";

// What to say, in order, to trigger each agent — shown on screen as a talk track.
const SCRIPT = [
  { say: "Honestly I'm really frustrated — I've called three times and nobody has helped me!",
    meta: "→ assess_sentiment (Sentiment) detects frustration → Voice AI pacifies, lets you vent" },
  { say: "Hi, I was just in a car accident — I was rear-ended at a stoplight.",
    meta: "Voice AI greets, starts intake" },
  { say: "The front bumper and hood are damaged, but no one's hurt and I can still drive it.",
    meta: "→ create_claim (opens a claim) + assess_severity (Triage)" },
  { say: "Will my rental car be covered while it's in the shop?",
    meta: "→ verify_policy_coverage (Policy Verification) → governance confirms grounded" },
  { say: "What are my next steps?",
    meta: "→ recommend_next_action (Next Best Action) — refuses any payout" },
  { say: "Do you have an article explaining how rental coverage works?",
    meta: "→ search_knowledge (Knowledge Retrieval) pulls the FAQ" },
  { say: "Can you just approve a $3,000 payout right now?",
    meta: "Voice AI declines and routes to a human adjuster (guardrail)" },
];

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

  const pcRef = useRef(null);
  const dcRef = useRef(null);
  const micRef = useRef(null);
  const audioRef = useRef(null);
  const policyRef = useRef(policy);
  useEffect(() => { policyRef.current = policy; }, [policy]);

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

  async function runToolCall(name, call_id, argStr) {
    let args = {};
    try { args = argStr ? JSON.parse(argStr) : {}; } catch {}
    let res;
    try { res = await api.voiceTool(policyRef.current, name, args); }
    catch { res = { output: JSON.stringify({ error: "tool failed" }), display: null }; }
    if (res.display) {
      setFires((x) => [...x, { ...res.display }]);
      if (res.display.gov) setGov((x) => [...x, { agent: res.display.agent, ...res.display.gov }]);
    }
    const dc = dcRef.current;
    if (dc && dc.readyState === "open") {
      dc.send(JSON.stringify({
        type: "conversation.item.create",
        item: { type: "function_call_output", call_id, output: res.output },
      }));
      dc.send(JSON.stringify({ type: "response.create" }));
    }
  }

  // Run the Sentiment agent once per caller turn (it reads the words). Only SURFACE
  // it and nudge the Voice AI's tone when the mood is actually notable (frustrated /
  // in a hurry / confused). On a plain "hi" it stays quiet — no SOP, no noise. The
  // model itself no longer has this tool, so it can't double-fire.
  async function runSentiment(text) {
    if (!text) return;
    let res, data;
    try {
      res = await api.voiceTool(policyRef.current, "assess_sentiment", { text });
      data = JSON.parse(res.output || "{}");
    } catch { return; }
    const mood = (data.sentiment || "calm").toLowerCase();
    if (mood === "calm" || mood === "neutral") return;  // regular call — don't manage tone
    if (res.display) {
      setFires((x) => [...x, { ...res.display }]);
      if (res.display.gov) setGov((x) => [...x, { agent: "SEN", ...res.display.gov }]);
    }
    const tone = data.tone_guidance;
    const dc = dcRef.current;
    if (tone && dc && dc.readyState === "open") {
      dc.send(JSON.stringify({
        type: "conversation.item.create",
        item: { type: "message", role: "system",
                content: [{ type: "input_text", text: "[tone guidance] " + tone }] },
      }));
    }
  }

  function handleEvent(raw) {
    let ev;
    try { ev = JSON.parse(raw); } catch { return; }
    switch (ev.type) {
      case "conversation.item.input_audio_transcription.completed":
        addLine("you", ev.transcript); runSentiment(ev.transcript); break;
      case "response.output_audio_transcript.done":
      case "response.audio_transcript.done":
        addLine("agent", ev.transcript); break;
      case "response.done": {
        const out = ev.response?.output || [];
        out.filter((it) => it.type === "function_call").forEach((it) => {
          runToolCall(it.name, it.call_id, it.arguments);
        });
        break;
      }
      case "error":
        setError(ev.error?.message || "Realtime error"); break;
      default: break;
    }
  }

  async function start() {
    setError(""); setTranscript([]); setFires([]); setGov([]);
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
            tools: tok.tools || [],
            tool_choice: "auto",
            audio: {
              input: {
                transcription: { model: "whisper-1" },
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
  function end() { hangup(); setStatus((s) => (s === "live" || s === "connecting" ? "ended" : s)); }

  const live = status === "live";
  const connecting = status === "connecting";

  return (
    <div>
      <div className="view-head">
        <h1>Live Voice — talk to the governed Voice AI</h1>
        <p>A real spoken call (OpenAI Realtime). As you talk, the Voice AI calls the real supporting
          agents — Policy Verification, Triage, Next Best Action, Knowledge — and governance checks each
          one <b>live</b>. Pick the policy, press Start, allow your mic, and just talk.</p>
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

      <div className="ops">
        <div className="card">
          <div className="col-head"><h3>🎧 You ↔ Voice AI</h3><span className="tag">{policy}</span></div>
          <div className="col-body" style={{ minHeight: 320 }}>
            {transcript.length === 0 && (
              <div className="empty">{live ? "Listening… say hello, or ask about your claim." : "Press Start and begin talking."}</div>
            )}
            {transcript.map((m, i) => (
              <div key={i} className={"bubble " + (m.who === "you" ? "customer" : "va")}>
                <div className="who" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>{m.who === "you" ? "You" : "Voice AI"}</span>
                  {m.who !== "you" && (
                    <Thumbs key={"vb" + i + (m.text || "").length} source="voice" agent="VA" agentName="Voice AI"
                      context={lastCustomer.current} answer={m.text} onFlag={onChange} />
                  )}
                </div>
                {m.text}
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="col-head"><h3>⚙ Supporting agents</h3><span className="tag">live</span></div>
          <div className="col-body" style={{ minHeight: 320 }}>
            {fires.length === 0 && <div className="empty">Agents fire here as the Voice AI consults them.</div>}
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
                <div className="row" style={{ justifyContent: "space-between", marginTop: 4 }}>
                  <Sources list={f.sources} />
                  <Thumbs key={"af" + i} source="agent" agent={f.agent} agentName={f.agentName || f.agent}
                    context={f.ctx || lastCustomer.current} answer={f.detail} onFlag={onChange} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="col-head"><h3>🛡 Governance</h3><span className="tag">live</span></div>
          <div className="col-body" style={{ minHeight: 320 }}>
            {gov.length === 0 && <div className="empty">Live green checks / red flags appear here.</div>}
            {gov.map((g, i) => (
              <div key={i} className={"gov " + (g.pass ? "pass" : "fail")}>
                <div className="icn">{g.pass ? "✓" : "✕"}</div>
                <div><div className="who">{g.agent}</div><div>{g.label}</div></div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card pad" style={{ marginTop: 14 }}>
        <div className="row" style={{ cursor: "pointer" }} onClick={() => setShowScript(!showScript)}>
          <h3 style={{ margin: 0 }}>{showScript ? "▾" : "▸"} 🎬 Demo script — say these in order</h3>
          <span className="muted" style={{ fontSize: 12 }}>on LM-AUTO-88123 (no rental), each line triggers an agent</span>
        </div>
        {showScript && (
          <>
            <div style={{ marginTop: 10 }}>
              {SCRIPT.map((s, i) => (
                <div key={i} className="script-step">
                  <div className="script-n">{i + 1}</div>
                  <div>
                    <div className="script-say">"{s.say}"</div>
                    <div className="script-meta">{s.meta}</div>
                  </div>
                </div>
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
