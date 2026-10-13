import React, { useState } from "react";

// Fixed layout positions for the agent dependency graph.
const POS = {
  VA:  { x: 90,  y: 150 },
  PV:  { x: 300, y: 60 },
  KR:  { x: 300, y: 150 },
  TR:  { x: 300, y: 240 },
  NBA: { x: 510, y: 150 },
  SUM: { x: 700, y: 150 },
  AU:  { x: 400, y: 345 },
  HITL:{ x: 210, y: 345 },
};
const COLOR = { ok: "#4ea86f", watch: "#e0a94a", err: "#e0533d", guardian: "#5b8bd0" };

// which agents are downstream of each node (for impact highlight)
const DOWNSTREAM = {
  VA: ["PV", "KR", "TR", "NBA", "SUM"],
  PV: ["NBA", "VA", "SUM"],
  KR: ["NBA", "VA", "SUM"],
  TR: ["NBA", "SUM"],
  NBA: ["VA", "SUM"],
  SUM: [],
  AU: [], HITL: [],
};

export default function Graph({ graph, onSelect }) {
  const [sel, setSel] = useState(null);
  if (!graph) return null;
  const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
  const impacted = sel ? new Set(DOWNSTREAM[sel] || []) : new Set();

  const line = (a, b, dashed, key) => {
    const p = POS[a], q = POS[b];
    if (!p || !q) return null;
    const hot = sel && (a === sel || impacted.has(b)) && !dashed;
    return (
      <line key={key} x1={p.x} y1={p.y} x2={q.x} y2={q.y}
        stroke={hot ? "#e8674b" : (dashed ? "#3a506b" : "#333")}
        strokeWidth={hot ? 2.2 : 1.2}
        strokeDasharray={dashed ? "4 4" : "0"} markerEnd="url(#arrow)" />
    );
  };

  const click = (id) => { setSel(id === sel ? null : id); onSelect && onSelect(id === sel ? null : id); };

  return (
    <div className="graph-wrap">
      <svg width="780" height="400" style={{ maxWidth: "100%" }}>
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3"
            orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L7,3 L0,6 Z" fill="#555" />
          </marker>
        </defs>
        {graph.monitors.map((m, i) => line(m[0], m[1], true, "m" + i))}
        {graph.edges.map((e, i) => line(e[0], e[1], false, "e" + i))}
        {graph.nodes.map((n) => {
          const p = POS[n.id];
          if (!p) return null;
          const c = COLOR[n.status] || "#888";
          const isSel = sel === n.id;
          const isImpact = impacted.has(n.id);
          const guardian = n.kind === "guardian";
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} style={{ cursor: "pointer" }}
               onClick={() => click(n.id)}>
              <circle r={guardian ? 20 : 24} fill="#141414" stroke={c}
                strokeWidth={isSel ? 3.5 : (isImpact ? 2.5 : 1.8)}
                strokeDasharray={guardian ? "3 3" : "0"} />
              <circle r="5" cy={guardian ? 0 : -0} fill={c} opacity="0" />
              <text textAnchor="middle" dy="4" fill={c} className="node-label"
                style={{ fontSize: guardian ? 10 : 12, fontWeight: 700 }}>{n.id}</text>
            </g>
          );
        })}
      </svg>
      <div className="legend">
        <span><i className="swatch" style={{ background: COLOR.ok }} /> Healthy</span>
        <span><i className="swatch" style={{ background: COLOR.watch }} /> Watch</span>
        <span><i className="swatch" style={{ background: COLOR.err }} /> Flagged / erred</span>
        <span><i className="swatch" style={{ background: COLOR.guardian }} /> Governance (monitors, dashed)</span>
      </div>
      {sel && (
        <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          <b style={{ color: "var(--coral)" }}>{byId[sel]?.name}</b> selected.{" "}
          {(DOWNSTREAM[sel] || []).length
            ? <>Downstream agents affected by an error here: <span className="mono">{(DOWNSTREAM[sel] || []).join(", ")}</span></>
            : "No downstream agents depend on this node."}
        </p>
      )}
    </div>
  );
}
