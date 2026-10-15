import React, { useState } from "react";
import { api } from "../api.js";

// Reusable 👍/👎 on a single answer (a Voice AI reply or a supporting-agent output).
// 👍 = no action. 👎 sends THIS answer to the Learning Studio review queue.
export default function Thumbs({ source, agent, agentName, context, answer, confidence, scenarioId, trapId, onFlag }) {
  const [state, setState] = useState("");  // '' | 'up' | 'down'
  const [busy, setBusy] = useState(false);

  async function send(thumbs) {
    if (busy || state) return;
    setBusy(true);
    try {
      await api.feedback({ thumbs, source, agent, agent_name: agentName, context,
                           answer, confidence, scenario_id: scenarioId, trap_id: trapId });
    } catch {}
    setState(thumbs);
    setBusy(false);
    if (thumbs === "down" && onFlag) onFlag();
  }

  if (state === "up") return <span className="fb-note ok">👍 thanks</span>;
  if (state === "down") return <span className="fb-note flag">👎 sent to Learning Studio →</span>;
  return (
    <span className="fb">
      <button className="fb-btn" title="Good answer" onClick={() => send("up")}>👍</button>
      <button className="fb-btn" title="Needs improvement" onClick={() => send("down")}>👎</button>
    </span>
  );
}
