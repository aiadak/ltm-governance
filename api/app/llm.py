"""
LLM access layer. Real when keyed, simulated otherwise.

- ANTHROPIC_API_KEY  -> Claude brain available
- OPENAI_API_KEY     -> OpenAI brain available
- neither            -> deterministic simulation (demo still runs end-to-end)

Agents call `complete()` to phrase natural language and `judge()` to get an
LLM-as-judge score. Core agent *decisions* are grounded in retrieved policy data
(see agents.py), so the governance demo is reliable with or without a key.
"""
import os
import json
from typing import List, Dict, Optional

_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
_OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
_ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def llm_status() -> dict:
    brains = []
    if _ANTHROPIC_KEY:
        brains.append("claude")
    if _OPENAI_KEY:
        brains.append("openai")
    return {
        "live": bool(brains),
        "brains": brains,
        "default": brains[0] if brains else "simulated",
    }


def _anthropic(system: str, user: str, max_tokens: int) -> Optional[str]:
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=_ANTHROPIC_KEY)
        msg = client.messages.create(
            model=_ANTHROPIC_MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    except Exception:
        return None


def _openai(system: str, user: str, max_tokens: int) -> Optional[str]:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=_OPENAI_KEY)
        resp = client.chat.completions.create(
            model=_OPENAI_MODEL, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return None


def complete(system: str, user: str, brain: str = "", max_tokens: int = 300,
             fallback: str = "") -> dict:
    """Return {text, source} where source is 'claude' | 'openai' | 'simulated'."""
    brain = brain or llm_status()["default"]
    if brain == "claude" and _ANTHROPIC_KEY:
        out = _anthropic(system, user, max_tokens)
        if out:
            return {"text": out, "source": "claude"}
    if brain == "openai" and _OPENAI_KEY:
        out = _openai(system, user, max_tokens)
        if out:
            return {"text": out, "source": "openai"}
    # try any available brain before simulating
    if _ANTHROPIC_KEY:
        out = _anthropic(system, user, max_tokens)
        if out:
            return {"text": out, "source": "claude"}
    if _OPENAI_KEY:
        out = _openai(system, user, max_tokens)
        if out:
            return {"text": out, "source": "openai"}
    return {"text": fallback, "source": "simulated"}


def judge(system: str, user: str, brain: str = "") -> Optional[dict]:
    """LLM-as-judge returning parsed JSON {score:0..1, pass:bool, reason:str} or None."""
    sys = system + "\nRespond with ONLY compact JSON: {\"score\":0..1,\"pass\":true/false,\"reason\":\"...\"}."
    res = complete(sys, user, brain=brain, max_tokens=200, fallback="")
    if res["source"] == "simulated" or not res["text"]:
        return None
    try:
        txt = res["text"]
        start, end = txt.find("{"), txt.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(txt[start:end + 1])
            return {"score": float(data.get("score", 0)),
                    "pass": bool(data.get("pass", False)),
                    "reason": str(data.get("reason", "")),
                    "source": res["source"]}
    except Exception:
        return None
    return None
