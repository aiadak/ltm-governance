"""
Real, in-memory telemetry for the Governance Command Center.

Every agent invocation (from the live per-turn router) and every LLM call records
its measured latency here, so the dashboard shows REAL numbers for this running
instance — agent-call counts, governance pass-rate, latency percentiles, token
usage — instead of fabricated figures. Before any activity, the dashboard falls
back to representative values and says so (mode: "warming up" / "simulated").

In-memory and per-process: on serverless this is per warm instance, which is the
honest scope for a live demo. We keep only the last N records to stay bounded.
"""
import time
import threading

_LOCK = threading.Lock()
_MAX = 4000
_agent_calls = []   # {agent, ms, passed, t}
_llm_calls = []     # {ms, tin, tout, source, t}


def record_agent(agent: str, ms: float, passed: bool = True, confidence=None, tin: int = 0, tout: int = 0):
    with _LOCK:
        _agent_calls.append({"agent": agent, "ms": float(ms), "passed": bool(passed),
                             "conf": (float(confidence) if confidence is not None else None),
                             "tin": int(tin or 0), "tout": int(tout or 0), "t": time.time()})
        if len(_agent_calls) > _MAX:
            del _agent_calls[: len(_agent_calls) - _MAX]


def record_llm(ms: float, tin: int, tout: int, source: str = ""):
    with _LOCK:
        _llm_calls.append({"ms": float(ms), "tin": int(tin), "tout": int(tout),
                           "source": source, "t": time.time()})
        if len(_llm_calls) > _MAX:
            del _llm_calls[: len(_llm_calls) - _MAX]


def _pct(values, p):
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    v = s[k]
    return int(round(v)) if v >= 10 else round(v, 1)  # keep sub-ms visible


def snapshot() -> dict:
    with _LOCK:
        agents = list(_agent_calls)
        llms = list(_llm_calls)
    n = len(agents)
    passed = sum(1 for a in agents if a["passed"])
    ms_all = [a["ms"] for a in agents] + [l["ms"] for l in llms]
    tin = sum(l["tin"] for l in llms)
    tout = sum(l["tout"] for l in llms)

    per = {}
    a_tin = a_tout = 0
    for a in agents:
        d = per.setdefault(a["agent"], {"calls": 0, "passed": 0, "ms": [], "conf": [], "tin": 0, "tout": 0})
        d["calls"] += 1
        d["passed"] += 1 if a["passed"] else 0
        d["ms"].append(a["ms"])
        if a.get("conf") is not None:
            d["conf"].append(a["conf"])
        d["tin"] += a.get("tin", 0)
        d["tout"] += a.get("tout", 0)
        a_tin += a.get("tin", 0)
        a_tout += a.get("tout", 0)

    # token economics = real LLM calls + per-agent (estimated) footprints
    tin_all, tout_all = tin + a_tin, tout + a_tout
    return {
        "has_data": n > 0,
        "agent_calls": n,
        "llm_calls": len(llms),
        "pass_rate": round(100.0 * passed / n, 1) if n else 0.0,
        "latency_ms": {"p50": _pct(ms_all, 50), "p95": _pct(ms_all, 95), "p99": _pct(ms_all, 99)},
        "tokens": {"input": tin_all, "output": tout_all, "total": tin_all + tout_all},
        "per_agent": {k: {"calls": v["calls"],
                          "pass_rate": round(100.0 * v["passed"] / v["calls"], 1) if v["calls"] else 0.0,
                          "avg_conf": round(100.0 * sum(v["conf"]) / len(v["conf"])) if v["conf"] else None,
                          "p50_ms": _pct(v["ms"], 50), "p95_ms": _pct(v["ms"], 95),
                          "tokens": v["tin"] + v["tout"], "tin": v["tin"], "tout": v["tout"]}
                      for k, v in per.items()},
    }


def reset():
    with _LOCK:
        _agent_calls.clear()
        _llm_calls.clear()
