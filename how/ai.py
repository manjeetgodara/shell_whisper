"""Optional: let Claude re-rank / fill gaps. Used only when the `anthropic` package and credentials exist.

Any failure here silently falls back to the local ranking.
"""
from __future__ import annotations

import json
import os
import platform

MODEL = os.environ.get("HOW_MODEL", "claude-opus-5-5")

SCHEMA = {
    "type": "object",
    "properties": {
        "commands": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "desc": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["cmd", "desc", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["commands"],
    "additionalProperties": False,
}

SYSTEM = """You turn a plain-English request into shell commands for a command-line helper.
Return up to {n} commands, best first. Rules:
- Each `cmd` is a single runnable line. Write values the user must supply as <lowercase_placeholders>.
- `desc` is one short line saying what it does.
- `why` is one sentence that helps the user remember it next time (what the flags mean, the mental model).
- Prefer the candidate commands provided when they fit; they come from this user's installed tools.
- The user's OS is {os}. Don't invent flags; if unsure, choose the more common, safer form."""


def available() -> bool:
    if os.environ.get("HOW_NO_AI"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("HOW_AI"))


def suggest(query: str, candidates: list, n: int = 6) -> list | None:
    try:
        import anthropic

        client = anthropic.Anthropic(timeout=30.0, max_retries=1)
        cand = "\n".join(f"- {c['cmd']}  # {c['desc']}" for c in candidates[:15]) or "(none)"
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM.format(n=n, os=platform.system()),
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": f"Request: {query}\n\nCandidate commands:\n{cand}"}],
        )
        if response.stop_reason != "end_turn":
            return None
        text = "".join(b.text for b in response.content if b.type == "text")
        items = json.loads(text)["commands"]
    except Exception:  # network, auth, refusal, parse: the offline ranking still works
        return None
    out = []
    for it in items[:n]:
        out.append({"cmd": it["cmd"].strip(), "desc": it["desc"], "why": it["why"],
                    "tool": it["cmd"].split()[0] if it["cmd"].split() else "", "source": "claude"})
    return out or None
