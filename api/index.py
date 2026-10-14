"""
FastAPI backend for the LTM governed contact-center platform.

Serverless entry for Vercel (exports `app`). Runs locally with:
    uvicorn api.index:app --reload --port 8000

Real LLMs when ANTHROPIC_API_KEY / OPENAI_API_KEY are set; synthetic data only.
"""
import os
import sys

# Ensure the sibling `app/` package is importable on Vercel's Python runtime,
# which does not put this file's directory on sys.path the way local dev does.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware

from app.stores import get_state, reset_state
from app.agents import AGENTS, A
from app.governance import GOV_ACTORS
from app import orchestrator, learning, llm, db, observability

app = FastAPI(title="LTM Governed Contact Center")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def agent_scorecard(state):
    """Latest quality score + status per agent, for the performance matrix."""
    cards = []
    # most recent governance score per agent
    latest = {}
    for t in state.operational.traces:
        if t["action"] == "governance_eval" and t["score"] is not None:
            latest[t["agent"]] = t  # traces are appended in order
    for a in AGENTS:
        aid = a["id"]
        ver = state.learning.current_version(aid)
        tr = latest.get(aid)
        # VA score reflects learning state explicitly
        if aid == "VA":
            viol = any(v["agent"] == "VA" for v in state.operational.violations)
            score = 0.96 if ver >= 2 else (0.78 if viol else 0.91)
        else:
            score = tr["score"] if tr and tr["score"] is not None else 0.9
        status = "Healthy" if score >= 0.9 else ("Watch" if score >= 0.7 else "Flagged")
        cards.append({
            "id": aid, "name": a["name"], "owner": a["owner"], "risk": a["risk"],
            "metric": a["metric"], "tools": a["tools"], "version": ver,
            "score": round(score * 100), "status": status,
        })
    return cards


def dependency_graph(state):
    """Nodes (with live status) + edges for the interactive agent graph."""
    scores = {c["id"]: c for c in agent_scorecard(state)}
    nodes = []
    for a in AGENTS + GOV_ACTORS:
        aid = a["id"]
        if aid in scores:
            st = scores[aid]["status"].lower()
            status = {"healthy": "ok", "watch": "watch", "flagged": "err"}[st]
        else:
            status = "guardian"
        nodes.append({"id": aid, "name": a["name"], "status": status,
                      "kind": "guardian" if aid in ("AU", "HITL") else "agent"})
    edges = [
        ["VA", "PV"], ["VA", "KR"], ["VA", "TR"],
        ["PV", "NBA"], ["KR", "NBA"], ["TR", "NBA"],
        ["NBA", "VA"], ["VA", "SUM"],
    ]
    monitors = [["AU", x["id"]] for x in AGENTS] + [["HITL", "AU"]]
    return {"nodes": nodes, "edges": edges, "monitors": monitors}


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    state = get_state()
    return {"ok": True, "llm": llm.llm_status(), "embeddings": state.embed_mode,
            "db": db.db_status(),
            "observability": observability.status(),
            "realtime": bool(os.environ.get("OPENAI_API_KEY")),
            "data": {"documents": len(state.knowledge.docs),
                     "policies": len(state.operational.policies)}}


@app.get("/api/agents")
def agents_route():
    state = get_state()
    return {"agents": agent_scorecard(state),
            "guardians": GOV_ACTORS}


@app.get("/api/policies")
def policies_route():
    state = get_state()
    return {"policies": list(state.operational.policies.values())}


@app.get("/api/documents")
def documents_route():
    state = get_state()
    return {"documents": state.knowledge.list_docs(),
            "embed_mode": state.embed_mode}


@app.post("/api/documents")
def add_document(doc: dict = Body(...)):
    state = get_state()
    saved = state.knowledge.add_document({
        "doc_id": doc.get("doc_id") or f"DOC-{len(state.knowledge.docs)+1}",
        "title": doc.get("title", "Untitled"),
        "category": doc.get("category", "Uploaded"),
        "roles": doc.get("roles", []),
        "text": doc.get("text", ""),
    })
    return {"saved": saved}


@app.post("/api/retrieve")
def retrieve_route(body: dict = Body(...)):
    state = get_state()
    docs = state.knowledge.retrieve(body.get("query", ""), body.get("role", ""),
                                    int(body.get("k", 3)))
    return {"results": docs}


@app.post("/api/call/run")
def run_call_route(body: dict = Body(default={})):
    state = get_state()
    result = orchestrator.run_call(
        state, policy_id=body.get("policy_id", "LM-AUTO-88123"),
        brain=body.get("brain", ""))
    return result


@app.get("/api/traces/{conv_id}")
def traces_route(conv_id: str):
    state = get_state()
    return {"traces": state.operational.traces_for(conv_id)}


