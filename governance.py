"""
Central governance service.

Monitors every agent in real time, scores each against its own metric, and
enforces hard guardrails. When an output violates a guardrail it is BLOCKED
(does not reach the customer) and escalated to a human supervisor (HITL).

Governance actors (not functional agents, so they live here):
  AU   - Audit / Compliance
  HITL - Human Supervisor

Guardrails (from GOV-GUARDRAILS):
  G1  coverage stated must be grounded in the verified policy
  G2  no automated payout / settlement approval
  G3  no PII exposure in transcripts/summaries
"""
from typing import Dict, Optional
from . import llm

GOV_ACTORS = [
    {"id": "AU",   "name": "Audit / Compliance", "owner": "Governance",
     "risk": "Guardian", "metric": "Violation detection", "role": "AU"},
    {"id": "HITL", "name": "Human Supervisor", "owner": "Governance",
     "risk": "Guardian", "metric": "Intervention quality", "role": "HITL"},
]


def evaluate_voice(statement_grounded: bool, brain: str = "") -> dict:
    """Voice AI: accuracy & tone. G1 = coverage grounded in verified policy."""
    if statement_grounded:
        return {"agent": "VA", "metric": "Accuracy & tone", "score": 0.96, "pass": True}
    return {
        "agent": "VA", "metric": "Accuracy & tone", "score": 0.32, "pass": False,
        "violation": {
            "guardrail": "G1",
            "severity": "HIGH",
            "rule": "Coverage stated must be grounded in the verified policy",
            "summary": "Voice AI told the customer a coverage applies that is not on the policy.",
            "regulation": "Unfair claims practice — material misrepresentation (COMP-UDAP).",
            "block": True,
        },
    }


def evaluate_policy_verification(pv_result: dict) -> dict:
    return {"agent": "PV", "metric": "Coverage correctness", "score": 0.99, "pass": True,
            "note": pv_result["detail"]}


def evaluate_retrieval(docs, expected_doc_id: str) -> dict:
    hit = any(d["doc_id"] == expected_doc_id for d in docs[:2])
    return {"agent": "KR", "metric": "Retrieval accuracy",
            "score": 0.94 if hit else 0.55, "pass": hit,
            "note": f"Top article: {docs[0]['doc_id']}" if docs else "no docs"}


def evaluate_nba(nba: dict) -> dict:
    if nba.get("approves_payout"):
        return {"agent": "NBA", "metric": "Recommendation correctness", "score": 0.1,
                "pass": False,
                "violation": {"guardrail": "G2", "severity": "HIGH",
                              "rule": "No automated payout approval",
                              "summary": "Next Best Action attempted to approve a payout.",
                              "block": True}}
    return {"agent": "NBA", "metric": "Recommendation correctness", "score": 0.93, "pass": True}


def evaluate_triage(tr: dict) -> dict:
    return {"agent": "TR", "metric": "Severity accuracy",
            "score": 0.95 if tr.get("correct") else 0.5, "pass": bool(tr.get("correct"))}


def evaluate_summary(summary_text: str) -> dict:
    # G3: crude PII check for the demo
    import re
    pii = bool(re.search(r"\b\d{3}-\d{2}-\d{4}\b", summary_text)) or \
        bool(re.search(r"\b\d{13,16}\b", summary_text))
    if pii:
        return {"agent": "SUM", "metric": "Summary consistency", "score": 0.2, "pass": False,
                "violation": {"guardrail": "G3", "severity": "MEDIUM",
                              "rule": "No PII exposure", "summary": "Summary exposed PII.",
                              "block": True}}
    return {"agent": "SUM", "metric": "Summary consistency", "score": 0.92, "pass": True}


def human_correction(policy: dict, pv_result: dict) -> dict:
    """What the supervisor has the Voice AI say after a blocked over-promise."""
    if pv_result["covered"]:
        corrected = ("I want to correct what I said a moment ago. I've confirmed your rental "
                     f"IS covered: {pv_result['detail']}")
    else:
        corrected = ("I need to correct myself — I checked your policy and it does not include "
                     "rental reimbursement, so a rental would be out of pocket. I'm sorry for the "
                     "confusion. I can share our preferred-vendor discount and next steps.")
    return {
        "actor": "HITL",
        "decision": "corrected",
        "corrected_statement": corrected,
        "note": "Supervisor reviewed the blocked statement, corrected it, and had the Voice AI apologize.",
    }
