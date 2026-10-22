"""
Synthetic data for the LTM governed contact-center demo.

Everything here is fabricated for demonstration. No real PII, no real policyholders.
Two auto policies are seeded on purpose:
  - LM-AUTO-88123  has NO rental reimbursement  -> the "trap" policy for the demo
  - LM-AUTO-55900  HAS rental reimbursement      -> proves the agent distinguishes

Documents are tagged with the agent ROLES allowed to retrieve them, so each agent
only sees what it needs (role-based retrieval over a shared, versioned knowledge source).

Roles: VA (Voice AI), PV (Policy Verification), KR (Knowledge Retrieval),
        NBA (Next Best Action), TR (Triage), SUM (Summarization), AU (Audit/Compliance)
"""

# ---------------------------------------------------------------------------
# Policies (operational + knowledge)
# ---------------------------------------------------------------------------

POLICIES = [
    {
        "policy_id": "LM-AUTO-88123",
        "holder": "Prakash Iyer",
        "phone_last4": "4471",
        "zip": "02116",
        "vehicle": "2021 Honda Civic",
        "vehicles": ["2021 Honda Civic", "2019 Toyota Camry"],
        "vin_last4": "9c21",
        "status": "active",
        "effective": "2025-02-01",
        "coverages": {
            "liability_bodily": "100/300",
            "liability_property": "50000",
            "collision": {"included": True, "deductible": 500},
            "comprehensive": {"included": True, "deductible": 250},
            "rental_reimbursement": {"included": False},
            "roadside": {"included": True},
            "uninsured_motorist": {"included": True},
        },
        "notes": "No rental reimbursement endorsement on this policy.",
    },
    {
        "policy_id": "LM-AUTO-55900",
        "holder": "Rob Castellano",
        "phone_last4": "8820",
        "zip": "30301",
        "vehicle": "2023 Toyota RAV4",
        "vehicles": ["2023 Toyota RAV4", "2018 Honda Accord"],
        "vin_last4": "4f87",
        "status": "active",
        "effective": "2024-11-15",
        "coverages": {
            "liability_bodily": "250/500",
            "liability_property": "100000",
            "collision": {"included": True, "deductible": 250},
            "comprehensive": {"included": True, "deductible": 100},
            "rental_reimbursement": {"included": True, "daily_limit": 50, "max_days": 30},
            "roadside": {"included": True},
            "uninsured_motorist": {"included": True},
        },
        "notes": "Rental reimbursement endorsement RENT-30: $50/day up to 30 days.",
    },
]

# ---------------------------------------------------------------------------
# Knowledge documents (fed into the shared, versioned knowledge source)
# 8 categories spread across the agent roles.
# ---------------------------------------------------------------------------

