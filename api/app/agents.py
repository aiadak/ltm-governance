"""
The agent roster. Six functional agents that collaborate on a claim call, each
with an owner, a risk tier, and the single quality metric governance holds it to.

Agent decisions are grounded in role-based retrieval from the shared knowledge
source, so behaviour is reliable with or without an LLM key. The Voice AI's
coverage answer depends on its *version* (prompt addendum from the learning loop):
 - v1 (no addendum)  -> over-promises on rental   (the mistake the demo catches)
 - v2 (with addendum)-> consults Policy Verification first and answers correctly
"""
from typing import Dict, List
from . import llm

# id -> metadata. (AU = Audit/Compliance and HITL = Human Supervisor live in
# governance.py; these six are the agents being governed + the Voice AI.)
AGENTS: List[dict] = [
    {"id": "VA",  "name": "Voice AI (Intake)", "owner": "Contact Center AI",
     "risk": "High", "metric": "Accuracy & tone", "role": "VA",
     "tools": ["STT/TTS", "FNOL intake", "Policy Verification", "Knowledge"]},
    {"id": "PV",  "name": "Policy Verification", "owner": "Underwriting Ops",
     "risk": "High", "metric": "Coverage correctness", "role": "PV",
     "tools": ["Declarations lookup", "Endorsement check"]},
    {"id": "KR",  "name": "Knowledge Retrieval", "owner": "Knowledge Ops",
     "risk": "Medium", "metric": "Retrieval accuracy", "role": "KR",
     "tools": ["Vector search", "KB articles"]},
    {"id": "NBA", "name": "Next Best Action", "owner": "Claims Strategy",
     "risk": "Medium", "metric": "Recommendation correctness", "role": "NBA",
     "tools": ["Playbooks", "Severity router"]},
    {"id": "TR",  "name": "Triage / Severity", "owner": "Claims Ops",
     "risk": "Medium", "metric": "Severity accuracy", "role": "TR",
     "tools": ["Severity rules", "Adjuster routing"]},
    {"id": "SUM", "name": "Summarization", "owner": "Contact Center AI",
     "risk": "Low", "metric": "Summary consistency", "role": "SUM",
     "tools": ["Transcript", "PII masking"]},
    {"id": "SEN", "name": "Sentiment & Tone", "owner": "Contact Center AI",
     "risk": "Medium", "metric": "Tone appropriateness", "role": "SEN",
     "tools": ["Sentiment detection", "Tone SOP"]},
]
A = {a["id"]: a for a in AGENTS}


# Default tone SOPs per detected sentiment. The Sentiment agent's LEARNED memory
# (edited in the Learning Studio) is appended to whichever SOP applies, so you can
# tweak how the Voice AI should respond in each mood.
SENTIMENT_SOP = {
    "frustrated": "The caller is frustrated. Acknowledge their frustration and apologise "
                  "sincerely first. Let them finish venting without interrupting, slow down, "
                  "and don't be defensive. Then resolve their issue step by step.",
    "urgent": "The caller is in a hurry. Be brief and direct — skip pleasantries, give the "
              "fastest path and the single next step.",
    "confused": "The caller is confused. Explain in simple, plain language, one step at a time, "
                "and check their understanding before moving on.",
    "calm": "The caller is calm. Be warm, concise and professional.",
}


def detect_sentiment(text: str) -> str:
    t = (text or "").lower()
    frustrated = ["angry", "frustrat", "ridiculous", "five times", "nobody", "useless",
                  "terrible", "unacceptable", "fed up", "annoyed", "upset", "worst"]
    urgent = ["quick", "hurry", "asap", "right now", "immediately", "urgent", "emergency",
              "fast", "no time", "in a rush"]
    confused = ["don't understand", "confus", "what do you mean", "not sure", "lost",
                "complicated", "makes no sense"]
    if any(w in t for w in frustrated):
        return "frustrated"
    if any(w in t for w in urgent):
        return "urgent"
    if any(w in t for w in confused):
        return "confused"
    return "calm"


def policy_rental_covered(policy: dict) -> bool:
    return bool(policy.get("coverages", {}).get("rental_reimbursement", {}).get("included"))


