import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

// Live voice call with the claims Voice AI via OpenAI Realtime (WebRTC).
// The browser streams mic audio straight to OpenAI using a short-lived
// ephemeral key minted by our backend; the real API key never reaches here.
export default function LiveVoice() {
  const [policy, setPolicy] = useState("LM-AUTO-88123");
  const [status, setStatus] = useState("idle"); // idle|connecting|live|ended|error
  const [error, setError] = useState("");
  const [transcript, setTranscript] = useState([]);
  const [available, setAvailable] = useState(null);

  const pcRef = useRef(null);
  const dcRef = useRef(null);
  const micRef = useRef(null);
  const audioRef = useRef(null);

  useEffect(() => {
    api.health().then((h) => setAvailable(!!h.realtime)).catch(() => setAvailable(false));
    return () => hangup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function addLine(who, text) {
    if (!text) return;
    setTranscript((t) => [...t, { who, text }]);
  }

  function handleEvent(raw) {
    let ev;
    try { ev = JSON.parse(raw); } catch { return; }
    switch (ev.type) {
      case "conversation.item.input_audio_transcription.completed":
        addLine("you", ev.transcript);
        break;
      case "response.output_audio_transcript.done":
      case "response.audio_transcript.done":
        addLine("agent", ev.transcript);
        break;
      case "error":
        setError(ev.error?.message || "Realtime error");
        break;
      default:
        break;
    }
  }

  async function start() {
    setError("");
    setTranscript([]);
    setStatus("connecting");
    let tok;
    try {
      tok = await api.realtimeToken(policy);
    } catch (e) {
      setStatus("error"); setError("Could not reach the server to start a call."); return;
    }
    if (tok.error || !tok.value) {
      setStatus("error");
      setError(tok.error || "No session token returned. Is OPENAI_API_KEY set on the server?");
      return;
    }
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      micRef.current = mic;

      const pc = new RTCPeerConnection();
      pcRef.current = pc;

      pc.ontrack = (e) => {
        if (audioRef.current) {
          audioRef.current.srcObject = e.streams[0];
          audioRef.current.play().catch(() => {});
        }
      };
      pc.onconnectionstatechange = () => {
        if (["failed", "disconnected", "closed"].includes(pc.connectionState) && status === "live") {
          setStatus("ended");
        }
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
            audio: { input: { transcription: { model: "whisper-1" } } },
          },
        }));
        // have the agent greet first
        dc.send(JSON.stringify({ type: "response.create" }));
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const resp = await fetch("https://api.openai.com/v1/realtime/calls", {
        method: "POST",
        body: offer.sdp,
        headers: {
          Authorization: `Bearer ${tok.value}`,
          "Content-Type": "application/sdp",
        },
      });
      if (!resp.ok) {
        const t = await resp.text();
        throw new Error(`OpenAI call setup failed (${resp.status}): ${t.slice(0, 160)}`);
      }
      const answer = { type: "answer", sdp: await resp.text() };
      await pc.setRemoteDescription(answer);
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
  }

  const live = status === "live";
  const connecting = status === "connecting";

  return (
    <div>
      <div className="view-head">
        <h1>Live Voice — talk to the Voice AI</h1>
        <p>A real spoken call with the claims Voice AI, powered by OpenAI Realtime. Pick the
          policy it's handling, press Start, allow your microphone, and just talk. It answers out
          loud and is grounded in that policy's coverages.</p>
      </div>

      {available === false && (
        <div className="banner" style={{ marginBottom: 16, borderColor: "var(--amber)" }}>
          Live voice needs <b>OPENAI_API_KEY</b> set on the server. Add it in Vercel →
          Environment Variables and redeploy, then reload this page.
        </div>
      )}

      <div className="row" style={{ marginBottom: 16 }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>Policy the agent is handling</label>
          <select value={policy} onChange={(e) => setPolicy(e.target.value)} disabled={live || connecting}>
            <option value="LM-AUTO-88123">LM-AUTO-88123 — Jordan Rivera (NO rental coverage)</option>
            <option value="LM-AUTO-55900">LM-AUTO-55900 — Priya Nair (HAS rental coverage)</option>
          </select>
        </div>
        {!live ? (
          <button className="btn" onClick={start} disabled={connecting || available === false}>
            {connecting ? "Connecting…" : "🎙 Start call"}
          </button>
        ) : (
          <button className="btn ghost" onClick={end}>■ End call</button>
        )}
        <span className="status-pill" style={{ marginLeft: "auto" }}>
          <span className={"dot" + (live ? "" : " sim")} />
          {live ? "LIVE — speak now" : connecting ? "connecting…" : status === "ended" ? "call ended" : "ready"}
        </span>
      </div>

      {error && (
        <div className="banner" style={{ marginBottom: 16, borderColor: "var(--red)", color: "var(--text)" }}>
          {error}
        </div>
      )}

      <div className="grid" style={{ gridTemplateColumns: "1.4fr 1fr", gap: 14 }}>
        <div className="card">
          <div className="col-head"><h3>🎧 Call transcript</h3>
            <span className="tag">{policy}</span></div>
          <div className="col-body" style={{ minHeight: 300 }}>
            {transcript.length === 0 && (
              <div className="empty">
                {live ? "Listening… say hello, or ask about your claim." : "Press Start and begin talking."}
              </div>
            )}
            {transcript.map((m, i) => (
              <div key={i} className={"bubble " + (m.who === "you" ? "customer" : "va")}>
                <div className="who">{m.who === "you" ? "You" : "Voice AI"}</div>
                {m.text}
              </div>
            ))}
          </div>
        </div>

        <div className="card pad">
          <h3 style={{ marginTop: 0 }}>Try saying…</h3>
          <p className="muted" style={{ fontSize: 13 }}>Hold a natural conversation. To see the
            governance behavior live, try the rental question on the <b>no-rental</b> policy:</p>
          <ul style={{ fontSize: 13, lineHeight: 1.8, paddingLeft: 18 }}>
            <li>"Hi, I was just in a car accident."</li>
            <li>"I got rear-ended, the bumper's damaged but I'm not hurt."</li>
            <li>"Will my rental car be covered while it's in the shop?"</li>
            <li>"Can you just approve a $3,000 payout now?"</li>
          </ul>
          <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
            On LM-AUTO-88123 the agent should say rental is <b>not</b> covered, and should refuse to
            approve a payout — that's the grounding + guardrails working in a live call.
          </p>
        </div>
      </div>

      <audio ref={audioRef} autoPlay />
    </div>
  );
}
