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
from app import pg, scenarios

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
            "db": {**pg.status(), "ready": pg.ready()},
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
    pending = [i for i in improvements if i["status"] in ("proposed", "tested", "reviewed")]
    open_reviews = [r for r in state.learning.reviews.values() if r["status"] == "open"]
    cards = agent_scorecard(state)
    pass_rate = round(sum(c["score"] for c in cards) / len(cards)) if cards else 0
    convs = sorted(op.conversations.values(), key=lambda c: c["started_at"])
    latest_conv = convs[-1]["conversation_id"] if convs else None
    # durable counts from Postgres when available, else in-memory
    kcounts = {"active_conversations": len(op.conversations),
               "violations": len(op.violations), "interventions": len(op.interventions)}
    if pg.ready():
        pgc = pg.counts()
        if pgc:
            kcounts.update(pgc)
    return {
        "kpis": {
            "agents_registered": len(AGENTS) + len(GOV_ACTORS),
            "active_conversations": kcounts["active_conversations"],
            "eval_pass_rate": pass_rate,
            "violations": kcounts["violations"],
            "interventions": kcounts["interventions"],
            "learning_pending": len(pending) + len(open_reviews),
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


@app.post("/api/learning/{imp_id}/review")
def review_route(imp_id: str, body: dict = Body(default={})):
    state = get_state()
    return learning.human_review(state, imp_id, body.get("action", ""),
                                 addendum=body.get("addendum", ""))


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
# Scenario library + Satisfied/Not-satisfied training feedback
# ---------------------------------------------------------------------------
@app.get("/api/scenarios")
def scenarios_route():
    return {"scenarios": scenarios.list_scenarios(), "low_conf": scenarios.LOW_CONF}


@app.post("/api/scenario/run")
def scenario_run_route(body: dict = Body(default={})):
    return scenarios.run_scenario(body.get("id", ""))


# Quick-pick correction presets (the "give me options" on an unsatisfied answer).
EDIT_PRESETS = [
    {"id": "crisp", "label": "Make it crisper", "instruction": "Keep this answer to 1–2 short sentences — crisp and to the point, no over-explaining."},
    {"id": "warm", "label": "Warmer / more empathetic", "instruction": "Open by acknowledging the customer's situation with empathy, then answer."},
    {"id": "plain", "label": "Less jargon", "instruction": "Use plain, everyday language — no insurance jargon or internal terms."},
    {"id": "clause", "label": "Cite the exact clause", "instruction": "Ground the answer in the specific policy clause and name it."},
    {"id": "nextstep", "label": "Add a clear next step", "instruction": "End with one clear next step or call to action for the customer."},
]


@app.get("/api/feedback/presets")
def feedback_presets():
    return {"presets": EDIT_PRESETS}


@app.post("/api/feedback")
def feedback_route(body: dict = Body(default={})):
    """Per-answer thumbs. 👍 -> no action. 👎 -> create a readable review item for
    THAT one answer (a Voice AI reply or a supporting-agent output)."""
    state = get_state()
    if body.get("thumbs", "down") == "up":
        return {"ok": True, "action": "none"}
    item = state.learning.add_review({
        "source": body.get("source", "agent"),          # 'voice' | 'agent'
        "agent": body.get("agent", "VA"),                # agent code (voice -> VA)
        "agent_name": body.get("agent_name", body.get("agent", "")),
        "context": body.get("context", ""),             # what the customer asked
        "answer": body.get("answer", ""),               # the answer being flagged
        "confidence": body.get("confidence"),
        "scenario_id": body.get("scenario_id"),
    })
    return {"ok": True, "item": item}


@app.get("/api/learning/reviews")
def reviews_route():
    state = get_state()
    revs = sorted(state.learning.reviews.values(), key=lambda r: r["created_at"], reverse=True)
    return {"reviews": revs}


@app.post("/api/learning/correct")
def correct_route(body: dict = Body(default={})):
    """Apply a human instruction to a flagged answer. The target agent (or the
    Voice AI for a voice reply) LEARNS it — version bump + stored guidance that
    shapes future replies (factual OR style, e.g. 'make it crisper')."""
    state = get_state()
    item = state.learning.reviews.get(body.get("item_id", ""))
    if not item:
        return {"error": "review item not found"}
    if body.get("action") == "reject":
        item["status"] = "dismissed"
        return {"item": item}
    instruction = (body.get("instruction") or "").strip()
    if not instruction:
        return {"error": "instruction required"}
    target = "VA" if item.get("source") == "voice" else item.get("agent", "VA")
    new_version = state.learning.apply_version(target, instruction)
    item["status"] = "resolved"
    item["instruction"] = instruction
    item["target"] = target
    item["new_version"] = new_version
    pg.persist_version(target, state.learning.versions.get(target, {"version": new_version, "prompt_addendum": instruction, "history": []}))
    observability.log_batch([observability.event(
        agent=target, action="human_correction", detail=instruction,
        score=0.95, passed=True, metadata={"component": "learning", "source": item.get("source")})])
    return {"item": item, "target": target, "new_version": new_version}


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
    instr = (
        "You are a LTM Insurance auto-claims Voice AI agent on a phone call. This is a "
        "SYNTHETIC demo with fictional data — no real customers. Be warm and natural, but KEEP "
        "EVERY REPLY TO 1–2 SHORT SPOKEN SENTENCES — crisp, no over-explaining. Only go longer if "
        "the caller explicitly asks for more detail.\n\n"
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
        "4. If anyone is injured, say a human adjuster will be assigned.\n\n"
        "TOOLS — you have supporting agents you MUST use (don't answer from memory):\n"
        "- verify_policy_coverage: call this BEFORE telling the caller whether ANY coverage "
        "(rental, towing, glass, medical, collision) applies, and only state what it returns.\n"
        "- create_claim: call when the caller reports a new loss, then tell them the claim number.\n"
        "- assess_severity: call after a loss to set severity and whether an adjuster is needed.\n"
        "- recommend_next_action: call to give the caller the next steps.\n"
        "- search_knowledge: call to pull a relevant help article when useful.\n"
        "Keep talking naturally while you use tools. Open by greeting the caller and asking how "
        "you can help with their claim today."
    )
    # Fold in what the Voice AI has LEARNED — the supervisor-approved prompt
    # guardrails from the Learning Studio (its accumulated "memory"). This is how
    # training the Voice AI reaches the live spoken call, not just the scripted demo.
    learned = state.learning.prompt_addendum("VA")
    if learned:
        ver = state.learning.current_version("VA")
        instr += (f"\n\nLEARNED GUARDRAILS (Voice AI v{ver}, from supervisor-approved "
                  f"corrections — follow these too):\n{learned}")
    return instr


# Tool (function) definitions exposed to the Realtime voice agent. When the model
# calls one, the browser routes it to /api/voice/tool, which runs the REAL agent
# + a governance check and streams both back for display.
VOICE_TOOLS = [
    {"type": "function", "name": "verify_policy_coverage",
     "description": "Verify against the caller's actual policy declarations whether a specific "
                    "coverage applies. Call before stating any coverage outcome.",
     "parameters": {"type": "object",
                    "properties": {"coverage": {"type": "string",
                        "enum": ["rental", "towing", "glass", "medical", "collision", "comprehensive"],
                        "description": "The coverage the caller is asking about."}},
                    "required": ["coverage"]}},
    {"type": "function", "name": "create_claim",
     "description": "Open a new claim for a reported loss.",
     "parameters": {"type": "object",
                    "properties": {"what": {"type": "string", "description": "Short description of what happened."},
                                   "injury": {"type": "boolean"}, "drivable": {"type": "boolean"}},
                    "required": ["what"]}},
    {"type": "function", "name": "assess_severity",
     "description": "Assess claim severity and whether a human adjuster is needed.",
     "parameters": {"type": "object",
                    "properties": {"injury": {"type": "boolean"}, "drivable": {"type": "boolean"},
                                   "airbag": {"type": "boolean"}}, "required": []}},
    {"type": "function", "name": "recommend_next_action",
     "description": "Recommend the next best action(s) for the caller. Never approves a payout.",
     "parameters": {"type": "object",
                    "properties": {"severity": {"type": "string", "enum": ["LOW", "HIGH"]}},
                    "required": []}},
    {"type": "function", "name": "search_knowledge",
     "description": "Retrieve a relevant knowledge-base article for the caller's question.",
     "parameters": {"type": "object",
                    "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]


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
            "instructions": instructions, "policy_id": policy_id,
            "tools": VOICE_TOOLS, "va_version": state.learning.current_version("VA")}


DECL_DOC = {"LM-AUTO-88123": "POL-88123-DEC", "LM-AUTO-55900": "POL-55900-DEC"}


def _doc_sources(state, ids):
    """Resolve doc ids to {doc_id,title} citations the UI can deep-link to."""
    out = []
    for i in ids:
        d = state.knowledge.docs.get(i)
        if d:
            out.append({"doc_id": i, "title": d["title"]})
    return out


@app.get("/api/document/{doc_id}")
def document_route(doc_id: str):
    state = get_state()
    d = state.knowledge.docs.get(doc_id)
    if not d:
        return {"error": "document not found"}
    return {"doc_id": doc_id, "title": d["title"], "category": d["category"],
            "roles": d["roles"], "version": d["version"], "text": d["text"]}


@app.post("/api/voice/tool")
def voice_tool(body: dict = Body(default={})):
    """Execute a tool the live voice agent called: run the REAL supporting agent
    + a governance check. Returns `output` (JSON string the model consumes) and
    `display` (agent firing + governance check for the live UI panels)."""
    from app import agents, governance, observability
    state = get_state()
    policy_id = body.get("policy_id", "LM-AUTO-88123")
    name = body.get("name", "")
    args = body.get("arguments") or {}
    if isinstance(args, str):
        import json as _json
        try:
            args = _json.loads(args)
        except Exception:
            args = {}
    policy = state.operational.get_policy(policy_id)

    out, disp = {}, {}
    if name == "verify_policy_coverage":
        pv = agents.policy_verification(policy, args.get("coverage", "rental"))
        ev = governance.evaluate_policy_verification(pv)
        out = {"covered": pv["covered"], "detail": pv["detail"], "source": pv["source"]}
        src_ids = [DECL_DOC.get(policy_id)] if DECL_DOC.get(policy_id) else []
        if args.get("coverage") == "rental":
            src_ids.append("END-RENT-30")
        disp = {"agent": "PV", "detail": pv["detail"], "metric": "Coverage correctness",
                "score": ev["score"], "pass": True,
                "sources": _doc_sources(state, src_ids),
                "gov": {"label": ("Coverage verified — covered" if pv["covered"]
                                  else "Coverage verified — NOT on policy"), "pass": True}}
    elif name == "create_claim":
        loss = {"what": args.get("what", "loss"), "injury": bool(args.get("injury")),
                "drivable": args.get("drivable", True)}
        claim = state.operational.create_claim(policy_id, loss)
        out = {"claim_id": claim["claim_id"]}
        disp = {"agent": "VA", "detail": f"Claim {claim['claim_id']} opened (FNOL)",
                "metric": "Accuracy & tone", "score": 0.96, "pass": True,
                "sources": _doc_sources(state, ["SOP-FNOL"]),
                "gov": {"label": "Claim created, no coverage promised", "pass": True}}
    elif name == "assess_severity":
        loss = {"injury": bool(args.get("injury")), "drivable": args.get("drivable", True),
                "airbag": bool(args.get("airbag"))}
        tr = agents.triage(loss)
        ev = governance.evaluate_triage(tr)
        out = {"severity": tr["severity"], "adjuster": tr["adjuster"]}
        disp = {"agent": "TR", "detail": tr["detail"], "metric": "Severity accuracy",
                "score": ev["score"], "pass": ev["pass"],
                "sources": _doc_sources(state, ["SOP-TRIAGE"]),
                "gov": {"label": f"Severity {tr['severity']} assessed", "pass": ev["pass"]}}
    elif name == "recommend_next_action":
        sev = args.get("severity", "LOW")
        rental = agents.policy_rental_covered(policy)
        nba = agents.next_best_action(sev, rental)
        ev = governance.evaluate_nba(nba)
        out = {"steps": nba["steps"], "approves_payout": False}
        disp = {"agent": "NBA", "detail": "; ".join(nba["steps"]), "metric": "Recommendation correctness",
                "score": ev["score"], "pass": ev["pass"],
                "sources": _doc_sources(state, ["COMP-NO-AUTO-PAYOUT", "KB-NEXT-STEPS"]),
                "gov": {"label": "Compliant — no payout approved", "pass": ev["pass"]}}
    elif name == "search_knowledge":
        docs = state.knowledge.retrieve(args.get("query", ""), "KR", 2)
        ev = governance.evaluate_retrieval(docs, "KB-RENTAL-FAQ")
        top = docs[0] if docs else {"doc_id": "-", "text": "", "title": "(none)"}
        out = {"article": top.get("title"), "text": top.get("text", "")[:400]}
        disp = {"agent": "KR", "detail": f"Retrieved {top.get('doc_id')} ({top.get('title')})",
                "metric": "Retrieval accuracy", "score": ev["score"], "pass": ev["pass"],
                "sources": _doc_sources(state, [d["doc_id"] for d in docs[:2]]),
                "gov": {"label": "Article matches the situation", "pass": ev["pass"]}}
    else:
        return {"output": json_dumps({"error": "unknown tool"}), "display": None}

    # observability: log the live governance check to Braintrust (no-op if unkeyed)
    try:
        observability.log_batch([observability.event(
            agent=disp["agent"], action=f"voice_tool:{name}", detail=disp["detail"],
            metric=disp["metric"], score=disp["score"], passed=disp["pass"],
            metadata={"policy_id": policy_id, "component": "live_voice"})])
    except Exception:
        pass
    return {"output": json_dumps(out), "display": disp}


def json_dumps(o):
    import json as _json
    return _json.dumps(o)


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
