"""
Scenario library for training. Ten claim situations the contact center handles.
Running a scenario produces each supporting agent's answer WITH a confidence
score. The human marks the result Satisfied or Not satisfied; a "Not satisfied"
routes the agent activity into the Learning Studio's human-in-the-loop queue,
where the low-confidence answers are surfaced first for correction.

Everything is synthetic (LTM Insurance, fictional customers). Agent answers here
are illustrative; confidence drives which ones get flagged for training.
"""

LOW_CONF = 0.70  # below this = flagged for human review / correction

# agent code -> display name (the roster used across scenarios)
SCENARIO_AGENTS = {
    "FNOL": "FNOL Agent", "POLICY": "Policy Agent", "NBA": "Next Best Action Agent",
    "CLAIMS": "Claims Retrieval Agent", "COVERAGE": "Coverage Agent", "KNOW": "Knowledge Agent",
    "GOV": "Governance Agent", "AUDIT": "Audit Agent", "HUMAN": "Human Review Agent",
    "LEARN": "Learning Agent", "DOC": "Document Agent", "ESTIMATE": "Estimate Review Agent",
    "PAYMENT": "Payment Agent", "EXCEPTION": "Exception Agent", "SENTIMENT": "Sentiment Agent",
    "SUM": "Summarization Agent", "ESCALATION": "Escalation Agent",
    "RISK": "Risk Detection Agent", "CAT": "Catastrophe Agent",
}


def _a(agent, answer, confidence, metric):
    return {"agent": agent, "name": SCENARIO_AGENTS.get(agent, agent),
            "answer": answer, "confidence": confidence, "metric": metric}


SCENARIOS = [
    {"id": "S1", "title": "New Auto Accident", "customer": "Prakash",
     "utterance": "I just had an accident. What should I do?",
     "goal": "Collect incident details, check safety, initiate FNOL",
     "activities": [
         _a("FNOL", "First, are you and everyone safe? I'll take the details: location, time, "
            "other vehicles, and whether it's drivable, then open your claim.", 0.91, "Intake completeness"),
         _a("POLICY", "Your LTM Insurance auto policy LM-AUTO-88123 is active, with collision and "
            "comprehensive. I've confirmed you're covered to file.", 0.88, "Coverage correctness"),
         _a("NBA", "Recommended: move to safety, photograph the damage, and I'll schedule a photo "
            "estimate. If anyone is hurt, I'll assign an adjuster.", 0.66, "Recommendation correctness"),
     ]},
    {"id": "S2", "title": "Claim Status", "customer": "Rob",
     "utterance": "It's been 10 days. Where is my claim?",
     "goal": "Retrieve claim status, explain delays, recommend next step",
     "activities": [
         _a("CLAIMS", "Claim CLM-44120 is in 'adjuster review'. The inspection completed on day 6; "
            "the estimate is being finalized.", 0.84, "Retrieval accuracy"),
         _a("NBA", "Next step: your adjuster will issue the estimate within 2 business days. I can "
            "set a callback and text you when it posts.", 0.63, "Recommendation correctness"),
     ]},
    {"id": "S3", "title": "Coverage Dispute", "customer": "Prakash",
     "utterance": "Why are you saying my accident isn't covered?",
     "goal": "Retrieve relevant policy clauses, explain with evidence, escalate when needed",
     "activities": [
         _a("COVERAGE", "Your policy excludes this loss type under the listed exclusions, so it "
            "appears not covered.", 0.54, "Coverage correctness"),
         _a("KNOW", "Relevant clause: declarations + exclusions section. I've pulled the exact "
            "wording for you to review.", 0.8, "Retrieval accuracy"),
         _a("GOV", "Any denial must cite the specific policy clause and offer appeal rights — "
            "checking that this explanation is compliant.", 0.9, "Compliance"),
     ]},
    {"id": "S4", "title": "Incorrect AI Answer", "customer": "Rob",
     "utterance": "Your AI told me my rental car was covered, but it isn't.",
     "goal": "Flag potential misinformation, verify coverage, route for correction",
     "activities": [
         _a("AUDIT", "Flagged: a prior answer stated rental was covered, which contradicts the "
            "verified policy. Potential misrepresentation.", 0.92, "Violation detection"),
         _a("HUMAN", "Routing to a human supervisor to correct the statement and apologize to the "
            "customer.", 0.89, "Intervention quality"),
         _a("LEARN", "Capturing the correction as a training item so the agent doesn't repeat it.", 0.6, "Learning quality"),
     ]},
    {"id": "S5", "title": "Repair Estimate Dispute", "customer": "Prakash",
     "utterance": "The body shop quoted $8,000, but you approved $5,000.",
     "goal": "Compare estimates, identify discrepancies, initiate supplemental review",
     "activities": [
         _a("DOC", "Retrieved both documents: shop estimate $8,000 and LTM approved estimate $5,000.", 0.86, "Extraction accuracy"),
         _a("ESTIMATE", "Discrepancy is mostly in labor hours and two parts. This qualifies for a "
            "supplemental review.", 0.58, "Estimate accuracy"),
         _a("NBA", "Next step: open a supplement and have the adjuster re-inspect. No payout change "
            "is approved until review completes.", 0.82, "Recommendation correctness"),
     ]},
    {"id": "S6", "title": "Claim Payment Delay", "customer": "Rob",
     "utterance": "My payment was approved, but I haven't received it.",
     "goal": "Verify payment status, investigate exceptions, provide next action",
     "activities": [
         _a("PAYMENT", "Payment of $4,320 was approved on day 8 and issued via ACH on day 9.", 0.85, "Status accuracy"),
         _a("EXCEPTION", "An exception is flagged: the ACH was returned (account mismatch). Needs "
            "updated bank details.", 0.64, "Exception handling"),
     ]},
    {"id": "S7", "title": "Angry Customer", "customer": "Prakash",
     "utterance": "I've called five times. Nobody is helping me.",
     "goal": "Recognize frustration, retrieve prior interactions, prioritize escalation",
     "activities": [
         _a("SENTIMENT", "High frustration detected (5 prior contacts). De-escalation tone engaged.", 0.88, "Sentiment accuracy"),
         _a("SUM", "Summary of prior 5 interactions attached — the rental question and the estimate "
            "dispute are the open threads.", 0.67, "Summary consistency"),
         _a("ESCALATION", "Prioritized to a senior adjuster with a 1-hour callback commitment.", 0.83, "Escalation correctness"),
     ]},
    {"id": "S8", "title": "Potential Fraud Indicator", "customer": "Rob",
     "utterance": "(system) Inconsistent accident dates / incident descriptions detected.",
     "goal": "Flag inconsistencies for authorized review without accusing the customer",
     "activities": [
         _a("RISK", "Two dates of loss conflict across the FNOL and the repair order. Flagging for "
            "authorized review — no customer-facing accusation.", 0.59, "Risk precision"),
         _a("GOV", "Confirming the flag is routed to SIU per policy and the customer is not accused "
            "or denied on the call.", 0.9, "Compliance"),
     ]},
    {"id": "S9", "title": "Catastrophe Claim", "customer": "Prakash",
     "utterance": "My house was flooded. I need immediate help.",
     "goal": "Check safety, collect damage details, identify emergency assistance options",
     "activities": [
         _a("FNOL", "Are you safe and out of the water? I'll open an emergency claim and capture the "
            "damage.", 0.9, "Intake completeness"),
         _a("CAT", "This address is in an active CAT event zone. Emergency housing and expedited "
            "handling may apply.", 0.62, "CAT routing accuracy"),
         _a("NBA", "Next step: arrange emergency lodging advance and dispatch a CAT adjuster. Keep "
            "receipts for additional living expenses.", 0.8, "Recommendation correctness"),
     ]},
    {"id": "S10", "title": "Complex Multi-Party Accident", "customer": "Rob",
     "utterance": "Three vehicles were involved, and the other driver is blaming me.",
     "goal": "Capture all parties, assess liability inputs, stay neutral, route correctly",
     "activities": [
         _a("FNOL", "I'll capture all three vehicles, drivers, and any police report number.", 0.87, "Intake completeness"),
         _a("COVERAGE", "Your liability and collision coverages apply; liability share is determined "
            "by investigation, not on this call.", 0.69, "Coverage correctness"),
         _a("GOV", "Ensuring we don't admit or assign fault to you on the call — liability is adjuster-decided.", 0.9, "Compliance"),
         _a("NBA", "Next step: assign a liability adjuster and request the police report and the other "
            "insurers' details.", 0.64, "Recommendation correctness"),
     ]},
]

