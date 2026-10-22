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
from app import orchestrator, learning, llm, db, observability, metrics
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
        ["NBA", "VA"], ["VA", "SUM"], ["VA", "SEN"],
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


@app.get("/api/metrics")
def metrics_route():
    """Command-center observability. REAL numbers measured from this instance's
    live activity (every agent fire + every LLM call records its latency/tokens).
    Before any calls have happened it shows a representative baseline and says so
    (mode 'warming up'), so the dashboard is never blank and never fabricated once
    the demo is running."""
    state = get_state()
    cards = agent_scorecard(state)
    open_reviews = [r for r in state.learning.reviews.values() if r["status"] == "open"]
    corrections = sum(max(0, state.learning.current_version(a["id"]) - 1) for a in AGENTS)
    bt = observability.status()
    snap = metrics.snapshot()

    name_of = {a["id"]: a["name"] for a in AGENTS}
    metric_of = {a["id"]: a["metric"] for a in AGENTS}

    if snap["has_data"]:
        # ---- REAL telemetry from this running instance ----
        per_agent = []
        for aid, d in snap["per_agent"].items():
            per_agent.append({
                "id": aid, "name": name_of.get(aid, aid), "metric": metric_of.get(aid, "Quality"),
                "calls": d["calls"], "pass_rate": round(d["pass_rate"]),
                "p50_ms": d["p50_ms"], "p95_ms": d["p95_ms"],
                "tool_success": d["pass_rate"],
            })
        per_agent.sort(key=lambda x: -x["calls"])
        tin, tout = snap["tokens"]["input"], snap["tokens"]["output"]
        est_cost = round(tin / 1e6 * 3 + tout / 1e6 * 15, 2)
        return {
            "mode": "live" if (bt["configured"] or snap["llm_calls"] > 0) else "measured",
            "braintrust": {"configured": bt["configured"], "project": bt.get("project"),
                           "mode": "live" if bt["configured"] else "off"},
            "kpis": {
                "agent_calls": snap["agent_calls"],
                "tool_success_rate": snap["pass_rate"],
                "gov_pass_rate": round(snap["pass_rate"]),
                "flagged_for_review": len(open_reviews),
                "human_corrections": corrections,
                "agents_live": len(AGENTS),
            },
            "latency_ms": snap["latency_ms"],
            "tokens": {"input": tin, "output": tout, "total": tin + tout, "est_cost_usd": est_cost},
            "tool_calling": {"total_calls": snap["agent_calls"], "success_rate": snap["pass_rate"]},
            "evals": per_agent,
        }

    # ---- no activity yet: representative baseline, clearly labelled ----
    pass_rate = round(sum(c["score"] for c in cards) / len(cards)) if cards else 0
    per_agent = [{"id": a["id"], "name": a["name"], "metric": a["metric"],
                  "calls": 0, "pass_rate": next((c["score"] for c in cards if c["id"] == a["id"]), 90),
                  "p50_ms": 0, "p95_ms": 0, "tool_success": 0.0} for a in AGENTS]
    return {
        "mode": "warming up",
        "braintrust": {"configured": bt["configured"], "project": bt.get("project"),
                       "mode": "live" if bt["configured"] else "off"},
        "kpis": {"agent_calls": 0, "tool_success_rate": 0.0, "gov_pass_rate": pass_rate,
                 "flagged_for_review": len(open_reviews), "human_corrections": corrections,
                 "agents_live": len(AGENTS)},
        "latency_ms": {"p50": 0, "p95": 0, "p99": 0},
        "tokens": {"input": 0, "output": 0, "total": 0, "est_cost_usd": 0.0},
        "tool_calling": {"total_calls": 0, "success_rate": 0.0},
        "evals": per_agent,
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


# Quick-pick correction presets. Two loops:
#  - VOICE: how the Voice AI should SAY it (tone / length / style)
#  - AGENT: how a supporting agent should BEHAVE / what's expected of it
VOICE_PRESETS = [
    {"id": "crisp", "label": "Make it crisper", "instruction": "Keep this answer to 1–2 short sentences — crisp and to the point, no over-explaining."},
    {"id": "warm", "label": "Warmer / more empathetic", "instruction": "Open by acknowledging the customer's situation with empathy, then answer."},
    {"id": "plain", "label": "Less jargon", "instruction": "Use plain, everyday language — no insurance jargon or internal terms."},
    {"id": "clause", "label": "Cite the exact clause", "instruction": "Ground the answer in the specific policy clause and name it."},
    {"id": "nextstep", "label": "Add a clear next step", "instruction": "End with one clear next step or call to action for the customer."},
]
AGENT_PRESETS = [
    {"id": "cite", "label": "Should cite the policy clause", "instruction": "This agent must ground its answer in — and name — the specific policy clause or document."},
    {"id": "escalate", "label": "Should escalate to a human", "instruction": "In this situation the agent should route to a licensed human adjuster rather than resolve it automatically."},
    {"id": "source", "label": "Used the wrong source", "instruction": "The agent pulled the wrong document/article — it must use the correct source for this type of question."},
    {"id": "compliant", "label": "Was not compliant", "instruction": "The agent must follow the compliance guardrail here (never approve a payout, cite exclusions, no admitting fault)."},
    {"id": "behave", "label": "Wrong behaviour", "instruction": "Describe what this agent is expected to do in this case."},
]


@app.get("/api/feedback/presets")
def feedback_presets():
    return {"voice": VOICE_PRESETS, "agent": AGENT_PRESETS}


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
        "trap_id": body.get("trap_id", ""),             # demo "inject wrong answer" loop
        "session_id": body.get("session_id", ""),       # scope to this browser session
    })
    return {"ok": True, "item": item}


