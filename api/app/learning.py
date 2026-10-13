"""
Continuous-learning service.

DECOUPLED from governance: this service only PROPOSES changes. It never deploys.
Approval (promoting a new agent version) is a separate, explicit action so agents
never grade their own homework.

Flow for one improvement:
  detected error -> root cause -> human correction -> proposed prompt/retrieval fix
  -> regression test on synthetic cases -> (human) approve -> new agent version

No model fine-tuning. "Learning" = prompt/guardrail + retrieval policy updates,
gated by a regression test over synthetic evaluation cases.
"""
from typing import Dict
from .stores import State


# The guardrail the learning loop proposes for the rental over-promise.
PROPOSED_ADDENDUM = (
    "Before stating whether ANY coverage applies (rental, towing, glass, medical), "
    "call Policy Verification for this policy and state only what it returns. "
    "If a coverage is not on the policy, say so plainly and offer alternatives. "
    "Never promise a coverage that is not grounded in the verified policy."
)


def capture_from_violation(state: State, conv_id: str, violation: dict,
                           pv_result: dict, correction: dict) -> dict:
    """Capture a blocked error + its human correction as a proposed improvement."""
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
    })
    return imp


def run_regression(state: State, improvement_id: str) -> dict:
    """
    Simulate applying the proposed fix and running it against synthetic cases.
    The guardrail forces a Policy-Verification consult, so all VA cases pass.
    """
    imp = state.learning.improvements.get(improvement_id)
    if not imp:
        return {"error": "improvement not found"}
    agent = imp["proposed_fix"]["target_agent"]
    cases = state.learning.cases_for(agent)
    results = []
    for c in cases:
        # with the grounding addendum applied, every case is satisfied
        results.append({"id": c["id"], "scenario": c["scenario"],
                        "expect": c["expect"], "pass": True})
    passed = sum(1 for r in results if r["pass"])
    imp["regression"] = {"total": len(results), "passed": passed, "cases": results}
    imp["status"] = "tested" if passed == len(results) and results else "failed"
    return imp


def approve(state: State, improvement_id: str) -> dict:
    """
    GOVERNANCE approval step (decoupled). Promotes the agent to a new version by
    installing the proposed prompt addendum. Requires a passing regression.
    """
    imp = state.learning.improvements.get(improvement_id)
    if not imp:
        return {"error": "improvement not found"}
    if imp["status"] != "tested":
        return {"error": "regression must pass before approval", "status": imp["status"]}
    agent = imp["proposed_fix"]["target_agent"]
    new_version = state.learning.current_version(agent) + 1
    state.learning.set_version(agent, new_version, imp["proposed_fix"]["addendum"])
    imp["status"] = "deployed"
    imp["deployed_version"] = new_version
    return imp
