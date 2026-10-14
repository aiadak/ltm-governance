import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// A deep-linkable source-document viewer. Any link of the form
//   <a href="#doc=POL-88123-DEC">…</a>
// (or the full URL https://your-app/#doc=POL-88123-DEC) opens this panel on that
// document — so an agent's citation points straight at the document section it used.
function parseHash() {
  const h = window.location.hash || "";
  const m = h.match(/doc=([A-Za-z0-9._-]+)/);
  return m ? m[1] : null;
}

export default function DocViewer() {
  const [docId, setDocId] = useState(parseHash());
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const onHash = () => setDocId(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (!docId) { setDoc(null); return; }
    setLoading(true);
    api.document(docId).then((d) => setDoc(d)).catch(() => setDoc({ error: true })).finally(() => setLoading(false));
  }, [docId]);

  function close() {
    // clear the hash without scrolling
    history.replaceState(null, "", window.location.pathname + window.location.search);
    setDocId(null);
  }

  if (!docId) return null;
  return (
    <div className="docoverlay" onClick={close}>
      <div className="docpanel" onClick={(e) => e.stopPropagation()}>
        <div className="docpanel-head">
          <div>
            <div className="mono muted" style={{ fontSize: 11 }}>SOURCE DOCUMENT · {docId}</div>
            <h3 style={{ margin: "4px 0 0" }}>{doc?.title || (loading ? "Loading…" : docId)}</h3>
          </div>
          <button className="btn ghost sm" onClick={close}>✕ Close</button>
        </div>
        {doc && !doc.error && (
          <div className="docpanel-body">
            <div className="row" style={{ gap: 8, marginBottom: 12 }}>
              <span className="chip">{doc.category}</span>
              <span className="chip">v{doc.version}</span>
              <span className="muted mono" style={{ fontSize: 11 }}>visible to: {(doc.roles || []).join(", ")}</span>
            </div>
            <p style={{ fontSize: 14, lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{doc.text}</p>
            <div className="muted" style={{ fontSize: 12, marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
              This is the exact section the agent cited. Share this view with the URL ending in
              <span className="mono"> #doc={docId}</span>.
            </div>
          </div>
        )}
        {doc?.error && <div className="empty">Document {docId} not found.</div>}
      </div>
    </div>
  );
}

// A small reusable citation link row.
export function Sources({ list }) {
  if (!list || list.length === 0) return null;
  return (
    <div className="sources">
      <span className="muted" style={{ fontSize: 11 }}>📄 grounded in:</span>
      {list.map((s) => (
        <a key={s.doc_id} className="cite" href={`#doc=${s.doc_id}`} title={s.title}>{s.doc_id}</a>
      ))}
    </div>
  );
}