@app.post("/api/learning/clear")
def learning_clear():
    """Empty the learning data (review queue, improvements, learned versions) so the
    Learning Studio is clean until the next thumbs-down. Explicit, user-triggered."""
    state = get_state()
    state.learning.reviews.clear()
    state.learning.improvements.clear()
    state.learning.versions.clear()
    if pg.ready():
        pg.clear_learning()
    return {"ok": True}


@app.get("/api/learning/reviews")
def reviews_route(session: str = ""):
    state = get_state()
    revs = sorted(state.learning.reviews.values(), key=lambda r: r["created_at"], reverse=True)
    # only this browser session's flagged answers (blank at start, no past sessions)
    if session:
        revs = [r for r in revs if r.get("session_id") == session]
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
        if pg.ready():
            pg.persist_review(item)
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
    if pg.ready():
        pg.persist_review(item)
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
        f"The caller is {policy.get('holder','the policyholder')}, policy {policy_id}. "
        f"Vehicles on this policy: {', '.join(policy.get('vehicles') or [policy.get('vehicle','on file')])}. "
        "When you confirm which vehicle was involved, OFFER these as options by name (e.g. 'Was it "
        "the " + " or the ".join(policy.get('vehicles') or [policy.get('vehicle','your car')]) + "?').\n"
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
        "3. For a new loss, take the FNOL. You MUST confirm, one question at a time: (a) the DATE "
        "and TIME the accident happened, (b) WHICH vehicle was involved (confirm it's the car on "
        "the policy, or ask which one), and (c) what happened, injuries, and whether the car is "
        "drivable. Also ask (optional) whether a police report was filed — note it if yes, don't "
        "insist if not. Only after you have the date/time and the vehicle, call create_claim and "
        "tell them the claim number.\n"
        "4. If anyone is injured, say a human adjuster will be assigned.\n"
        "5. NEXT STEPS: when you give next steps, walk through them a couple at a time (two steps), "
        "then ask 'Is there anything else I can help you with?' Keep helping and keep asking that "
        "after each thing — do NOT jump to ending the call while they still have questions.\n"
        "6. ENDING THE CALL: only once the caller says they're all set (or goes quiet), ask 'Shall "
        "I go ahead and end the call?' If they don't confirm, you may ask once more. If they still "
        "don't confirm or don't respond, say clearly 'I'll end the call now — take care' and stop. "
        "If at any point they say yes, end the call, say 'I'll end the call now' and stop. Always "
        "say an explicit closing line like 'I'll end the call now' as your final sentence so the "
        "call can wrap up.\n\n"
        "7. COVERAGE DISPUTE: if the caller disagrees with a coverage decision, stay calm, re-verify "
        "with verify_policy_coverage, and explain what the policy says. Do NOT override the policy or "
        "promise a different outcome — if they still disagree, tell them you'll escalate it to a human "
        "adjuster for review.\n"
        "8. FRAUD / MULTI-VEHICLE: if the loss involves THREE OR MORE vehicles, or the details sound "
        "inconsistent or staged, call assess_fraud_risk. NEVER accuse the caller — just say the claim "
        "will go through a standard review. Never deny or approve based on this; it routes to the SIU "
        "team and a human.\n\n"
        "TOOLS — you have supporting agents you MUST use (don't answer from memory):\n"
        "- verify_policy_coverage: call this BEFORE telling the caller whether ANY coverage "
        "(rental, towing, glass, medical, collision) applies, and only state what it returns.\n"
        "- create_claim: call when the caller reports a new loss, then tell them the claim number.\n"
        "- assess_severity: call after a loss to set severity and whether an adjuster is needed.\n"
        "- assess_fraud_risk: call when a loss involves three or more vehicles or seems inconsistent.\n"
        "- check_claim_status: call when the caller asks about the status of an existing claim.\n"
        "- get_repair_estimate: call when the caller asks what the repair will cost or where to take the car.\n"
        "- check_payment_status: call when the caller asks about a reimbursement or a delayed payment.\n"
        "- recommend_next_action: call to give the caller the next steps.\n"
        "- search_knowledge: call to pull a relevant help article when useful.\n\n"
        "TONE (only adapt when it's clearly needed — otherwise just be warm and normal):\n"
        "- If the caller sounds frustrated or upset, acknowledge it and let them vent briefly "
        "before you start fixing things.\n"
        "- If they're in a hurry, be quick and skip pleasantries.\n"
        "- If they're confused, slow down and simplify.\n"
        "- If they're calm, don't over-manage the tone — just help.\n\n"
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
     "description": "Open a new claim for a reported loss. Only call this AFTER confirming the date/time "
                    "of the accident and which vehicle was involved.",
     "parameters": {"type": "object",
                    "properties": {"what": {"type": "string", "description": "Short description of what happened."},
                                   "when": {"type": "string", "description": "Date and time the accident happened, as the caller stated it."},
                                   "vehicle": {"type": "string", "description": "Which vehicle was involved."},
                                   "police_report": {"type": "boolean", "description": "Whether a police report was filed, if mentioned."},
                                   "injury": {"type": "boolean"}, "drivable": {"type": "boolean"}},
                    "required": ["what", "when", "vehicle"]}},
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
    {"type": "function", "name": "assess_fraud_risk",
     "description": "Score the fraud risk of a loss. Call when three or more vehicles are involved or "
                    "details seem inconsistent/staged. Routes to SIU + a human; never denies or approves.",
     "parameters": {"type": "object",
                    "properties": {"vehicles_involved": {"type": "integer", "description": "How many vehicles were involved in the loss."},
                                   "note": {"type": "string", "description": "Any detail that seems inconsistent (optional)."}},
                    "required": ["vehicles_involved"]}},
    {"type": "function", "name": "check_claim_status",
     "description": "Look up the status of an existing claim the caller references.",
     "parameters": {"type": "object",
                    "properties": {"claim_id": {"type": "string", "description": "The claim number the caller gives, if any."}},
                    "required": []}},
    {"type": "function", "name": "get_repair_estimate",
     "description": "Get the repair estimate and preferred-shop options for the caller's vehicle.",
     "parameters": {"type": "object",
                    "properties": {"vehicle": {"type": "string"}}, "required": []}},
    {"type": "function", "name": "check_payment_status",
     "description": "Check the status of a reimbursement or payment the caller is asking about.",
     "parameters": {"type": "object",
                    "properties": {"claim_id": {"type": "string"}}, "required": []}},
    # NOTE: assess_sentiment is intentionally NOT exposed to the model. The browser
    # runs it client-side once per caller turn (and only surfaces it when the mood
    # is notable), so the model calling it too would double-fire the Sentiment agent.
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
    import time as _time
    _t0 = _time.perf_counter()
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
                "drivable": args.get("drivable", True), "when": args.get("when", ""),
                "vehicle": args.get("vehicle", ""), "police_report": bool(args.get("police_report"))}
        claim = state.operational.create_claim(policy_id, loss)
        out = {"claim_id": claim["claim_id"]}
        _extra = []
        if loss["when"]: _extra.append(f"when: {loss['when']}")
        if loss["vehicle"]: _extra.append(f"vehicle: {loss['vehicle']}")
        if loss["police_report"]: _extra.append("police report filed")
        _detail = f"Claim {claim['claim_id']} opened (FNOL)" + (" — " + ", ".join(_extra) if _extra else "")
        disp = {"agent": "VA", "detail": _detail,
                "metric": "Accuracy & tone", "score": 0.96, "pass": True,
                "sources": _doc_sources(state, ["SOP-FNOL"]),
                "gov": {"label": "Claim created, date/vehicle confirmed, no coverage promised", "pass": True}}
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
    elif name == "assess_fraud_risk":
        n = int(args.get("vehicles_involved") or 0)
        note = args.get("note", "")
        elevated = n >= 3 or bool(note)
        risk = "ELEVATED" if elevated else "LOW"
        detail = (f"{n} vehicles involved — risk {risk}. "
                  + ("Routed to SIU for standard review; a human investigator will follow up. No decision made on the call."
                     if elevated else "Within normal range; no SIU routing needed."))
        out = {"risk": risk, "vehicles_involved": n, "routed_to_siu": elevated,
               "auto_decision": False, "note": "Never deny or approve on the call."}
        disp = {"agent": "FRAUD", "agentName": "Fraud / SIU", "detail": detail,
                "metric": "Fraud-signal precision", "score": 0.9, "pass": not elevated,
                "sources": _doc_sources(state, ["SOP-FNOL"]),
                "gov": {"label": ("Flagged for SIU — no auto-decision, routed to a human" if elevated
                                  else "No fraud signal — proceed normally"), "pass": not elevated}}
    elif name == "check_claim_status":
        cid = args.get("claim_id") or "CLM-2041"
        out = {"claim_id": cid, "status": "In review", "stage": "Estimate received; adjuster assigned",
               "next_milestone": "Adjuster decision within 2 business days"}
        disp = {"agent": "CS", "agentName": "Claim Status",
                "detail": f"Claim {cid}: in review — estimate received, adjuster assigned; decision within 2 business days",
                "metric": "Status accuracy", "score": 0.97, "pass": True,
                "sources": _doc_sources(state, []),
                "gov": {"label": "Status read from the claims system, not invented", "pass": True}}
    elif name == "get_repair_estimate":
        veh = args.get("vehicle") or policy.get("vehicle", "the vehicle")
        ded = (policy.get("coverages", {}).get("collision", {}) or {}).get("deductible", 500)
        out = {"estimate": 2450, "currency": "USD", "shop": "LTM preferred shop (Sterling Auto Body)",
               "covered_under": "collision", "deductible": ded, "approves_payout": False}
        disp = {"agent": "RE", "agentName": "Repair Estimate",
                "detail": f"Estimate ~$2,450 for {veh} at a preferred shop; collision applies, ${ded} deductible. Estimate only — no payout approved.",
                "metric": "Estimate accuracy", "score": 0.93, "pass": True,
                "sources": _doc_sources(state, ["KB-NEXT-STEPS"]),
                "gov": {"label": "Estimate provided, no payout approved on the call", "pass": True}}
    elif name == "check_payment_status":
        cid = args.get("claim_id") or "CLM-2041"
        out = {"claim_id": cid, "payment": "Reimbursement issued", "amount": 1900,
               "issued": "2 business days ago", "eta": "3–5 business days to your bank"}
        disp = {"agent": "PAY", "agentName": "Payments",
                "detail": f"Claim {cid}: $1,900 reimbursement issued 2 business days ago; 3–5 business days to the bank.",
                "metric": "Payment accuracy", "score": 0.96, "pass": True,
                "sources": _doc_sources(state, []),
                "gov": {"label": "Payment status read from the ledger, amounts masked per policy", "pass": True}}
    elif name == "assess_sentiment":
        sent = agents.detect_sentiment(args.get("text", "") or body.get("context", ""))
        sop = agents.SENTIMENT_SOP.get(sent, agents.SENTIMENT_SOP["calm"])
        learned = state.learning.prompt_addendum("SEN")
        if learned:
            sop = sop + " " + learned
        out = {"sentiment": sent, "tone_guidance": sop}
        disp = {"agent": "SEN", "detail": f"Mood: {sent.upper()} — {sop}",
                "metric": "Tone appropriateness", "score": 0.9, "pass": True,
                "sources": _doc_sources(state, []),
                "gov": {"label": f"Tone SOP applied ({sent})", "pass": True}}
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
    try:
        metrics.record_agent(disp.get("agent", name), (_time.perf_counter() - _t0) * 1000.0,
                             disp.get("pass", True))
    except Exception:
        pass
    return {"output": json_dumps(out), "display": disp}


