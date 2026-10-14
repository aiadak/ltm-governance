# Deploying to GitHub + Vercel

This repo is one Vercel project: a static React build **plus** a Python serverless API. The included
`vercel.json` wires them together — no manual framework config needed.

## 1. Push to GitHub

```bash
cd ltm-governance
git init
git add .
git commit -m "LTM governed contact center"
git branch -M main
git remote add origin https://github.com/<you>/ltm-governance.git
git push -u origin main
```

(Or create the repo with the GitHub CLI: `gh repo create ltm-governance --public --source=. --push`.)

## 2. Import on Vercel

1. Go to **vercel.com → Add New → Project**, and import the `ltm-governance` repo.
2. Vercel reads `vercel.json`, so leave the defaults:
   - **Framework Preset:** Other
   - **Build Command / Output Directory:** already set by `vercel.json`
     (`cd web && npm install && npm run build` → `web/dist`).
3. (Optional) **Settings → Environment Variables** — add any of:
   - `ANTHROPIC_API_KEY` — turns on the real Claude brain for Voice AI / Summarization
   - `OPENAI_API_KEY` — OpenAI brain + real vector embeddings
   - `DATABASE_URL` — Postgres + pgvector durable storage (e.g. Neon or Vercel Postgres)
4. **Deploy.** The site is served from `web/dist`; every `/api/*` request hits the FastAPI function.

The app works immediately with **no** environment variables (simulated brain + deterministic
embeddings + in-memory stores). Add keys later to make it progressively more "real."

## 3. (Optional) Postgres + pgvector

1. Create a Postgres database that supports the `vector` extension — **Neon** or **Vercel Postgres**
   both do. (Neon: the project's connection string; prefer the **pooled** one for serverless.)
2. Set `DATABASE_URL` in Vercel → Environment Variables and redeploy.
3. That's it — the app **creates the schema and the `vector` extension automatically** on first
   request, seeds the documents with embeddings, and from then on uses **pgvector** for retrieval and
   persists claims, conversations, traces, violations, interventions, improvements and agent
   versions. No manual SQL needed. The driver is pure-Python (`pg8000`), so there's no Python-3.14
   wheel problem. If the DB is ever unreachable, the app automatically falls back to in-memory and
   keeps working (check the function logs for `[pg] error:` lines).

## Notes

- Vercel's Python runtime serves the FastAPI app via the exported `app` in `api/index.py`.
- Serverless functions are stateless between cold starts, so the in-memory stores reset periodically.
  That's fine for the demo; `DATABASE_URL` makes state durable.
- `requirements.txt` pins the Python deps Vercel installs for the function.