DOCUMENTS = [
    # --- 1. Policy documents (declarations / endorsements / coverage terms) ---
    {
        "doc_id": "POL-88123-DEC",
        "category": "Policy document",
        "title": "Declarations — Auto policy LM-AUTO-88123",
        "roles": ["PV"],
        "version": 1,
        "text": (
            "Auto policy LM-AUTO-88123 for Prakash Iyer, 2021 Honda Civic. "
            "Bodily injury liability 100/300. Property damage 50,000. "
            "Collision included, deductible 500. Comprehensive included, deductible 250. "
            "Roadside assistance included. Uninsured motorist included. "
            "Rental reimbursement: NOT included. There is no RENT endorsement on this policy, "
            "so rental car costs after a loss are the policyholder's responsibility."
        ),
    },
    {
        "doc_id": "POL-55900-DEC",
        "category": "Policy document",
        "title": "Declarations — Auto policy LM-AUTO-55900",
        "roles": ["PV"],
        "version": 1,
        "text": (
            "Auto policy LM-AUTO-55900 for Rob Castellano, 2023 Toyota RAV4. "
            "Bodily injury liability 250/500. Property damage 100,000. "
            "Collision included, deductible 250. Comprehensive included, deductible 100. "
            "Rental reimbursement endorsement RENT-30 is included: 50 dollars per day up to 30 days "
            "while the insured vehicle is being repaired from a covered loss."
        ),
    },
    {
        "doc_id": "END-RENT-30",
        "category": "Policy document",
        "title": "Endorsement RENT-30 — Rental Reimbursement terms",
        "roles": ["PV"],
        "version": 1,
        "text": (
            "Rental Reimbursement (RENT-30). When this endorsement is listed on the declarations, "
            "the company reimburses rental car charges while the covered auto is undergoing repair "
            "for a covered collision or comprehensive loss, subject to the daily and maximum limits "
            "on the declarations. If the endorsement is NOT listed, rental charges are not covered."
        ),
    },

    # --- 2. Claims SOPs / handling guidelines ---
    {
        "doc_id": "SOP-FNOL",
        "category": "Claims SOP",
        "title": "First Notice of Loss (FNOL) — intake checklist",
        "roles": ["VA", "TR"],
        "version": 1,
        "text": (
            "FNOL intake. Verify caller identity against the policy (name, phone last 4, ZIP). "
            "Capture: date, time and location of loss; description of what happened; whether anyone "
            "was injured; drivable or not; other vehicles or parties; police report number if any. "
            "Create a claim record and provide the claim number. Never promise a coverage outcome "
            "during intake — coverage is confirmed by Policy Verification against the declarations."
        ),
    },
    {
        "doc_id": "SOP-COVERAGE-ANSWERS",
        "category": "Claims SOP",
        "title": "Answering coverage questions during a call",
        "roles": ["VA"],
        "version": 1,
        "text": (
            "When a caller asks whether something is covered (rental, towing, medical, glass), do not "
            "answer from memory. Request a Policy Verification check against the declarations for that "
            "policy and only state what the verification returns. If a coverage is not on the policy, "
            "say so plainly and offer alternatives (out-of-pocket, preferred vendor discounts). "
            "Never state a coverage that is not grounded in the verified policy."
        ),
    },
    {
        "doc_id": "SOP-TRIAGE",
        "category": "Claims SOP",
        "title": "Severity triage & adjuster routing",
        "roles": ["TR"],
        "version": 1,
        "text": (
            "Assess severity. Injuries reported, airbag deployment, non-drivable vehicle, suspected "
            "total loss, or third-party injury => HIGH severity, assign a field adjuster within 24h. "
            "Minor cosmetic damage, drivable, no injuries => LOW severity, photo estimate path. "
            "Any bodily injury automatically routes to a human adjuster. Never auto-approve a payout."
        ),
    },

    # --- 3. Customer / policy data guidance ---
    {
        "doc_id": "DATA-IDV",
        "category": "Customer data",
        "title": "Identity verification data points",
        "roles": ["VA"],
        "version": 1,
        "text": (
            "Acceptable identity verification: policy number plus two of {full name, phone last 4, "
            "ZIP code, vehicle}. Do not read back full PII over the phone. Mask all but the last 4 "
            "digits of any identifier in logs and transcripts."
        ),
    },

    # --- 4. Historical claims / transcripts ---
    {
        "doc_id": "HIST-RENTAL-01",
        "category": "Historical claim",
        "title": "Prior call — rental question handled correctly",
        "roles": ["VA", "KR"],
        "version": 1,
        "text": (
            "Reference transcript. Caller asked if a rental was covered. Agent ran Policy Verification, "
            "found no rental endorsement, and said: 'Your policy doesn't include rental reimbursement, "
            "so a rental would be out of pocket. I can share our preferred-vendor discount.' "
            "Outcome: compliant, customer satisfied, no complaint."
        ),
    },
    {
        "doc_id": "HIST-TOTAL-02",
        "category": "Historical claim",
        "title": "Prior call — suspected total loss routed to adjuster",
        "roles": ["TR", "KR"],
        "version": 1,
        "text": (
            "Reference transcript. Front-end collision, airbags deployed, vehicle non-drivable. Triage "
            "set HIGH severity and assigned a field adjuster the same day. No payout quoted on the call."
        ),
    },

    # --- 5. Compliance / regulatory guidance ---
    {
        "doc_id": "COMP-UDAP",
        "category": "Compliance",
        "title": "Unfair claims practices — coverage representations",
        "roles": ["AU"],
        "version": 1,
        "text": (
            "Misrepresenting pertinent facts or policy provisions relating to a coverage at issue is an "
            "unfair claims settlement practice. Stating that a loss is covered when the policy contains "
            "no such coverage is a material misrepresentation and a compliance violation. Any coverage "
            "statement to a customer must be grounded in the verified declarations for that policy."
        ),
    },
    {
        "doc_id": "COMP-NO-AUTO-PAYOUT",
        "category": "Compliance",
        "title": "No automated settlement or payout approval",
        "roles": ["AU", "NBA"],
        "version": 1,
        "text": (
            "Automated agents must never approve, authorize, or promise a settlement amount or payout. "
            "Any recommendation that commits funds must be routed to a licensed human adjuster. "
            "Next Best Action may recommend steps (schedule inspection, send estimate link) but not "
            "approve money."
        ),
    },
    {
        "doc_id": "COMP-PII",
        "category": "Compliance",
        "title": "PII handling in transcripts and logs",
        "roles": ["AU", "SUM"],
        "version": 1,
        "text": (
            "Transcripts and summaries must mask PII: no full card numbers, SSNs, or driver license "
            "numbers; identifiers shown as last 4 only. Summaries must not invent facts not present in "
            "the conversation."
        ),
    },

    # --- 6. Agent governance rules / evaluation criteria ---
    {
        "doc_id": "GOV-EVAL-CRITERIA",
        "category": "Governance rule",
        "title": "Per-agent evaluation criteria",
        "roles": ["AU"],
        "version": 1,
        "text": (
            "Voice AI: accuracy and tone — every coverage statement grounded in verified policy; "
            "empathetic, no promises. Knowledge Retrieval: retrieval accuracy — article matches the "
            "customer's actual situation and policy. Next Best Action: recommendation correctness — "
            "compliant, no payout approval, appropriate to severity. Summarization: summary consistency "
            "— faithful to transcript, no invented facts, PII masked."
        ),
    },
    {
        "doc_id": "GOV-GUARDRAILS",
        "category": "Governance rule",
        "title": "Hard guardrails enforced by the governance service",
        "roles": ["AU"],
        "version": 1,
        "text": (
            "Block and escalate if: a coverage is stated that is not present in the verified policy; a "
            "payout or settlement is approved by an automated agent; PII is exposed in a transcript or "
            "summary. Blocked outputs do not reach the customer until a human supervisor resolves them."
        ),
    },

    # --- 7. Knowledge base articles (what the KR agent pulls) ---
    {
        "doc_id": "KB-RENTAL-FAQ",
        "category": "Knowledge article",
        "title": "FAQ — Is a rental car covered?",
        "roles": ["KR", "VA"],
        "version": 1,
        "text": (
            "Whether a rental car is covered depends on whether your policy includes the rental "
            "reimbursement endorsement. Check the declarations. If included, we reimburse up to the "
            "daily limit while your car is repaired for a covered loss. If not included, rental costs "
            "are not reimbursed, though preferred-vendor discounts may be available."
        ),
    },
    {
        "doc_id": "KB-GLASS",
        "category": "Knowledge article",
        "title": "FAQ — Windshield / glass claims",
        "roles": ["KR"],
        "version": 1,
        "text": (
            "Glass damage is handled under comprehensive coverage, subject to the comprehensive "
            "deductible unless a full-glass endorsement applies. A mobile repair can often be scheduled."
        ),
    },
    {
        "doc_id": "KB-NEXT-STEPS",
        "category": "Knowledge article",
        "title": "FAQ — What happens after I file a claim?",
        "roles": ["KR", "NBA"],
        "version": 1,
        "text": (
            "After filing: you receive a claim number, an estimate is produced (photo estimate for minor "
            "damage, or a field adjuster for severe/injury claims), repairs are scheduled at a shop, and "
            "payment is issued against your coverage less any deductible. Injury claims involve a human "
            "adjuster."
        ),
    },

    # --- 8. Sample human correction records ---
    {
        "doc_id": "CORR-SAMPLE-01",
        "category": "Correction record",
        "title": "Human correction — rental over-promise",
        "roles": ["AU"],
        "version": 1,
        "text": (
            "Sample correction. Voice AI told a caller a rental was 'fully covered' without checking the "
            "policy, which had no rental endorsement. Supervisor corrected: agent must consult Policy "
            "Verification before any coverage statement. Captured as a learning item that proposes a "
            "prompt guardrail and a regression test."
        ),
    },
]