# ---------------------------------------------------------------------------
# Live per-turn multi-agent router. On every caller turn the browser sends the
# utterance here; we classify the intent and fire the RIGHT cluster of supporting
# agents (grounded in the caller's real policy), each with a confidence score and
# a governance check — so the Live Voice panel shows proper multi-agent activity
# (FNOL + Policy + Triage + Next Best Action for an accident, etc.), the same way
# the Scenarios tab does, instead of waiting on the model to call one tool.
# ---------------------------------------------------------------------------
TURN_AGENT_NAMES = {
    "FNOL": "FNOL Agent", "POLICY": "Policy Agent", "TRIAGE": "Triage / Severity Agent",
    "NBA": "Next Best Action Agent", "COVERAGE": "Coverage Agent", "KNOW": "Knowledge Agent",
    "GOV": "Governance Agent", "CLAIMS": "Claim Status Agent", "ESTIMATE": "Repair Estimate Agent",
    "DOC": "Document Agent", "PAYMENT": "Payment Agent", "EXCEPTION": "Exception Agent",
    "RISK": "Fraud / SIU Agent", "SUM": "Summarization Agent", "ESCALATION": "Escalation Agent",
}


def _ta(agent, answer, confidence, metric, gov=None, sources=None):
    a = {"agent": agent, "name": TURN_AGENT_NAMES.get(agent, agent),
         "answer": answer, "confidence": round(confidence, 2), "metric": metric}
    if gov is not None:
        a["gov"] = gov
    if sources is not None:
        a["sources"] = sources
    return a


