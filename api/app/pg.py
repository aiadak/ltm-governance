"""
Postgres + pgvector persistence (pure-Python pg8000 driver — no compiled wheel,
so it installs on Vercel's Python 3.14).

This is the DURABLE three-store backend. When DATABASE_URL is set:
  - the knowledge store's vector retrieval runs in Postgres via pgvector (<=>),
  - operational rows (claims, conversations, turns, traces, violations,
    interventions) are persisted per call,
  - learning rows (improvements, agent versions/memory) are persisted and
    reloaded on startup — so recursive learning survives restarts.

Everything here is FAIL-SAFE: any DB error is swallowed (and printed to the
function logs) and the app falls back to its in-memory stores, so a
misconfigured database can never take the app down.
"""
import os
import sys
import json
from urllib.parse import urlparse, parse_qs

DATABASE_URL = os.environ.get("DATABASE_URL")
_READY = False  # set True once schema is created + seeded successfully


def enabled() -> bool:
    return bool(DATABASE_URL)


def ready() -> bool:
    return _READY


def status() -> dict:
    return {"configured": bool(DATABASE_URL),
            "mode": "postgres+pgvector" if DATABASE_URL else "in-memory"}


def _log(msg):
    print(f"[pg] {msg}", file=sys.stderr)


def _connect():
    import pg8000.native  # noqa
    import pg8000
    u = urlparse(DATABASE_URL)
    q = parse_qs(u.query)
    host = u.hostname or "localhost"
    sslmode = (q.get("sslmode", [""])[0]).lower()
    use_ssl = sslmode not in ("disable", "") or host not in ("localhost", "127.0.0.1")
    kwargs = dict(
        user=u.username or "postgres",
        password=u.password or None,
        host=host,
        port=u.port or 5432,
        database=(u.path or "/postgres").lstrip("/") or "postgres",
    )
    if use_ssl:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
    return pg8000.connect(**kwargs)


def _run(sql, params=(), fetch=False, many=None):
    """Open a connection, run, commit. Returns rows (fetch), True, or None on error."""
    if not DATABASE_URL:
        return None
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        if many is not None:
            cur.executemany(sql, many)
        else:
            cur.execute(sql, params)
        rows = cur.fetchall() if fetch else True
        conn.commit()
        return rows
    except Exception as e:
        _log(f"error: {e}")
        return None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


SCHEMA = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    # knowledge (vector column has no fixed dim so it works with 1536-dim OpenAI
    # embeddings or the 256-dim fallback; the corpus is tiny so no index needed)
    """CREATE TABLE IF NOT EXISTS documents (
         doc_id text PRIMARY KEY, title text, category text, roles text[],
         body text, version int DEFAULT 1, embedding vector, added_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS claims (
         claim_id text PRIMARY KEY, policy_id text, loss jsonb, severity text,
         adjuster text, created_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS conversations (
         conversation_id text PRIMARY KEY, policy_id text, started_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS turns (
         id bigserial PRIMARY KEY, conversation_id text, speaker text, body text, meta jsonb)""",
    """CREATE TABLE IF NOT EXISTS traces (
         id text PRIMARY KEY, conversation_id text, agent text, action text, detail text,
         metric text, score real, passed boolean, step int)""",
    """CREATE TABLE IF NOT EXISTS violations (
         id text PRIMARY KEY, conversation_id text, agent text, guardrail text,
         severity text, rule text, summary text, regulation text)""",
    """CREATE TABLE IF NOT EXISTS interventions (
         id text PRIMARY KEY, conversation_id text, agent text, decision text, note text)""",
    """CREATE TABLE IF NOT EXISTS agent_versions (
         agent text PRIMARY KEY, version int, prompt_addendum text, history jsonb)""",
    """CREATE TABLE IF NOT EXISTS improvements (
         id text PRIMARY KEY, agent text, conversation_id text, error text, root_cause text,
         correction text, proposed_fix jsonb, guardrail text, status text,
         regression jsonb, human_decision jsonb, deployed_version int,
         created_at timestamptz DEFAULT now())""",
]


def _vec(v):
    return "[" + ",".join(str(round(float(x), 6)) for x in v) + "]"


def init_and_seed(state) -> bool:
    """Create schema, seed documents (with embeddings) if empty, load learning."""
    if not DATABASE_URL:
        return False
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        for ddl in SCHEMA:
            cur.execute(ddl)
        conn.commit()
        cur.execute("SELECT count(*) FROM documents")
        n = cur.fetchall()[0][0]
        if n == 0:
            for d in state.knowledge.docs.values():
                cur.execute(
                    "INSERT INTO documents (doc_id,title,category,roles,body,version,embedding) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s::vector) ON CONFLICT (doc_id) DO NOTHING",
                    (d["doc_id"], d["title"], d["category"], d["roles"], d["text"],
                     d["version"], _vec(d["vector"])))
            conn.commit()
        conn.close(); conn = None
        _load_learning(state)
        global _READY
        _READY = True
        _log(f"ready (documents={max(n, len(state.knowledge.docs))})")
        return True
    except Exception as e:
        _log(f"init error: {e}")
        try:
            if conn:
                conn.close()
        except Exception:
            pass
        return False


