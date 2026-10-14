import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Registry({ nonce }) {
  const [data, setData] = useState(null);
  useEffect(() => { api.agents().then(setData); }, [nonce]);
  if (!data) return <div className="empty">Loading registry…</div>;

  return (
    <div>
      <div className="view-head">
        <h1>Agent Registry</h1>
        <p>Every agent and governance actor in the platform, with its owner, risk tier, the single
          quality metric it is held to, its tools, and its current version.</p>
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr><th>Agent</th><th>Owner</th><th>Risk</th><th>Governed on</th><th>Tools</th><th>Version</th><th>Status</th></tr>
          </thead>
          <tbody>
            {data.agents.map((a) => (
              <tr key={a.id}>
                <td><b>{a.name}</b><div className="sub mono">{a.id}</div></td>
                <td className="muted">{a.owner}</td>
                <td className="risk">{a.risk}</td>
                <td className="muted">{a.metric}</td>
                <td><div className="pill-roles">{a.tools.map((t) => <span key={t} className="role-pill">{t}</span>)}</div></td>
                <td className="ver">v{a.version}</td>
                <td><span className={"status-tag " + a.status}>{a.status}</span></td>
              </tr>
            ))}
            {data.guardians.map((g) => (
              <tr key={g.id}>
                <td><b>{g.name}</b><div className="sub mono">{g.id}</div></td>
                <td className="muted">{g.owner}</td>
                <td className="risk" style={{ color: "var(--blue)" }}>{g.risk}</td>
                <td className="muted">{g.metric}</td>
                <td><span className="role-pill">monitors all agents</span></td>
                <td className="ver">—</td>
                <td><span className="status-tag Healthy" style={{ color: "var(--blue)", background: "#132033" }}>Guardian</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
        Audit/Compliance (AU) and the Human Supervisor (HITL) are governance actors — they monitor
        every agent rather than serving the customer directly.
      </p>
    </div>
  );
}
