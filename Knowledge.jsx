import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const ROLES = [
  ["VA", "Voice AI"], ["PV", "Policy Verification"], ["KR", "Knowledge Retrieval"],
  ["NBA", "Next Best Action"], ["TR", "Triage"], ["SUM", "Summarization"], ["AU", "Audit/Compliance"],
];

export default function Knowledge({ nonce }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ title: "", category: "Policy document", text: "", roles: ["PV"] });
  const [q, setQ] = useState("is a rental car covered");
  const [qRole, setQRole] = useState("KR");
  const [results, setResults] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = () => api.documents().then(setData);
  useEffect(() => { load(); }, [nonce]);

  function toggleRole(r) {
    setForm((f) => ({ ...f, roles: f.roles.includes(r) ? f.roles.filter((x) => x !== r) : [...f.roles, r] }));
  }

  async function save() {
    if (!form.title || !form.text) return;
    setSaving(true);
    await api.addDocument(form);
    setForm({ title: "", category: "Policy document", text: "", roles: ["PV"] });
    await load();
    setSaving(false);
  }

  async function runQuery() {
    const r = await api.retrieve(q, qRole, 3);
    setResults(r.results);
  }

  if (!data) return <div className="empty">Loading knowledge base…</div>;

  return (
    <div>
      <div className="view-head">
        <h1>Knowledge Base</h1>
        <p>One shared, versioned knowledge source feeds every agent — but with role-based retrieval,
          so each agent only sees what it needs. {data.embed_mode === "openai"
            ? "Embeddings: OpenAI (live)." : "Embeddings: deterministic fallback (set OPENAI_API_KEY for vector embeddings)."}</p>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="card pad">
          <h3 style={{ marginTop: 0 }}>Feed a document</h3>
          <div className="field">
            <label>Title</label>
            <input type="text" value={form.title} placeholder="e.g. Endorsement RENT-45 terms"
              onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </div>
          <div className="field">
            <label>Category</label>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {["Policy document", "Claims SOP", "Customer data", "Historical claim",
                "Compliance", "Governance rule", "Knowledge article", "Correction record"]
                .map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Text</label>
            <textarea value={form.text} placeholder="Paste the policy / SOP / article text…"
              onChange={(e) => setForm({ ...form, text: e.target.value })} />
          </div>
          <div className="field">
            <label>Which agents may retrieve this (role-based access)</label>
            <div className="pill-roles">
              {ROLES.map(([id, name]) => (
                <span key={id} className="role-pill" onClick={() => toggleRole(id)}
                  style={{ cursor: "pointer", borderColor: form.roles.includes(id) ? "var(--coral)" : "var(--line-2)",
                           color: form.roles.includes(id) ? "var(--coral)" : "var(--muted)" }}>
                  {id} · {name}
                </span>
              ))}
            </div>
          </div>
          <button className="btn sm" onClick={save} disabled={saving || !form.title || !form.text}>
            {saving ? "Embedding…" : "Add to knowledge source"}
          </button>
        </div>

        <div className="card pad">
          <h3 style={{ marginTop: 0 }}>Test role-based retrieval</h3>
          <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
            Query as a specific agent. The agent only sees documents tagged for its role — proving,
            for example, that Policy Verification can read declarations the Voice AI cannot.
          </p>
          <div className="field">
            <label>Query</label>
            <input type="text" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="field">
            <label>Retrieve as agent</label>
            <select value={qRole} onChange={(e) => setQRole(e.target.value)}>
              {ROLES.map(([id, name]) => <option key={id} value={id}>{id} · {name}</option>)}
            </select>
          </div>
          <button className="btn ghost sm" onClick={runQuery}>Retrieve</button>
          {results && (
            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              {results.length === 0 && <div className="empty">No documents visible to {qRole}.</div>}
              {results.map((d) => (
                <div key={d.doc_id} className="fire">
                  <div className="top">
                    <span className="chip agent">{d.doc_id}</span>
                    <span className="chip">{d.category}</span>
                    <span className="mono" style={{ marginLeft: "auto" }}>sim {d.score}</span>
                  </div>
                  <div style={{ fontSize: 13, marginTop: 4 }}>{d.title}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="section-title">Shared versioned knowledge source · {data.documents.length} documents</div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table>
          <thead><tr><th>Doc</th><th>Title</th><th>Category</th><th>Visible to</th><th>Ver</th></tr></thead>
          <tbody>
            {data.documents.map((d) => (
              <tr key={d.doc_id}>
                <td><a className="cite" href={`#doc=${d.doc_id}`}>{d.doc_id}</a></td>
                <td>{d.title}</td>
                <td className="muted">{d.category}</td>
                <td><div className="pill-roles">{d.roles.map((r) => <span key={r} className="role-pill">{r}</span>)}</div></td>
                <td className="ver">v{d.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