def _load_learning(state):
    rows = _run("SELECT agent,version,prompt_addendum,history FROM agent_versions", fetch=True)
    if rows:
        for agent, version, addendum, history in rows:
            state.learning.versions[agent] = {
                "version": version or 1, "prompt_addendum": addendum or "",
                "history": history if isinstance(history, list) else (json.loads(history) if history else [])}
    rows = _run("SELECT id,agent,conversation_id,error,root_cause,correction,proposed_fix,"
                "guardrail,status,regression,human_decision,deployed_version "
                "FROM improvements ORDER BY created_at", fetch=True)
    if rows:
        for r in rows:
            (iid, agent, conv, err, rc, corr, pf, gr, st, reg, hd, dv) = r
            jj = lambda x: (x if isinstance(x, (dict, list)) else (json.loads(x) if x else None))
            state.learning.improvements[iid] = {
                "id": iid, "agent": agent, "conversation_id": conv, "error": err,
                "root_cause": rc, "correction": corr, "proposed_fix": jj(pf) or {},
                "guardrail": gr, "status": st, "regression": jj(reg) or {"total": 0, "passed": 0, "cases": []},
                "human_decision": jj(hd), "deployed_version": dv, "created_at": 0}


def knowledge_retrieve(query_vec, role, k=3):
    """pgvector cosine retrieval, role-filtered. Returns docs or None (fall back)."""
    rows = _run(
        "SELECT doc_id,title,category,roles,body,version, (embedding <=> %s::vector) AS dist "
        "FROM documents WHERE %s = ANY(roles) ORDER BY embedding <=> %s::vector LIMIT %s",
        (_vec(query_vec), role, _vec(query_vec), int(k)), fetch=True)
    if rows is None:
        return None
    out = []
    for doc_id, title, cat, roles, body, version, dist in rows:
        out.append({"doc_id": doc_id, "title": title, "category": cat, "roles": roles,
                    "text": body, "version": version, "score": round(1 - float(dist), 3)})
    return out


def persist_document(rec):
    _run("INSERT INTO documents (doc_id,title,category,roles,body,version,embedding) "
         "VALUES (%s,%s,%s,%s,%s,%s,%s::vector) "
         "ON CONFLICT (doc_id) DO UPDATE SET title=EXCLUDED.title,category=EXCLUDED.category,"
         "roles=EXCLUDED.roles,body=EXCLUDED.body,version=EXCLUDED.version,embedding=EXCLUDED.embedding",
         (rec["doc_id"], rec["title"], rec["category"], rec["roles"], rec["text"],
          rec["version"], _vec(rec["vector"])))


def persist_call(state, conv_id):
    """Persist everything produced by one call, in one connection."""
    if not DATABASE_URL:
        return
    op = state.operational
    conv = op.conversations.get(conv_id)
    conn = None
    try:
        conn = _connect(); cur = conn.cursor()
        if conv:
            cur.execute("INSERT INTO conversations (conversation_id,policy_id) VALUES (%s,%s) "
                        "ON CONFLICT (conversation_id) DO NOTHING", (conv_id, conv["policy_id"]))
            for t in conv["turns"]:
                cur.execute("INSERT INTO turns (conversation_id,speaker,body,meta) VALUES (%s,%s,%s,%s)",
                            (conv_id, t["speaker"], t["text"], json.dumps(t.get("meta", {}))))
        for c in op.claims.values():
            if c["policy_id"] == (conv or {}).get("policy_id"):
                cur.execute("INSERT INTO claims (claim_id,policy_id,loss,severity,adjuster) "
                            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (claim_id) DO NOTHING",
                            (c["claim_id"], c["policy_id"], json.dumps(c.get("loss", {})),
                             c.get("severity"), c.get("adjuster")))
        for t in op.traces_for(conv_id):
            cur.execute("INSERT INTO traces (id,conversation_id,agent,action,detail,metric,score,passed,step) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                        (t["id"], conv_id, t["agent"], t["action"], t["detail"], t["metric"],
                         t["score"], t["passed"], t["step"]))
        for v in op.violations:
            if v["conversation_id"] == conv_id:
                cur.execute("INSERT INTO violations (id,conversation_id,agent,guardrail,severity,rule,summary,regulation) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                            (v["id"], conv_id, v["agent"], v.get("guardrail"), v.get("severity"),
                             v.get("rule"), v.get("summary"), v.get("regulation")))
        for i in op.interventions:
            if i["conversation_id"] == conv_id:
                cur.execute("INSERT INTO interventions (id,conversation_id,agent,decision,note) "
                            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                            (i["id"], conv_id, i["agent"], i.get("decision"), i.get("note")))
        conn.commit()
    except Exception as e:
        _log(f"persist_call error: {e}")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def persist_improvement(imp):
    _run("INSERT INTO improvements (id,agent,conversation_id,error,root_cause,correction,"
         "proposed_fix,guardrail,status,regression,human_decision,deployed_version) "
         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
         "ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status,proposed_fix=EXCLUDED.proposed_fix,"
         "regression=EXCLUDED.regression,human_decision=EXCLUDED.human_decision,"
         "deployed_version=EXCLUDED.deployed_version",
         (imp["id"], imp.get("agent"), imp.get("conversation_id"), imp.get("error"),
          imp.get("root_cause"), imp.get("correction"), json.dumps(imp.get("proposed_fix", {})),
          imp.get("guardrail"), imp.get("status"), json.dumps(imp.get("regression", {})),
          json.dumps(imp.get("human_decision")), imp.get("deployed_version")))


def persist_version(agent, vobj):
    _run("INSERT INTO agent_versions (agent,version,prompt_addendum,history) VALUES (%s,%s,%s,%s) "
         "ON CONFLICT (agent) DO UPDATE SET version=EXCLUDED.version,"
         "prompt_addendum=EXCLUDED.prompt_addendum,history=EXCLUDED.history",
         (agent, vobj["version"], vobj["prompt_addendum"], json.dumps(vobj["history"])))


def counts():
    """Totals for the dashboard when running on Postgres. None on error."""
    out = {}
    for key, tbl in (("active_conversations", "conversations"),
                     ("violations", "violations"), ("interventions", "interventions")):
        r = _run(f"SELECT count(*) FROM {tbl}", fetch=True)
        if r is None:
            return None
        out[key] = r[0][0]
    return out
