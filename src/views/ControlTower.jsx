import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import Graph from "../components/Graph.jsx";

function rateColor(v) {
  if (v >= 90) return "var(--green)";
  if (v >= 75) return "var(--amber)";
  return "var(--red)";
}
function fmt(n) { return (n || 0).toLocaleString(); }

export default function ControlTower({ nonce }) {
  const [data, setData] = useState(null);
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    api.dashboard().then(setData);
    api.metrics().then(setMetrics).catch(() => {});
  }, [nonce]);

  if (!data) return <div className="empty">Loading command center…</div>;
  const m = metrics;

  return (
    <div>
      <div className="view-head">
        <h1>Governance Command Center</h1>
        <p>One screen to oversee every agent in the contact center — observability metrics, tool
          calling, token economics, latency and eval pass-rates, plus the agent dependency graph,
          performance matrix and execution-trace replay.</p>
      </div>

      {/* ===================== observability dashboard ===================== */}
      {m && (
        <>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center", margin: "0 0 10px" }}>
            <div className="section-title" style={{ margin: 0 }}>
              Observability
              <span className="mono muted" style={{ fontSize: 11, marginLeft: 8, textTransform: "none", letterSpacing: 0 }}>
                {m.mode === "warming up" ? "· warming up — run a call to populate"
                  : m.mode === "live" ? "· live telemetry" : "· measured this session"}
              </span>
            </div>
            <span className="status-pill" title="Braintrust tracing">
              <span className={"dot" + (m.braintrust.configured ? "" : " sim")} />
              Braintrust · {m.braintrust.mode}{m.braintrust.project ? ` · ${m.braintrust.project}` : ""}
            </span>
          </div>

          <div className="grid kpis">
            <div className="card kpi"><div className="label">Agent calls</div><div className="val">{fmt(m.kpis.agent_calls)}</div></div>
            <div className="card kpi"><div className="label">Tool-call success</div>
              <div className="val" style={{ color: rateColor(m.kpis.tool_success_rate) }}>{m.kpis.tool_success_rate}%</div></div>
            <div className="card kpi"><div className="label">Governance pass rate</div>
              <div className="val" style={{ color: rateColor(m.kpis.gov_pass_rate) }}>{m.kpis.gov_pass_rate}%</div></div>
            <div className="card kpi"><div className="label">Flagged for review</div>
              <div className="val coral">{m.kpis.flagged_for_review}</div></div>
            <div className="card kpi"><div className="label">Human corrections</div>
              <div className="val coral">{m.kpis.human_corrections}</div></div>
            <div className="card kpi"><div className="label">Agents live</div><div className="val">{m.kpis.agents_live}</div></div>
          </div>

          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12, marginTop: 12 }}>
            {/* latency percentiles */}
            <div className="card pad">
              <div className="label" style={{ marginBottom: 10 }}>Latency (ms)</div>
              <div className="row" style={{ justifyContent: "space-between" }}>
                {[["P50", m.latency_ms.p50], ["P95", m.latency_ms.p95], ["P99", m.latency_ms.p99]].map(([k, v]) => (
                  <div key={k} style={{ textAlign: "center", flex: 1 }}>
                    <div className="mono muted" style={{ fontSize: 11 }}>{k}</div>
                    <div style={{ fontFamily: "Poppins", fontSize: 22, fontWeight: 700 }}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
            {/* token economics */}
            <div className="card pad">
              <div className="label" style={{ marginBottom: 10 }}>Token economics</div>
              <div className="metric-row"><span className="muted">Input</span><span className="mono">{fmt(m.tokens.input)}</span></div>
              <div className="metric-row"><span className="muted">Output</span><span className="mono">{fmt(m.tokens.output)}</span></div>
              <div className="metric-row"><span className="muted">Total</span><span className="mono">{fmt(m.tokens.total)}</span></div>
              <div className="metric-row" style={{ borderTop: "1px solid var(--line)", paddingTop: 6, marginTop: 4 }}>
                <span className="muted">Est. cost</span><span className="mono" style={{ color: "var(--coral)" }}>${m.tokens.est_cost_usd}</span></div>
            </div>
            {/* tool calling */}
            <div className="card pad">
              <div className="label" style={{ marginBottom: 10 }}>Tool calling</div>
              <div className="metric-row"><span className="muted">Total calls</span><span className="mono">{fmt(m.tool_calling.total_calls)}</span></div>
              <div className="metric-row"><span className="muted">Success rate</span>
                <span className="mono" style={{ color: rateColor(m.tool_calling.success_rate) }}>{m.tool_calling.success_rate}%</span></div>
              <div className="meter" style={{ marginTop: 8, width: "100%" }}>
                <span style={{ width: m.tool_calling.success_rate + "%", background: rateColor(m.tool_calling.success_rate) }} />
              </div>
            </div>
          </div>

          <div className="section-title">Agent evaluation toolkit · per agent</div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
            Everything an evaluator needs per agent, measured live: quality metric, version, calls, average
            confidence, governance pass rate, latency (P50/P95), tool-call success, token economics, human
            flags (👎), corrections applied, and health. Rows for agents that haven't fired yet show baseline.
          </div>
          <div className="card" style={{ overflowX: "auto" }}>
            <table className="evaltab">
              <thead><tr>
                <th>Agent</th><th>Eval metric</th><th>Ver</th><th>Calls</th><th>Avg conf</th><th>Pass rate</th>
                <th>P50</th><th>P95</th><th>Tool ✓</th><th>Tokens</th><th>Cost</th><th>👎 Flagged</th><th>Fixes</th><th>Status</th>
              </tr></thead>
              <tbody>
                {m.evals.map((e) => (
                  <tr key={e.id} style={{ opacity: e.measured ? 1 : 0.55 }}>
                    <td><b>{e.name}</b><div className="sub mono">{e.id} · {e.owner}</div></td>
                    <td className="muted">{e.metric}</td>
                    <td className="ver">v{e.version}</td>
                    <td className="mono">{e.calls}</td>
                    <td className="mono" style={{ color: e.avg_conf == null ? "var(--faint)" : rateColor(e.avg_conf) }}>
                      {e.avg_conf == null ? "—" : e.avg_conf + "%"}</td>
                    <td>
                      <span className="meter" style={{ width: 64 }}><span style={{ width: e.pass_rate + "%", background: rateColor(e.pass_rate) }} /></span>{" "}
                      <span className="mono" style={{ color: rateColor(e.pass_rate) }}>{e.pass_rate}%</span>
                    </td>
                    <td className="mono muted">{e.measured ? e.p50_ms + "ms" : "—"}</td>
                    <td className="mono muted">{e.measured ? e.p95_ms + "ms" : "—"}</td>
                    <td className="mono">{e.measured ? e.tool_success + "%" : "—"}</td>
                    <td className="mono">{e.tokens ? e.tokens.toLocaleString() : "—"}
                      {e.tokens ? <div className="sub mono">{e.tokens_in} in · {e.tokens_out} out</div> : null}</td>
                    <td className="mono">{e.cost_usd ? "$" + e.cost_usd.toFixed(4) : "—"}</td>
                    <td className="mono" style={{ color: e.flagged ? "var(--coral)" : "var(--faint)" }}>{e.flagged}</td>
                    <td className="mono" style={{ color: e.corrections ? "var(--green)" : "var(--faint)" }}>{e.corrections}</td>
                    <td><span className={"status-tag " + e.status}>{e.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ===================== dependency graph ===================== */}
      <div className="section-title">Agent dependency graph</div>
      <div className="card pad">
        <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
          Click a node to see which downstream agents an upstream error would affect.
          Governance actors (AU, HITL) monitor every agent along the dashed edges.
        </p>
        <Graph graph={data.graph} />
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