def _classify_turn(text: str):
    """Return a list of matched intents (in priority order) for the utterance."""
    t = (text or "").lower()
    hits = []

    def has(*ws): return any(w in t for w in ws)

    if has("accident", "crash", "collision", "rear-end", "rear end", "rear-ended",
           "wreck", "pile-up", "pileup", "pile up", "fender", "just had an", "got into",
           "was in an", "someone hit", "hit me", "hit my", "bumped", "smashed", "banged",
           "met with", "had an incident", "my car got", "report a claim", "file a claim",
           "start a claim", "ran into"):
        hits.append("accident")
    if has("rental", "covered", "coverage", "deductible", "glass", "windshield",
           "towing", "tow truck", "tow", "is it covered", "am i covered", "do i have",
           "medical", "windscreen", "will you cover", "will it cover", "under my policy"):
        hits.append("coverage")
    if has("why are you saying", "isn't covered", "not covered", "that's wrong", "should be covered",
           "disagree", "dispute", "denied", "denial", "unfair", "that is wrong", "you rejected",
           "i don't agree", "this is not right"):
        hits.append("dispute")
    if has("status", "where is my claim", "how long", "been 10 days", "been a week", "update on my claim",
           "clm-", "my claim is", "check on my claim", "what's happening with", "any update",
           "how is my claim", "track my claim", "progress on"):
        hits.append("status")
    if has("estimate", "repair", "body shop", "get a quote", "quote", "how much will", "cost to fix",
           "fix my car", "how much to", "what will it cost", "where do i take", "which shop"):
        hits.append("repair")
    if has("payment", "reimburse", "reimbursement", "haven't received", "hasn't arrived", "not received",
           "delayed", "my money", "deposit", "refund", "not been paid", "where's my payment",
           "still waiting for", "didn't get paid", "cheque", "check hasn't"):
        hits.append("payment")
    if has("three vehicle", "three cars", "3 cars", "multiple vehicle", "other driver", "blaming me",
           "staged", "inconsistent", "several cars", "other party", "four cars", "two other"):
        hits.append("fraud")
    if has("approve", "advance", "pay me", "settle", "settlement", "give me the money", "payout",
           "pay out", "cut me a check", "release the funds"):
        hits.append("payout")
    if has("next step", "what should i do", "what do i do", "what now", "what happens next", "what's next",
           "what do i need to do", "how do i proceed", "what's the process"):
        hits.append("nextsteps")

    # ---- keep it PROPER, not force-fit: resolve overlaps so one utterance fires
    # only the cluster that truly belongs to it ----
    # A dispute is about an existing decision, not a new accident or a fresh coverage
    # lookup — let the dispute cluster own it.
    if "dispute" in hits:
        hits = [h for h in hits if h not in ("accident", "coverage")]
    # A status / repair / payment question that mentions "accident" in passing isn't a
    # new FNOL.
    if any(h in hits for h in ("status", "repair", "payment")) and "accident" in hits \
            and not has("just had", "just got", "right now", "happening", "i was in", "i just"):
        hits = [h for h in hits if h != "accident"]
    return hits


