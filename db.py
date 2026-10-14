"""
Postgres + pgvector schema (the durable upgrade path).

The app runs in-memory by default so it deploys with zero config. When
DATABASE_URL is set you can create these tables and back the three stores with
Postgres; retrieval uses the pgvector `<=>` cosine-distance operator. This module
exposes the schema and a connection helper; wiring the stores to it is the
"operational store / learning store in Postgres" step noted in the README.

Three stores map to these tables:
  knowledge  -> documents (+ vector)         [KnowledgeStore]
  operational-> policies, claims, conversations, turns, traces, violations, interventions
  learning   -> improvements, eval_cases, agent_versions
"""
import os

DATABASE_URL = os.environ.get("DATABASE_URL")

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

-- knowledge store (shared, versioned, role-tagged)
CREATE TABLE IF NOT EXISTS documents (
  doc_id     text PRIMARY KEY,
  title      text NOT NULL,
  category   text NOT NULL,
  roles      text[] NOT NULL,
  body       text NOT NULL,
  version    int  NOT NULL DEFAULT 1,
  embedding  vector(1536),
  added_at   timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documents_embedding_idx
  ON documents USING ivfflat (embedding vector_cosine_ops);

-- operational store
CREATE TABLE IF NOT EXISTS policies (
  policy_id text PRIMARY KEY, holder text, coverages jsonb, data jsonb
);
CREATE TABLE IF NOT EXISTS claims (
  claim_id text PRIMARY KEY, policy_id text REFERENCES policies(policy_id),
  loss jsonb, severity text, adjuster text, created_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conversations (
  conversation_id text PRIMARY KEY, policy_id text, started_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS turns (
  id bigserial PRIMARY KEY, conversation_id text, speaker text, body text,
  meta jsonb, t timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS traces (
  id text PRIMARY KEY, conversation_id text, agent text, action text, detail text,
  metric text, score real, passed boolean, step int, t timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS violations (
  id text PRIMARY KEY, conversation_id text, agent text, guardrail text,
  severity text, rule text, summary text, regulation text, t timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS interventions (
  id text PRIMARY KEY, conversation_id text, agent text, decision text, note text,
  t timestamptz DEFAULT now()
);

-- learning store (proposes; approval is separate)
CREATE TABLE IF NOT EXISTS agent_versions (
  agent text PRIMARY KEY, version int NOT NULL DEFAULT 1,
  prompt_addendum text DEFAULT '', updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS eval_cases (
  id text PRIMARY KEY, agent text, scenario text, expect text
);
CREATE TABLE IF NOT EXISTS improvements (
  id text PRIMARY KEY, agent text, conversation_id text, error text, root_cause text,
  correction text, proposed_fix jsonb, guardrail text, status text DEFAULT 'proposed',
  regression jsonb, deployed_version int, created_at timestamptz DEFAULT now()
);
"""


def get_conn():
    """Return a psycopg connection when DATABASE_URL is set, else None."""
    if not DATABASE_URL:
        return None
    try:
        import psycopg
        return psycopg.connect(DATABASE_URL)
    except Exception:
        return None


def db_status() -> dict:
    return {"configured": bool(DATABASE_URL),
            "mode": "postgres+pgvector" if DATABASE_URL else "in-memory"}
