"""
Braintrust observability — an OPTIONAL layer bolted on top of the self-contained
governance engine. When BRAINTRUST_API_KEY is set, every governance evaluation,
violation and human intervention from a call is logged to Braintrust as events,
so the traces + eval scores are searchable/analyzable there over time.

With no key, this is a complete no-op and the app is unchanged. We log via the
REST API (urllib, no SDK dependency) and batch one insert per call, so there is
no added latency per step and nothing can break a request.

Refs: POST /v1/project (get-or-create), POST /v1/project_logs/{id}/insert.
"""
import os
import json
import uuid
import urllib.request

_API = os.environ.get("BRAINTRUST_API_URL", "https://api.braintrust.dev")
_KEY = os.environ.get("BRAINTRUST_API_KEY")
_PROJECT = os.environ.get("BRAINTRUST_PROJECT", "LTM Governed Contact Center")
_project_id = None  # resolved once per process


def enabled() -> bool:
    return bool(_KEY)


def status() -> dict:
    return {"configured": bool(_KEY), "project": _PROJECT if _KEY else None}


def _post(path: str, body: dict, timeout: int = 5):
    req = urllib.request.Request(
        _API + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _resolve_project() -> str:
    global _project_id
    if _project_id:
        return _project_id
    data = _post("/v1/project", {"name": _PROJECT})
    _project_id = data.get("id") or (data.get("project") or {}).get("id")
    return _project_id


def event(agent, action, detail, metric="", score=None, passed=None,
          metadata=None) -> dict:
    """Build one Braintrust log event from a governance evaluation."""
    scores = {}
    if score is not None:
        scores["quality"] = max(0.0, min(1.0, float(score)))
    if passed is not None:
        scores["pass"] = 1.0 if passed else 0.0
    return {
        "id": uuid.uuid4().hex,
        "input": {"agent": agent, "action": action, "metric": metric},
        "output": detail,
        "scores": scores,
        "metadata": {"component": "governance", "agent": agent, **(metadata or {})},
    }


def log_batch(events) -> None:
    """Best-effort: flush a batch of events for one call. Never raises."""
    if not _KEY or not events:
        return
    try:
        pid = _resolve_project()
        if not pid:
            return
        _post(f"/v1/project_logs/{pid}/insert", {"events": events})
    except Exception:
        # observability must never break the app
        pass