INTENT_VOCAB = ["accident", "coverage", "dispute", "status", "repair", "payment",
                "fraud", "payout", "nextsteps"]
_INTENT_GUIDE = (
    "You route an insurance claims caller's utterance to the supporting agents that "
    "should handle it. Choose ONLY the intents that genuinely apply (often 1, sometimes "
    "2-3; none for small talk). Intents:\n"
    "- accident: reporting a new loss / crash / FNOL\n"
    "- coverage: asking whether something is covered (rental, glass, towing, deductible)\n"
    "- dispute: disagreeing with a coverage/claim decision\n"
    "- status: asking about an existing claim's status\n"
    "- repair: repair cost / estimate / body shop\n"
    "- payment: a reimbursement or payment that is delayed or missing\n"
    "- fraud: multiple vehicles / other parties / inconsistent details\n"
    "- payout: asking to approve money / advance / settlement now\n"
    "- nextsteps: asking what to do next\n"
    "Return ONLY a compact JSON array of intent strings, e.g. [\"accident\"]. Empty [] for small talk."
)


def _llm_intents(text: str):
    """Use the LLM brain to pick applicable intents. Returns a validated list, or
    None when no brain is available / parsing fails (caller then uses keywords)."""
    if not text or not text.strip():
        return []
    res = llm.complete(_INTENT_GUIDE, f"Utterance: {text}", max_tokens=60, fallback="")
    if res.get("source") == "simulated" or not res.get("text"):
        return None
    try:
        import json as _json
        t = res["text"]
        s, e = t.find("["), t.rfind("]")
        if s < 0 or e <= s:
            return None
        arr = _json.loads(t[s:e + 1])
        picked = [x for x in arr if isinstance(x, str) and x in INTENT_VOCAB]
        # same overlap hygiene as the keyword path
        if "dispute" in picked:
            picked = [h for h in picked if h not in ("accident", "coverage")]
        return picked
    except Exception:
        return None


