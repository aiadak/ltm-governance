# LTM Governed Contact Center

An **agent governance & continuous-learning platform for a whole contact center** — not just a voice
chatbot. A LTM Insurance–style auto-claim call runs through a governed multi-agent ecosystem: a
Voice AI handles the call, supporting agents fire (Policy Verification, Knowledge Retrieval, Next
Best Action, Triage, Summarization), and a governance layer (Audit/Compliance + a Human Supervisor)
monitors every agent in real time. When the Voice AI over-promises rental coverage, governance
catches it, a human corrects it, and the mistake becomes training data that produces a better next
version — the **closed loop**.

Everything runs on **synthetic data**. Real LLMs are used when API keys are present, and the app
still runs end-to-end with no keys at all (simulated brain + deterministic embeddings).

## The three experiences (tabs)

1. **Live Ops** — the live claims conversation: Voice AI ↔ customer (left), supporting agents firing
   (middle), real-time governance checks, green/red (right).
2. **Control Tower** — the governance command center: KPI cards, the interactive **agent dependency
   graph** (click a node to see downstream impact of an upstream error), the **agent performance
   matrix**, and an **execution-trace replay**.
3. **Learning Studio** — the continuous-learning loop: detected error → root cause → human correction
   → proposed fix → regression test → approved new version. **Learning proposes; governance approves.**

Plus **Live Voice** (talk to the Voice AI out loud via OpenAI Realtime over WebRTC — grounded in the
selected policy), **Agent Registry** (every agent/guardian, owner, risk, metric, version) and
**Knowledge Base** (feed documents with role-based retrieval; test what each agent can see).

### Live Voice
The **Live Voice** tab opens a real spoken call with the claims Voice AI. The backend mints a
short-lived OpenAI Realtime ephemeral token (`/api/realtime/token`, model `gpt-realtime-2.1`); the
browser streams mic audio straight to OpenAI over WebRTC and plays the reply. Requires
`OPENAI_API_KEY`; without it the tab shows how to enable it. The agent's instructions are built
server-side from the chosen policy's coverages, so it only states coverage that policy actually has.

## Architecture

- **Front end:** React + Vite (repo root: `index.html`, `src/`), LTM dark/coral theme.
- **Back end:** Python **FastAPI** agent orchestrator (`api/`), deployed as a Vercel serverless
  function. Six functional agents + a central governance service + a learning service.
- **Three stores** (`api/app/stores.py`):
  - **Knowledge** — shared, versioned knowledge source with **role-based vector retrieval**.
  - **Operational** — claims, conversations, agent execution traces, violations, interventions.
  - **Learning** — feedback items, synthetic evaluation cases, agent versions, deployment decisions.
- **Storage:** in-memory by default (zero-config). Set `DATABASE_URL` to use **Postgres + pgvector**;
  the full schema is in `api/app/db.py`.
- **Observability (optional):** set `BRAINTRUST_API_KEY` to stream every governance evaluation,
  violation and intervention to **Braintrust** as log events (scores + metadata). This bolts on top
  of the self-contained governance engine — with no key it is a complete no-op (`api/app/observability.py`).
- **No fine-tuning.** "Learning" = prompt/guardrail + retrieval updates, gated by a regression test.

## Run locally

Two terminals:

```bash
# 1) backend
pip install -r requirements.txt
uvicorn api.index:app --reload --port 8000

# 2) frontend (proxies /api to :8000)
npm install && npm run dev
# open http://localhost:5173
```

## Demo script (90 seconds)

1. **Live Ops** → keep policy `LM-AUTO-88123` (no rental) → **Play governed call**. The Voice AI says
   rental is "fully covered"; Policy Verification contradicts it; Audit flags the compliance violation
   and **blocks** it; the Human Supervisor corrects it and the Voice AI apologizes.
2. **Control Tower** → see the violation + intervention KPIs, the flagged node in the dependency graph,
   and the step-by-step trace.
3. **Learning Studio** → on the captured improvement, **Run regression test** (4/4) → **Approve & deploy**.
   Voice AI goes to v2.
4. Back to **Live Ops** → **Play** again → the Voice AI now answers correctly. Switch to `LM-AUTO-55900`
   (has rental) to show it distinguishes policies.

## Deploy to GitHub + Vercel

See `DEPLOY.md`.

## Environment variables

See `.env.example`. All optional.

| Var | Effect |
|-----|--------|
| `ANTHROPIC_API_KEY` | Voice AI / Summarization use the Claude brain |
| `OPENAI_API_KEY` | OpenAI brain + real vector embeddings |
| `DATABASE_URL` | Postgres + pgvector durable storage |

> Synthetic data only, no real PII. Automated agents never approve a payout/settlement — always routed
> to a human. No coverage is ever stated that isn't grounded in the verified policy.
