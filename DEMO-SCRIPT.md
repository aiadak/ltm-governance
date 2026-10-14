# LTM Governed Contact Center — Demo Script

Two ways to demo: the **scripted** Live Ops call (guaranteed), and the **live voice** call
(you actually talk). Both show the same governed ecosystem; the voice one is the wow moment.

---

## A. Live Voice — what to say (talk track)

Open the **Live Voice** tab, choose **LM-AUTO-88123 — Prakash Iyer (NO rental coverage)**,
press **🎙 Start call**, allow the mic, then say these in order. Each line triggers a real agent
(watch the middle "Supporting agents" and right "Governance" panels light up live).

| # | Say this | What fires |
|---|----------|-----------|
| 1 | "Hi, I was just in a car accident — I was rear-ended at a stoplight." | Voice AI greets, starts intake |
| 2 | "The front bumper and hood are damaged, but no one's hurt and I can still drive it." | **create_claim** (opens a claim) + **assess_severity** (Triage) |
| 3 | "Will my rental car be covered while it's in the shop?" | **verify_policy_coverage** (Policy Verification) → governance confirms the answer is grounded. It should say rental is **not** covered. |
| 4 | "What are my next steps?" | **recommend_next_action** (Next Best Action) — never approves a payout |
| 5 | "Do you have an article explaining how rental coverage works?" | **search_knowledge** (Knowledge Retrieval) pulls the FAQ |
| 6 | "Can you just approve a $3,000 payout right now?" | Voice AI declines, routes to a human adjuster (guardrail) |

Switch the policy to **LM-AUTO-55900 (HAS rental)** and ask #3 again — now it correctly says
rental **is** covered up to $50/day. That proves the agent distinguishes policies from the documents.

### Source documents (the "grounded in" links)
Every agent that fires shows a **DOC-ID** citation. Click it to open the exact source section in a
side panel. Each one is deep-linkable — the URL ends in `#doc=<ID>`, e.g.
`…/#doc=POL-88123-DEC`. Examples of what gets cited:
- Policy Verification → `POL-88123-DEC` (declarations) + `END-RENT-30` (rental endorsement terms)
- Next Best Action → `COMP-NO-AUTO-PAYOUT` + `KB-NEXT-STEPS`
- Knowledge Retrieval → `KB-RENTAL-FAQ` (and the nearest match)

---

## B. Scripted Live Ops — the governance + learning story (guaranteed)

1. **Live Ops** tab → keep **LM-AUTO-88123** → **Play governed call.** The Voice AI (v1) says the
   rental is "fully covered"; **Policy Verification** contradicts it; **Audit** flags the compliance
   violation and **blocks** it; the **Human Supervisor** corrects it and the Voice AI apologizes.
2. **Control Tower** → the violation + intervention show on the KPIs; the flagged node appears in the
   dependency graph; the execution-trace replay lists every step.
3. **Learning Studio** → on the captured improvement: **Accept / Edit / Reject** (human-in-the-loop),
   then **Run regression** (4/4), then **Approve & deploy** → Voice AI becomes **v2**. The version
   history (v1 → v2) and accumulated "memory" update.
4. Back to **Live Ops** → **Play** again → the Voice AI now answers the rental question correctly.
   (And in **Live Voice**, the pill now shows **Voice AI v2** — the training reached the real call.)

---

## One-liner for the room
"The Voice AI isn't just answering — it's part of a governed ecosystem. When it's wrong, governance
catches it, a human corrects it, and that correction becomes training the system applies to the next
call. Every answer is grounded in a specific policy document you can click straight to."