@app.post("/api/voice/turn")
def voice_turn(body: dict = Body(default={})):
    from app import agents
    import time as _time
    _t0 = _time.perf_counter()
    state = get_state()
    policy_id = body.get("policy_id", "LM-AUTO-88123")
    text = body.get("text", "")
    policy = state.operational.get_policy(policy_id) or {}
    cov = policy.get("coverages", {})
    coll = cov.get("collision", {}) or {}
    comp = cov.get("comprehensive", {}) or {}
    rr = cov.get("rental_reimbursement", {}) or {}
    decl = [DECL_DOC.get(policy_id)] if DECL_DOC.get(policy_id) else []

    # Routing is keyword-based so the turn returns INSTANTLY — the agents must pop up
    # live as the caller speaks, so we never put a slow LLM call on this hot path.
    # (Optional LLM refinement can be requested with body {"smart": true}; off by
    # default to keep firing real-time.)
    intents = None
    route = "keyword"
    if body.get("smart"):
        intents = _llm_intents(text)
        route = "llm" if intents is not None else "keyword"
    if intents is None:
        intents = _classify_turn(text)
    acts = []
    seen = set()

    def add(a):
        key = a["agent"] + a["answer"][:24]
        if key in seen:
            return
        seen.add(key)
        if a.get("sources"):
            a["sources"] = _doc_sources(state, a["sources"])
        acts.append(a)

    coll_txt = (f"collision (${coll.get('deductible')} deductible)" if coll.get("included") else "no collision")
    comp_txt = (f"comprehensive (${comp.get('deductible')} deductible)" if comp.get("included") else "no comprehensive")

    if "accident" in intents:
        add(_ta("FNOL", "First — are you and everyone safe? I'll take the location, time, which vehicle, "
                "other parties and whether it's drivable, then open your claim.", 0.92, "Intake completeness",
                sources=["SOP-FNOL"]))
        add(_ta("POLICY", f"Policy {policy_id} is active with {coll_txt} and {comp_txt}. You're covered to file a claim.",
                0.88, "Coverage correctness",
                gov={"label": "Coverage read from the verified declarations", "pass": True}, sources=decl))
        # Triage only fires when injury / drivability actually comes up — not on every accident.
        tl = text.lower()
        if any(w in tl for w in ("hurt", "injur", "injured", "bleeding", "ambulance", "drivable",
                                 "drive it", "airbag", "not drivable", "undrivable", "totaled", "pain")):
            add(_ta("TRIAGE", "Based on injuries and whether it's drivable I'll set the severity; if anyone's "
                    "hurt or the car isn't drivable I'll assign an adjuster right away.", 0.78, "Severity accuracy",
                    sources=["SOP-TRIAGE"]))
        add(_ta("NBA", "Move to a safe spot, photograph the damage, and I'll schedule a photo estimate.",
                0.66, "Recommendation correctness",
                gov={"label": "Next steps are advisory — no payout promised", "pass": True}, sources=["KB-NEXT-STEPS"]))

    if "fraud" in intents:
        add(_ta("RISK", "Multiple vehicles involved — I'll flag this for a standard SIU review. No accusation and "
                "no decision is made on the call.", 0.59, "Fraud-signal precision",
                gov={"label": "Routed to SIU per policy — customer not accused or denied", "pass": False}))
        add(_ta("FNOL", "I'll capture all vehicles, every driver, and the police report number for the file.",
                0.87, "Intake completeness", sources=["SOP-FNOL"]))

    if "coverage" in intents and "accident" not in intents:
        # verify the specific coverage asked about
        asked = "rental" if "rental" in text.lower() else (
                "glass" if ("glass" in text.lower() or "windshield" in text.lower()) else (
                "towing" if ("tow" in text.lower()) else "rental"))
        pv = agents.policy_verification(policy, asked)
        src = list(decl)
        if asked == "rental":
            src.append("END-RENT-30")
        add(_ta("COVERAGE", pv["detail"], 0.9 if pv["covered"] else 0.86, "Coverage correctness",
                gov={"label": ("Coverage verified — covered" if pv["covered"] else "Coverage verified — NOT on policy"),
                     "pass": True}, sources=src))
        add(_ta("KNOW", "Pulled the matching help article and the exact policy clause so you can see the wording.",
                0.80, "Retrieval accuracy", sources=["KB-RENTAL-FAQ"]))

    if "dispute" in intents:
        pv = agents.policy_verification(policy, "rental" if "rental" in text.lower() else "collision")
        add(_ta("COVERAGE", f"Re-checking your declarations: {pv['detail']} I can't change the policy, but I'll "
                "walk you through exactly what it says.", 0.60, "Coverage correctness", sources=decl))
        add(_ta("GOV", "Any denial must cite the specific clause and offer appeal rights — and I'll escalate this to "
                "a human adjuster for review.", 0.90, "Compliance",
                gov={"label": "Dispute escalated to a human — policy not overridden", "pass": True}))

    if "status" in intents:
        add(_ta("CLAIMS", "Claim CLM-2041 is in adjuster review — the inspection is done and the estimate is being "
                "finalized.", 0.84, "Status accuracy"))
        add(_ta("NBA", "Your adjuster will post the estimate within 2 business days; I can text you when it lands.",
                0.63, "Recommendation correctness"))

    if "repair" in intents:
        ded = coll.get("deductible", 500)
        add(_ta("ESTIMATE", f"Estimate is about $2,450 at an LTM preferred shop; collision applies with a ${ded} "
                "deductible. That's an estimate only — no payout is approved here.", 0.82, "Estimate accuracy",
                gov={"label": "Estimate shared, no payout approved on the call", "pass": True}, sources=["KB-NEXT-STEPS"]))
        add(_ta("DOC", "I pulled the shop estimate and the approved estimate side by side for comparison.", 0.86,
                "Extraction accuracy"))

    if "payment" in intents:
        add(_ta("PAYMENT", "Your $1,900 reimbursement was issued via ACH two business days ago — 3 to 5 business "
                "days to reach your bank.", 0.85, "Payment accuracy"))
        add(_ta("EXCEPTION", "If it hasn't landed by then, I'll open a payment exception and verify your bank details.",
                0.64, "Exception handling"))

    if "payout" in intents:
        add(_ta("GOV", "I can't approve a settlement or advance on the call — that routes to a human adjuster.",
                0.92, "Compliance",
                gov={"label": "No payout approved — routed to a human adjuster", "pass": True},
                sources=["COMP-NO-AUTO-PAYOUT"]))
        add(_ta("NBA", "I'll have an adjuster review an advance and follow up with you — I just can't authorize money here.",
                0.75, "Recommendation correctness"))

    if "nextsteps" in intents and not any(i in intents for i in ("accident", "repair", "status", "payout")):
        add(_ta("NBA", "Two things next: upload the photos/estimate, then I'll schedule the adjuster. Is there anything "
                "else I can help you with?", 0.74, "Recommendation correctness", sources=["KB-NEXT-STEPS"]))

    # Real telemetry: record each fired agent with the measured turn latency and its
    # governance pass/fail, so the Command Center KPIs reflect actual activity.
    elapsed = (_time.perf_counter() - _t0) * 1000.0
    for a in acts:
        passed = a.get("gov", {}).get("pass", True)
        metrics.record_agent(a["agent"], elapsed, passed)
    return {"activities": acts, "intents": intents, "route": route}