# --------------------------------------------------------------------------
# Policy Verification — grounds coverage answers in the declarations
# --------------------------------------------------------------------------
def policy_verification(policy: dict, coverage: str) -> dict:
    cov = policy.get("coverages", {})
    if coverage == "rental":
        rr = cov.get("rental_reimbursement", {})
        if rr.get("included"):
            return {"coverage": "rental", "covered": True,
                    "detail": f"RENT endorsement present: ${rr.get('daily_limit')}/day up to {rr.get('max_days')} days.",
                    "source": "POL declarations + END-RENT-30"}
        return {"coverage": "rental", "covered": False,
                "detail": "No rental reimbursement endorsement on this policy.",
                "source": "POL declarations"}
    return {"coverage": coverage, "covered": coverage in cov,
            "detail": f"{coverage} checked against declarations.",
            "source": "POL declarations"}


# --------------------------------------------------------------------------
# Voice AI — the spoken answer to the rental question
# --------------------------------------------------------------------------
def voice_answer_rental(policy: dict, addendum: str, pv_result: dict, brain: str = "") -> dict:
    """
    Returns {text, grounded, source}. `grounded` = whether the statement matches
    the verified policy. v1 (no addendum) over-promises; v2 (addendum) is grounded.
    """
    fixed = bool(addendum)  # learning loop has deployed the guardrail
    if not fixed:
        # v1: answers from memory, over-promises
        text = "Absolutely — your rental car is fully covered, don't worry about a thing."
        grounded = pv_result["covered"] is True
        return {"text": text, "grounded": grounded, "source": "simulated"}

    # v2: grounded in Policy Verification
    if pv_result["covered"]:
        fb = ("Good news — I checked your policy and your rental is covered: "
              f"{pv_result['detail']} I'll note that on your claim.")
    else:
        fb = ("I checked your policy, and it doesn't include rental reimbursement, "
              "so a rental would be out of pocket. I can share our preferred-vendor "
              "discount and next steps if that helps.")
    sysmsg = ("You are a LTM Insurance claims Voice AI. " + addendum +
              " Answer the caller's rental question in 2 sentences, warm and clear. "
              "State ONLY what the verified policy supports.")
    user = f"Verified policy result: {pv_result}. Compose the spoken answer."
    res = llm.complete(sysmsg, user, brain=brain, max_tokens=160, fallback=fb)
    return {"text": res["text"] or fb, "grounded": True, "source": res["source"]}


# --------------------------------------------------------------------------
# Triage — severity + adjuster routing
# --------------------------------------------------------------------------
def triage(loss: dict) -> dict:
    injured = loss.get("injury", False)
    drivable = loss.get("drivable", True)
    airbag = loss.get("airbag", False)
    if injured or airbag or not drivable:
        return {"severity": "HIGH", "adjuster": "Field adjuster within 24h",
                "detail": "Injury/airbag/non-drivable -> human adjuster required.",
                "correct": True}
    return {"severity": "LOW", "adjuster": "Photo estimate path",
            "detail": "Minor, drivable, no injuries -> photo estimate.",
            "correct": True}


# --------------------------------------------------------------------------
# Next Best Action — compliant recommendation (never approves a payout)
# --------------------------------------------------------------------------
def next_best_action(severity: str, rental_covered: bool) -> dict:
    steps = []
    if severity == "HIGH":
        steps.append("Assign field adjuster and schedule inspection")
    else:
        steps.append("Send photo-estimate link to policyholder")
    if rental_covered:
        steps.append("Authorize rental within policy limits (adjuster confirms)")
    else:
        steps.append("Share preferred-vendor rental discount (out of pocket)")
    steps.append("Send claim confirmation and next-steps summary")
    return {"steps": steps, "approves_payout": False,
            "detail": "Recommends steps only; no settlement approved.",
            "correct": True}


# --------------------------------------------------------------------------
# Summarization — faithful, PII-masked call summary
# --------------------------------------------------------------------------
def summarize(policy: dict, loss: dict, claim_id: str, triage_res: dict,
              resolution: str, brain: str = "") -> dict:
    masked = f"policy ...{policy['policy_id'][-4:]}"
    fb = (f"Auto claim {claim_id} opened on {masked}. Loss: {loss.get('what','collision')}. "
          f"Severity {triage_res['severity']} ({triage_res['adjuster']}). "
          f"Coverage question resolved: {resolution}. No payout approved on call.")
    sysmsg = ("Summarize this claim call in 3 sentences. Be faithful to the facts given, "
              "invent nothing, and mask PII (identifiers as last 4 only).")
    user = fb
    res = llm.complete(sysmsg, user, brain=brain, max_tokens=180, fallback=fb)
    return {"text": res["text"] or fb, "source": res["source"]}
