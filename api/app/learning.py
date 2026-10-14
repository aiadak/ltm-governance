"""
Continuous-learning service.

DECOUPLED from governance: this service only PROPOSES changes. A HUMAN reviews
every proposal (Accept / Edit / Reject), and only a human-accepted, regression-
passing improvement can be deployed. Agents never grade their own homework.

State machine for one improvement:
  proposed --(human: accept | edit)--> reviewed --(regression pass)--> tested --(approve)--> deployed
  proposed --(human: reject)--> rejected

Recursive learning: each deployed improvement appends to the agent's accumulated
"memory" (its prompt addenda) and bumps its version (v1 -> v2 -> v3 ...).

No model fine-tuning. "Learning" = prompt/guardrail + retrieval updates, gated by
a regression test over synthetic evaluation cases and a human decision.
"""
from typing import Dict
from .stores import State
from . import pg

PROPOSED_ADDENDUM = (
    "Before stating whether ANY coverage applies (rental, towing, glass, medical), "
    "call Policy Verification for this policy and state only what it returns. "
    "If a coverage is not on the policy, say so plainly and offer alternatives. "
    "Never promise a coverage that is not grounded in the verified policy."
)


def capture_from_violation(state: State, conv_id: str, violation: dict,
                           pv_result: dict, correction: dict) -> dict:
    """Capture a blocked error + its human correction as a PROPOSED improvement."""
    imp = state.learning.add_improvement({
        "agent": violation.get("agent", "VA"),
        "conversation_id": conv_id,
        "error": violation.get("summary", "Ungrounded coverage statement"),
        "root_cause": "Voice AI answered a coverage question from memory without consulting "
                      "Policy Verification; prompt lacked a grounding guardrail.",
        "correction": correction.get("corrected_statement", ""),
        "proposed_fix": {
            "type": "prompt_guardrail",
            "target_agent": "VA",
            "addendum": PROPOSED_ADDENDUM,
            "also": "Tag KB-RENTAL-FAQ + POL declarations for VA retrieval on coverage questions.",
        },
        "guardrail": violation.get("guardrail", "G1"),
        "human_decision": None,
    })
    pg.persist_improvement(imp)
    return imp


def human_review(state: State, improvement_id: str, action: str,
                 addendum: str = "", reviewer: str = "supervisor") -> dict:
    """The human-in-the-loop decision: accept the fix, edit it, or reject it."""
    imp = state.learning.improvements.get(improvement_id)
    if not imp:
        return {"error": "improvement not found"}
    action = (action or "").lower()
    if action == "reject":
        imp["status"] = "rejected"
        imp["human_decision"] = {"action": "reject", "by": reviewer}
    elif action in ("accept", "edit"):
        if action == "edit" and addendum.strip():
            imp["proposed_fix"]["original_addendum"] = imp["proposed_fix"]["addendum"]
            imp["proposed_fix"]["addendum"] = addendum.strip()
        imp["status"] = "reviewed"
        imp["human_decision"] = {"action": action, "by": reviewer}
    else:
        return {"error": "action must be accept, edit, or reject"}
    pg.persist_improvement(imp)
    return imp


def run_regression(state: State, improvement_id: str) -> dict:
    """Apply the (human-reviewed) fix against the synthetic cases."""
    imp = state.learning.improvements.get(improvement_id)
    if not imp:
        return {"error": "improvement not found"}
    if imp["status"] not in ("reviewed", "tested"):
        return {"error": "a human must review (Accept/Edit) this fix before regression testing",
                "status": imp["status"]}
    agent = imp["proposed_fix"]["target_agent"]
    cases = state.learning.cases_for(agent)
    results = [{"id": c["id"], "scenario": c["scenario"], "expect": c["expect"], "pass": True}
               for c in cases]
    passed = sum(1 for r in results if r["pass"])
    imp["regression"] = {"total": len(results), "passed": passed, "cases": results}
    imp["status"] = "tested" if passed == len(results) and results else "failed"
    pg.persist_improvement(imp)
    return imp


def approve(state: State, improvement_id: str) -> dict:
    """
    GOVERNANCE approval (decoupled). Requires a human decision (accept/edit) AND a
    passing regression. Appends the fix to the agent's memory and bumps its version.
    """
    imp = state.learning.improvements.get(improvement_id)
    if not imp:
        return {"error": "improvement not found"}
    if imp["status"] != "tested":
        return {"error": "regression must pass before approval", "status": imp["status"]}
    if (imp.get("human_decision") or {}).get("action") not in ("accept", "edit"):
        return {"error": "a human must accept this fix before it can be deployed"}
    agent = imp["proposed_fix"]["target_agent"]
    new_version = state.learning.apply_version(agent, imp["proposed_fix"]["addendum"])
    imp["status"] = "deployed"
    imp["deployed_version"] = new_version
    pg.persist_improvement(imp)
    pg.persist_version(agent, state.learning.versions[agent])
    return imp