@app.get("/api/dashboard")
def dashboard_route():
    state = get_state()
    op = state.operational
    improvements = list(state.learning.improvements.values())
    pending = [i for i in improvements if i["status"] in ("proposed", "tested")]
    cards = agent_scorecard(state)
    pass_rate = round(sum(c["score"] for c in cards) / len(cards)) if cards else 0
    convs = sorted(op.conversations.values(), key=lambda c: c["started_at"])
    latest_conv = convs[-1]["conversation_id"] if convs else None
    return {
        "kpis": {
            "agents_registered": len(AGENTS) + len(GOV_ACTORS),
            "active_conversations": len(op.conversations),
            "eval_pass_rate": pass_rate,
            "violations": len(op.violations),
            "interventions": len(op.interventions),
            "learning_pending": len(pending),
        },
        "matrix": cards,
        "violations": op.violations[-10:],
        "interventions": op.interventions[-10:],
        "graph": dependency_graph(state),
        "latest_conversation": latest_conv,
    }


@app.get("/api/learning")
def learning_route():
    state = get_state()
    return {"improvements": list(state.learning.improvements.values()),
            "eval_cases": state.learning.eval_cases,
            "versions": state.learning.versions}


@app.post("/api/learning/{imp_id}/regression")
def regression_route(imp_id: str):
    state = get_state()
    return learning.run_regression(state, imp_id)


@app.post("/api/learning/{imp_id}/approve")
def approve_route(imp_id: str):
    state = get_state()
    return learning.approve(state, imp_id)


@app.post("/api/reset")
def reset_route():
    reset_state()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Live voice — OpenAI Realtime (WebRTC). The browser streams mic audio directly
# to OpenAI with a short-lived ephemeral key minted here; the standard API key
# never leaves the server. We also build the grounded agent instructions from
# the selected policy so the Voice AI only states coverage on that policy.
# ---------------------------------------------------------------------------
REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1")
REALTIME_VOICE = os.environ.get("OPENAI_REALTIME_VOICE", "marin")


def build_voice_instructions(state, policy_id: str) -> str:
    policy = state.operational.get_policy(policy_id)
    cov = policy.get("coverages", {}) if policy else {}
    rr = cov.get("rental_reimbursement", {})
    rental = (f"INCLUDED (${rr.get('daily_limit')}/day up to {rr.get('max_days')} days)"
              if rr.get("included") else "NOT included")
    coll = cov.get("collision", {})
    comp = cov.get("comprehensive", {})
    return (
        "You are a Liberty Mutual auto-claims Voice AI agent on a phone call. This is a "
        "SYNTHETIC demo with fictional data — no real customers. Be warm, concise and natural; "
        "speak in short spoken sentences.\n\n"
        f"The caller is {policy.get('holder','the policyholder')}, policy {policy_id}, "
        f"vehicle {policy.get('vehicle','on file')}.\n"
        "VERIFIED POLICY COVERAGES (this is the single source of truth — never state a coverage "
        "that is not listed here):\n"
        f"- Collision: {'included, deductible $'+str(coll.get('deductible')) if coll.get('included') else 'not included'}\n"
        f"- Comprehensive: {'included, deductible $'+str(comp.get('deductible')) if comp.get('included') else 'not included'}\n"
        f"- Rental reimbursement: {rental}\n"
        f"- Roadside assistance: {'included' if cov.get('roadside',{}).get('included') else 'not included'}\n\n"
        "RULES (governance guardrails):\n"
        "1. Only state a coverage as covered if it is listed above. If a caller asks about rental "
        "and it is NOT included, say plainly it is not covered and offer alternatives (out of "
        "pocket, preferred-vendor discount). Never promise coverage the policy does not have.\n"
        "2. Never approve or promise a settlement or payout amount — route money decisions to a "
        "human adjuster.\n"
        "3. For a new loss, take the FNOL: ask what happened, injuries, whether the car is "
        "drivable, then say you've opened a claim.\n"
        "4. If anyone is injured, say a human adjuster will be assigned.\n"
        "Open by greeting the caller and asking how you can help with their claim today."
    )


@app.post("/api/realtime/token")
def realtime_token(body: dict = Body(default={})):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY is not set on the server. Add it in Vercel "
                "Environment Variables and redeploy to enable live voice."}
    state = get_state()
    policy_id = body.get("policy_id", "LM-AUTO-88123")
    instructions = build_voice_instructions(state, policy_id)
    import json as _json
    import urllib.request as _url
    payload = _json.dumps({
        "session": {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "audio": {"output": {"voice": REALTIME_VOICE}},
        }
    }).encode()
    req = _url.Request(
        "https://api.openai.com/v1/realtime/client_secrets",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _url.urlopen(req, timeout=20) as resp:
            data = _json.loads(resp.read().decode())
    except Exception as e:
        detail = ""
        try:
            detail = e.read().decode()  # type: ignore[attr-defined]
        except Exception:
            detail = str(e)
        return {"error": "Could not mint a realtime session.", "detail": detail[:500]}
    value = data.get("value") or (data.get("client_secret") or {}).get("value")
    return {"value": value, "expires_at": data.get("expires_at"),
            "model": REALTIME_MODEL, "voice": REALTIME_VOICE,
            "instructions": instructions, "policy_id": policy_id}


# convenience root
@app.get("/api")
def root():
    return {"service": "LTM Governed Contact Center", "docs": "/api/health"}


# Optional single-server mode: if a built SPA exists next to the repo, serve it.
# (On Vercel the static build is served separately, so skip this there.)
_DIST = os.path.join(os.path.dirname(__file__), "..", "dist")
if not os.environ.get("VERCEL") and os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="spa")