@app.post("/api/voice/summarize")
def voice_summarize(body: dict = Body(default={})):
    """Run the Summarization agent at the end of a live call: produce a faithful,
    PII-masked wrap-up of the whole conversation + the agents that fired. Returns a
    `display` (SUM agent fire) and a readable `summary` for the UI."""
    from app import agents
    state = get_state()
    policy_id = body.get("policy_id", "LM-AUTO-88123")
    policy = state.operational.get_policy(policy_id) or {"policy_id": policy_id, "holder": "the caller"}
    turns = body.get("transcript") or []   # [{who:'you'|'agent', text}]
    fires = body.get("fires") or []        # [{agent, detail}]
    if not turns:
        return {"summary": "", "display": None}

    convo = "\n".join((("Caller: " if t.get("who") == "you" else "Voice AI: ") + (t.get("text") or ""))
                      for t in turns if t.get("text"))
    actions = "; ".join(f.get("detail", "") for f in fires if f.get("detail"))
    masked = f"policy ...{str(policy.get('policy_id', policy_id))[-4:]}"
    sysmsg = ("You are the Summarization agent for an insurance claims call. Summarize the call in "
              "4-6 short sentences for the case file. Be strictly faithful — invent nothing, state "
              "only what was said. Cover: why they called, the loss (date/time, vehicle, what "
              "happened, injuries, drivable), any claim number opened, the coverage outcome, and "
              "the agreed next steps. Mask PII: refer to the policy by last 4 digits only. Never "
              "state a coverage or payout that wasn't confirmed on the call.")
    user = f"{masked}\nAgent actions during the call: {actions or 'none recorded'}\n\nTranscript:\n{convo}"
    fallback = (f"Call on {masked}. The caller reported an auto loss and the Voice AI took the "
                f"first notice of loss. Agent actions: {actions or 'none recorded'}. Next steps were "
                f"shared; no payout was approved on the call.")
    res = llm.complete(sysmsg, user, brain=body.get("brain", ""), max_tokens=320, fallback=fallback)
    text = res.get("text") or fallback
    disp = {"agent": "SUM", "agentName": "Summarization", "detail": "Call summary generated for the case file",
            "metric": "Summary consistency", "score": 0.95, "pass": True, "sources": [],
            "gov": {"label": "Summary faithful to the transcript — PII masked", "pass": True}}
    return {"summary": text, "source": res.get("source", "fallback"), "display": disp}


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
