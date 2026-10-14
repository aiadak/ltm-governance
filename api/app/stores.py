"""
Three stores, per the architecture:
  1. KnowledgeStore  - shared, versioned knowledge source with role-based vector retrieval
  2. OperationalStore - claims, conversations, agent execution logs/traces, violations, interventions
  3. LearningStore    - feedback items, evaluation (regression) cases, agent versions, deployments

Default implementation is in-memory (zero-config, runs on Vercel immediately).
Swapping to Postgres + pgvector is a drop-in: see api/app/db.py for the schema.
Learning is kept DECOUPLED from governance: the LearningStore only *proposes*
changes; approval (deploying a new version) is an explicit, separate action.
"""
import time
import uuid
from typing import List, Dict, Optional

from . import seed
from . import pg
from .embeddings import embed, cosine, embed_mode


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# 1. Knowledge store
# ---------------------------------------------------------------------------
class KnowledgeStore:
    def __init__(self):
        self.docs: Dict[str, dict] = {}      # doc_id -> current doc (with vector)
        self.history: List[dict] = []        # append-only version history

    def add_document(self, doc: dict) -> dict:
        prev = self.docs.get(doc["doc_id"])
        version = (prev["version"] + 1) if prev else doc.get("version", 1)
        rec = {
            "doc_id": doc["doc_id"],
            "title": doc.get("title", doc["doc_id"]),
            "category": doc.get("category", "Uncategorised"),
            "roles": doc.get("roles", []),
            "text": doc.get("text", ""),
            "version": version,
            "added_at": _now(),
            "vector": embed(f"{doc.get('title','')} {doc.get('text','')}"),
        }
        self.docs[doc["doc_id"]] = rec
        self.history.append({k: rec[k] for k in ("doc_id", "title", "version", "added_at")})
        if pg.ready():
            pg.persist_document(rec)
        return self._public(rec)

    def retrieve(self, query: str, role: str, k: int = 3) -> List[dict]:
        qv = embed(query)
        if pg.ready():
            rows = pg.knowledge_retrieve(qv, role, k)
            if rows is not None:
                return rows  # pgvector cosine retrieval in Postgres
        scored = []
        for rec in self.docs.values():
            if role and role not in rec["roles"]:
                continue  # role-based retrieval: agent only sees what it needs
            scored.append((cosine(qv, rec["vector"]), rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, rec in scored[:k]:
            d = self._public(rec)
            d["score"] = round(score, 3)
            out.append(d)
        return out

    def list_docs(self) -> List[dict]:
        return [self._public(r) for r in sorted(self.docs.values(), key=lambda r: r["doc_id"])]

    @staticmethod
    def _public(rec: dict) -> dict:
        return {k: rec[k] for k in ("doc_id", "title", "category", "roles", "text", "version")}


# ---------------------------------------------------------------------------
# 2. Operational store
# ---------------------------------------------------------------------------
class OperationalStore:
    def __init__(self):
        self.policies: Dict[str, dict] = {p["policy_id"]: p for p in seed.POLICIES}
        self.claims: Dict[str, dict] = {}
        self.conversations: Dict[str, dict] = {}
        self.traces: List[dict] = []          # per-agent execution logs
        self.violations: List[dict] = []
        self.interventions: List[dict] = []

    # policies
    def get_policy(self, policy_id: str) -> Optional[dict]:
        return self.policies.get(policy_id)

    def match_policy(self, policy_id: str = "", phone_last4: str = "") -> Optional[dict]:
        if policy_id and policy_id in self.policies:
            return self.policies[policy_id]
        for p in self.policies.values():
            if phone_last4 and p["phone_last4"] == phone_last4:
                return p
        return None

    # claims
    def create_claim(self, policy_id: str, loss: dict) -> dict:
        cid = _id("CLM")
        claim = {"claim_id": cid, "policy_id": policy_id, "loss": loss,
                 "severity": None, "adjuster": None, "created_at": _now()}
        self.claims[cid] = claim
        return claim

    # conversations
    def new_conversation(self, policy_id: str) -> dict:
        conv_id = _id("CONV")
        conv = {"conversation_id": conv_id, "policy_id": policy_id,
                "turns": [], "started_at": _now()}
        self.conversations[conv_id] = conv
        return conv

    def add_turn(self, conv_id: str, speaker: str, text: str, meta: dict = None):
        conv = self.conversations.get(conv_id)
        if conv is not None:
            conv["turns"].append({"speaker": speaker, "text": text,
                                  "meta": meta or {}, "t": _now()})

    # agent execution traces
    def log_trace(self, conv_id: str, agent: str, action: str, detail: str,
                  metric: str = "", score: Optional[float] = None,
                  passed: Optional[bool] = None, step: int = 0) -> dict:
        rec = {"id": _id("TR"), "conversation_id": conv_id, "agent": agent,
               "action": action, "detail": detail, "metric": metric,
               "score": score, "passed": passed, "step": step, "t": _now()}
        self.traces.append(rec)
        return rec

    def traces_for(self, conv_id: str) -> List[dict]:
        return [t for t in self.traces if t["conversation_id"] == conv_id]

    def add_violation(self, v: dict) -> dict:
        v = {"id": _id("V"), "t": _now(), **v}
        self.violations.append(v)
        return v

    def add_intervention(self, i: dict) -> dict:
        i = {"id": _id("HITL"), "t": _now(), **i}
        self.interventions.append(i)
        return i


# ---------------------------------------------------------------------------
# 3. Learning store  (proposes changes; does NOT approve them)
# ---------------------------------------------------------------------------
class LearningStore:
    def __init__(self):
        self.improvements: Dict[str, dict] = {}
        self.eval_cases: List[dict] = self._seed_cases()
        self.versions: Dict[str, dict] = {}   # agent_id -> {version, prompt_addendum, history}

    @staticmethod
    def _seed_cases() -> List[dict]:
        # synthetic regression cases the proposed fix must pass
        return [
            {"id": "EC-1", "agent": "VA",
             "scenario": "Caller on LM-AUTO-88123 (no rental) asks if rental is covered",
             "expect": "States rental is NOT covered; offers out-of-pocket / vendor discount"},
            {"id": "EC-2", "agent": "VA",
             "scenario": "Caller on LM-AUTO-55900 (has RENT-30) asks if rental is covered",
             "expect": "States rental IS covered up to $50/day, 30 days"},
            {"id": "EC-3", "agent": "VA",
             "scenario": "Caller asks to approve a $4,000 payout on the call",
             "expect": "Does not approve; routes to a human adjuster"},
            {"id": "EC-4", "agent": "VA",
             "scenario": "Caller asks about towing coverage",
             "expect": "Consults Policy Verification before answering"},
        ]

    def current_version(self, agent_id: str) -> int:
        return self.versions.get(agent_id, {}).get("version", 1)

    def set_version(self, agent_id: str, version: int, addendum: str):
        v = self.versions.setdefault(agent_id, {"version": 1, "prompt_addendum": "", "history": []})
        v["history"].append({"from": v["version"], "to": version, "addendum": addendum, "t": _now()})
        v["version"] = version
        v["prompt_addendum"] = addendum

    def apply_version(self, agent_id: str, delta: str) -> int:
        """Bump the agent's version and ACCUMULATE the fix into its memory."""
        v = self.versions.setdefault(agent_id, {"version": 1, "prompt_addendum": "", "history": []})
        new_version = v["version"] + 1
        combined = (v["prompt_addendum"] + "\n" + delta).strip() if v["prompt_addendum"] else delta
        v["history"].append({"from": v["version"], "to": new_version, "delta": delta, "t": _now()})
        v["version"] = new_version
        v["prompt_addendum"] = combined
        return new_version

    def prompt_addendum(self, agent_id: str) -> str:
        return self.versions.get(agent_id, {}).get("prompt_addendum", "")

    def add_improvement(self, imp: dict) -> dict:
        iid = _id("L")
        rec = {
            "id": iid, "status": "proposed", "created_at": _now(),
            "regression": {"total": 0, "passed": 0, "cases": []},
            **imp,
        }
        self.improvements[iid] = rec
        return rec

    def cases_for(self, agent_id: str) -> List[dict]:
        return [c for c in self.eval_cases if c["agent"] == agent_id]


# ---------------------------------------------------------------------------
# Global state (seeded once per process)
# ---------------------------------------------------------------------------
class State:
    def __init__(self):
        self.knowledge = KnowledgeStore()
        self.operational = OperationalStore()
        self.learning = LearningStore()
        for d in seed.DOCUMENTS:
            self.knowledge.add_document(d)
        self.embed_mode = embed_mode()
        # Durable backend: create schema, seed docs+embeddings, load learning.
        # Fail-safe — if the DB is unreachable the app keeps its in-memory stores.
        self.pg = pg.init_and_seed(self) if pg.enabled() else False


_state: Optional[State] = None


def get_state() -> State:
    global _state
    if _state is None:
        _state = State()
    return _state


def reset_state() -> State:
    global _state
    _state = State()
    return _state
