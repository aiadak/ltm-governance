import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import Graph from "../components/Graph.jsx";

const KPI = [
  ["agents_registered", "Agents registered", ""],
  ["active_conversations", "Active conversations", ""],
  ["eval_pass_rate", "Eval pass rate", "green", "%"],
  ["violations", "Governance violations", "red"],
  ["interventions", "Human interventions", "coral"],
  ["learning_pending", "Learning pending", "coral"],
];

export default function ControlTower({ nonce }) {
  const [data, setData] = useState(null);
  const [traces, setTraces] = useState([]);

  useEffect(() => {
    api.dashboard().then((d) => {
      setData(d);
      if (d.latest_conversation)
        api.traces(d.latest_conversation).then((t) => setTraces(t.traces || [])).catch(() => {});
      else setTraces([]);
    });
  }, [nonce]);

  if (!data) return <div className="empty">Loading command center…</div>;
  const k = data.kpis;

  return (
    <div>
      <div className="view-head">
        <h1>Governance Command Center</h1>
        <p>Oversight for every agent in the contact center — quality scores, compliance violations,
          human interventions, the agent dependency graph, and a step-by-step execution trace replay.</p>
      </div>

      <div className="grid kpis">
        {KPI.map(([key, label, cls, suffix]) => (
          <div key={key} className="card kpi">
            <div className="label">{label}</div>
            <div className={"val " + (cls || "")}>{k[key]}{suffix || ""}</div>
          </div>
        ))}
      </div>

      <div className="section-title">Agent dependency graph</div>
      <div className="card pad">
        <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
          Click a node to see which downstream agents an upstream error would affect.
          Governance actors (AU, HITL) monitor every agent along the dashed edges.
        </p>
        <Graph graph={data.graph} />
      </div>

      <div className="section-title">Agent performance matrix</div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr><th>Agent</th><th>Owner</th><th>Risk</th><th>Quality metric</th><th>Score</th><th>Ver</th><th>Status</th></tr>
          </thead>
          <tbody>
            {data.matrix.map((a) => (
              <tr key={a.id}>
                <td><b>{a.name}</b><div className="sub mono">{a.id}</div></td>
                <td className="muted">{a.owner}</td>
                <td className="risk">{a.risk}</td>
                <td className="muted">{a.metric}</td>
                <td>
                  <span className="meter"><span style={{ width: a.score + "%" }} /></span>{" "}
                  <span className="mono">{a.score}</span>
                </td>
                <td className="ver">v{a.version}</td>
                <td><span className={"status-tag " + a.status}>{a.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">Execution trace replay {data.latest_conversation && <span className="mono muted" style={{ fontSize: 12 }}>· {data.latest_conversation}</span>}</div>
      <div className="card pad">
        {traces.length === 0 && <div className="empty">Run a call in Live Ops to populate the trace.</div>}
        {traces.map((t, i) => (
          <div key={t.id} className="row" style={{ borderBottom: "1px solid var(--line)", padding: "9px 0", gap: 12 }}>
            <span className="mono muted" style={{ width: 28 }}>#{t.step}</span>
            <span className="chip agent" style={{ width: 44, textAlign: "center" }}>{t.agent}</span>
            <span className="muted" style={{ flex: 1, minWidth: 180 }}>{t.detail || t.metric}</span>
            {t.score != null && <span className="mono">{Math.round(t.score * 100)}</span>}
            <span className={"pass-badge " + (t.passed ? "ok" : "no")}>{t.passed ? "PASS" : "FAIL"}</span>
          </div>
        ))}
      </div>

      {data.violations.length > 0 && (
        <>
          <div className="section-title">Compliance violations</div>
          <div className="card pad">
            {data.violations.map((v) => (
              <div key={v.id} className="banner" style={{ marginBottom: 8 }}>
                <b className="mono" style={{ color: "var(--red)" }}>{v.guardrail} · {v.agent}</b> — {v.summary}
                {v.regulation && <div className="muted" style={{ marginTop: 4 }}>{v.regulation}</div>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
