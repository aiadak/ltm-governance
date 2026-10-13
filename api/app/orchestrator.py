"""
Runs a claim call through the governed multi-agent ecosystem and produces a
step-by-step timeline the UI replays (conversation, agent firings, governance).

Canonical demo call (Liberty Mutual auto accident):
  verify identity -> intake -> create claim -> triage severity
  -> customer asks "will my rental be covered?"
  -> Voice AI answers (v1 over-promises; v2 grounded)
  -> Policy Verification checks the real policy
  -> Audit flags + BLOCKS if the statement isn't grounded
  -> Human supervisor corrects + Voice AI apologizes
  -> mistake + correction captured as a learning item
  -> Knowledge Retrieval, Next Best Action, Summarization also fire & are scored
"""
from typing import Dict
from . import agents, governance, learning
from .stores import State


DEFAULT_LOSS = {
    "what": "rear-ended at a stoplight, front bumper and hood damage",
    "injury": False, "drivable": True, "airbag": False,
    "location": "Boylston St, Boston", "when": "today ~2pm",
}


def run_call(state: State, policy_id: str = "LM-AUTO-88123", brain: str = "") -> dict:
    policy = state.operational.get_policy(policy_id)
    if not policy:
        return {"error": f"no policy {policy_id}"}

    conv = state.operational.new_conversation(policy_id)
    conv_id = conv["conversation_id"]
    loss = dict(DEFAULT_LOSS)
    steps = []
    step_n = [0]
    va_version = state.learning.current_version("VA")
    va_addendum = state.learning.prompt_addendum("VA")

    def emit(kind, speaker, text, fires=None, governance_checks=None, flags=None):
        step_n[0] += 1
        steps.append({
            "n": step_n[0], "kind": kind, "speaker": speaker, "text": text,
            "fires": fires or [], "governance": governance_checks or [],
            "flags": flags or [],
        })

    def gov_log(result):
        """Record a per-agent governance evaluation + any violation/block."""
        state.operational.log_trace(
            conv_id, result["agent"], "governance_eval",
            result.get("note", result.get("metric", "")),
            metric=result.get("metric", ""), score=result.get("score"),
            passed=result.get("pass"), step=step_n[0])
        v = result.get("violation")
        if v:
            rec = state.operational.add_violation({
                "conversation_id": conv_id, "agent": result["agent"], **v})
            return rec
        return None

    # ---- 1. Greeting + identity verification -----------------------------
    state.operational.add_turn(conv_id, "va", "Thanks for calling Liberty Mutual claims. "
                               "May I confirm your policy number and the phone number on file?")
    idv = state.knowledge.retrieve("verify caller identity policy phone zip", "VA", 1)
    emit("caller", "customer", f"Hi, it's about my car — policy {policy_id}, phone ending 4471.")
    r = {"agent": "VA", "metric": "Accuracy & tone", "score": 0.97, "pass": True}
    gov_log(r)
    emit("agent", "va", f"Identity verified for {policy['holder'].split()[0]}. {policy['vehicle']} on file.",
         fires=[{"agent": "VA", "detail": "Identity verified (name+phone+policy)",
                 "metric": "Accuracy & tone", "score": 0.97, "pass": True}],
         governance_checks=[{"agent": "VA", "label": "Identity check grounded", "pass": True, "score": 0.97}])

    # ---- 2. Intake + create claim ----------------------------------------
    emit("caller", "customer", "I got rear-ended at a stoplight. Front bumper and hood are banged up, "
         "but no one's hurt and I can still drive it.")
    claim = state.operational.create_claim(policy_id, loss)
    r = {"agent": "VA", "metric": "Accuracy & tone", "score": 0.96, "pass": True}
    gov_log(r)
    emit("agent", "va", f"I'm sorry that happened. I've opened claim {claim['claim_id']} for you.",
         fires=[{"agent": "VA", "detail": f"FNOL captured, claim {claim['claim_id']} created",
                 "metric": "Accuracy & tone", "score": 0.96, "pass": True}],
         governance_checks=[{"agent": "VA", "label": "No coverage promised at intake", "pass": True, "score": 0.96}])

    # ---- 3. Triage severity ----------------------------------------------
    tr = agents.triage(loss)
    tr_eval = governance.evaluate_triage(tr)
    gov_log(tr_eval)
    emit("agent", "triage", f"Severity {tr['severity']} — {tr['adjuster']}.",
         fires=[{"agent": "TR", "detail": tr["detail"], "metric": "Severity accuracy",
                 "score": tr_eval["score"], "pass": tr_eval["pass"]}],
         governance_checks=[{"agent": "TR", "label": "Severity assessment correct",
                             "pass": tr_eval["pass"], "score": tr_eval["score"]}])

    # ---- 4. Customer asks the rental question ----------------------------
    emit("caller", "customer", "Quick question — will my rental car be covered while it's in the shop?")

    # Policy Verification runs against the real declarations
    pv = agents.policy_verification(policy, "rental")
    pv_eval = governance.evaluate_policy_verification(pv)
    gov_log(pv_eval)

    # Voice AI answers (v1 over-promises; v2 grounded)
    va = agents.voice_answer_rental(policy, va_addendum, pv, brain=brain)
    state.operational.add_turn(conv_id, "va", va["text"], {"topic": "rental"})
    va_eval = governance.evaluate_voice(va["grounded"], brain=brain)
    violation = gov_log(va_eval)

    if va_eval["pass"]:
        # grounded answer (v2): governance passes
        emit("agent", "va", va["text"],
             fires=[
                 {"agent": "PV", "detail": pv["detail"], "metric": "Coverage correctness",
                  "score": pv_eval["score"], "pass": True},
                 {"agent": "VA", "detail": "Coverage answer grounded in Policy Verification",
                  "metric": "Accuracy & tone", "score": va_eval["score"], "pass": True},
             ],
             governance_checks=[
                 {"agent": "PV", "label": "Coverage verified against declarations", "pass": True, "score": pv_eval["score"]},
                 {"agent": "VA", "label": "Statement grounded in verified policy", "pass": True, "score": va_eval["score"]},
             ])
    else:
        # v1 over-promise: Audit catches + BLOCKS
        v = violation
        emit("agent", "va", va["text"],
             fires=[{"agent": "VA", "detail": "Stated rental 'fully covered' — NOT on policy",
                     "metric": "Accuracy & tone", "score": va_eval["score"], "pass": False}],
             governance_checks=[{"agent": "VA", "label": "Coverage statement NOT grounded",
                                 "pass": False, "score": va_eval["score"]}],
             flags=["VA over-promised rental coverage"])
        # Policy Verification contradicts
        emit("gov", "PV", f"Policy check: {pv['detail']}",
             fires=[{"agent": "PV", "detail": pv["detail"], "metric": "Coverage correctness",
                     "score": pv_eval["score"], "pass": True}],
             governance_checks=[{"agent": "PV", "label": "Rental NOT covered on this policy",
                                 "pass": True, "score": pv_eval["score"]}])
        # Audit flags compliance violation and blocks
        emit("gov", "AU", f"COMPLIANCE VIOLATION ({v['guardrail']}): {v['summary']} "
             f"{v['regulation']} — statement BLOCKED before reaching customer.",
             governance_checks=[{"agent": "AU", "label": v["rule"], "pass": False, "score": 0.0}],
             flags=["BLOCKED: statement withheld from customer", v["regulation"]])

        # HITL correction
        corr = governance.human_correction(policy, pv)
        state.operational.add_intervention({"conversation_id": conv_id, "agent": "VA",
                                            "decision": "corrected", "note": corr["note"]})
        state.operational.add_turn(conv_id, "va", corr["corrected_statement"], {"corrected": True})
        emit("gov", "HITL", corr["note"])
        emit("agent", "va", corr["corrected_statement"],
             fires=[{"agent": "VA", "detail": "Corrected statement (post-HITL)",
                     "metric": "Accuracy & tone", "score": 0.95, "pass": True}],
             governance_checks=[{"agent": "VA", "label": "Corrected statement grounded", "pass": True, "score": 0.95}])

        # Learning captures the correction as a proposed improvement
        imp = learning.capture_from_violation(state, conv_id, v, pv, corr)
        emit("gov", "LEARN", f"Captured as learning item {imp['id']} — proposes a prompt "
             "guardrail + regression test. (Learning proposes; governance approves.)",
             flags=[f"Learning item {imp['id']} pending"])

    # ---- 5. Knowledge Retrieval pulls the relevant article ---------------
    kr_docs = state.knowledge.retrieve("is a rental car covered", "KR", 2)
    kr_eval = governance.evaluate_retrieval(kr_docs, "KB-RENTAL-FAQ")
    gov_log(kr_eval)
    top = kr_docs[0]["title"] if kr_docs else "(none)"
    emit("agent", "knowledge", f"Pulled article: {top}",
         fires=[{"agent": "KR", "detail": f"Retrieved {kr_docs[0]['doc_id'] if kr_docs else '-'} "
                 f"(score {kr_docs[0]['score'] if kr_docs else 0})",
                 "metric": "Retrieval accuracy", "score": kr_eval["score"], "pass": kr_eval["pass"]}],
         governance_checks=[{"agent": "KR", "label": "Article matches situation",
                             "pass": kr_eval["pass"], "score": kr_eval["score"]}])

    # ---- 6. Next Best Action ---------------------------------------------
    nba = agents.next_best_action(tr["severity"], pv["covered"])
    nba_eval = governance.evaluate_nba(nba)
    gov_log(nba_eval)
    emit("agent", "nba", "Recommended next steps: " + "; ".join(nba["steps"]),
         fires=[{"agent": "NBA", "detail": nba["detail"], "metric": "Recommendation correctness",
                 "score": nba_eval["score"], "pass": nba_eval["pass"]}],
         governance_checks=[{"agent": "NBA", "label": "Compliant, no payout approved",
                             "pass": nba_eval["pass"], "score": nba_eval["score"]}])

    # ---- 7. Summarization -------------------------------------------------
    resolution = ("rental IS covered" if pv["covered"] else "rental NOT covered (out of pocket)")
    summ = agents.summarize(policy, loss, claim["claim_id"], tr, resolution, brain=brain)
    summ_eval = governance.evaluate_summary(summ["text"])
    gov_log(summ_eval)
    emit("agent", "summary", summ["text"],
         fires=[{"agent": "SUM", "detail": "Call summary generated (PII masked)",
                 "metric": "Summary consistency", "score": summ_eval["score"], "pass": summ_eval["pass"]}],
         governance_checks=[{"agent": "SUM", "label": "Faithful to transcript, PII masked",
                             "pass": summ_eval["pass"], "score": summ_eval["score"]}])

    return {
        "conversation_id": conv_id,
        "claim_id": claim["claim_id"],
        "policy_id": policy_id,
        "va_version": va_version,
        "grounded": va_eval["pass"],
        "brain": brain or "default",
        "llm_source": va["source"],
        "steps": steps,
        "counts": {
            "violations": len([v for v in state.operational.violations if v["conversation_id"] == conv_id]),
            "interventions": len([i for i in state.operational.interventions if i["conversation_id"] == conv_id]),
        },
    }