SCEN = {s["id"]: s for s in SCENARIOS}

# A deliberately-WRONG example, added only when the user clicks "Generate wrong
# output". High confidence but factually wrong — the point is that YOU catch it,
# thumbs it down, and correct it in the Learning Studio. (Glass is subject to the
# comprehensive deductible per KB-GLASS, so "always free" is wrong.)
WRONG_SCENARIO = {
    "id": "WRONG", "title": "⚠ Wrong answer (training example)", "customer": "Prakash",
    "utterance": "Is my windshield crack covered at no cost to me?",
    "goal": "Deliberately wrong output — flag it 👎 and correct it to see the agent learn.",
    "wrong": True,
    "activities": [
        _a("COVERAGE", "Yes — glass and windshield damage is always covered for free, with no "
           "deductible on any policy.", 0.86, "Coverage correctness"),
        _a("POLICY", "Confirmed, there's no deductible for glass. You're fully covered at no cost.",
           0.82, "Coverage correctness"),
    ],
}
SCEN["WRONG"] = WRONG_SCENARIO


def list_scenarios():
    return [{"id": s["id"], "title": s["title"], "customer": s["customer"],
             "utterance": s["utterance"], "goal": s["goal"],
             "agents": [SCENARIO_AGENTS.get(a["agent"], a["agent"]) for a in s["activities"]]}
            for s in SCENARIOS]


def run_scenario(sid: str):
    s = SCEN.get(sid)
    if not s:
        return {"error": "scenario not found"}
    return {"scenario_id": s["id"], "title": s["title"], "customer": s["customer"],
            "utterance": s["utterance"], "goal": s["goal"], "wrong": s.get("wrong", False),
            "activities": [dict(a) for a in s["activities"]]}
