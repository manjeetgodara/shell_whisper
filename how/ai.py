"""Optional: let an LLM re-rank / fill gaps. Two providers:

- deepinfra: DeepInfra's OpenAI-compatible API, called with urllib (no extra package). Needs DEEPINFRA_API_KEY.
- claude:    the `anthropic` package plus ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN).

HOW_PROVIDER picks one explicitly; otherwise DeepInfra is used when its key is set, else Claude.
HOW_MODEL overrides the model. Any failure here silently falls back to the local ranking.
"""
from __future__ import annotations

import json
import os
import platform
import re
import urllib.request

DEFAULT_MODELS = {
    "claude": "claude-opus-5-5",
    "deepinfra": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
}
LABELS = {"claude": "Claude", "deepinfra": "DeepInfra"}
DEEPINFRA_URL = os.environ.get("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai") + "/chat/completions"

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

JSON_HINT = """
Reply with JSON only, no prose and no code fences, exactly in this shape:
{"commands": [{"cmd": "...", "desc": "...", "why": "..."}]}"""


def _has_anthropic() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("HOW_AI"))


def provider() -> str | None:
    """Which provider to use, or None if none is configured."""
    if os.environ.get("HOW_NO_AI"):
        return None
    forced = os.environ.get("HOW_PROVIDER", "").strip().lower()
    if forced == "deepinfra":
        return "deepinfra" if os.environ.get("DEEPINFRA_API_KEY") else None
    if forced == "claude":
        return "claude" if _has_anthropic() else None
    if os.environ.get("DEEPINFRA_API_KEY"):
        return "deepinfra"
    if _has_anthropic():
        return "claude"
    return None


def available() -> bool:
    return provider() is not None


def label() -> str:
    return LABELS.get(provider() or "", "AI")


def _model(p: str) -> str:
    return os.environ.get("HOW_MODEL") or DEFAULT_MODELS[p]


def _prompt(query: str, candidates: list) -> str:
    cand = "\n".join(f"- {c['cmd']}  # {c['desc']}" for c in candidates[:15]) or "(none)"
    return f"Request: {query}\n\nCandidate commands:\n{cand}"


def _ask_claude(query: str, candidates: list, n: int) -> str | None:
    import anthropic

    client = anthropic.Anthropic(timeout=30.0, max_retries=1)
    response = client.beta.messages.create(
        model=_model("claude"),
        max_tokens=4000,
        system=SYSTEM.format(n=n, os=platform.system()),
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": _prompt(query, candidates)}],
    )
    if response.stop_reason != "end_turn":
        return None
    return "".join(b.text for b in response.content if b.type == "text")


def _ask_deepinfra(query: str, candidates: list, n: int) -> str | None:
    body = {
        "model": _model("deepinfra"),
        "messages": [
            {"role": "system", "content": SYSTEM.format(n=n, os=platform.system()) + JSON_HINT},
            {"role": "user", "content": _prompt(query, candidates)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 2000,
    }
    req = urllib.request.Request(
        DEEPINFRA_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {os.environ['DEEPINFRA_API_KEY']}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choice = data["choices"][0]
    if choice.get("finish_reason") not in (None, "stop"):
        return None
    return choice["message"]["content"]


def _parse(text: str) -> list:
    """Pull the commands list out of a reply, tolerating code fences or stray prose around the JSON."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start:end + 1] if start != -1 else text)
    items = data["commands"] if isinstance(data, dict) else data
    return [it for it in items if isinstance(it, dict) and str(it.get("cmd", "")).strip()]


def suggest(query: str, candidates: list, n: int = 6) -> list | None:
    p = provider()
    if not p:
        return None
    try:
        ask = _ask_deepinfra if p == "deepinfra" else _ask_claude
        text = ask(query, candidates, n)
        if not text:
            return None
        items = _parse(text)
    except Exception:  # network, auth, refusal, parse: the offline ranking still works
        return None
    out = []
    for it in items[:n]:
        cmd = str(it["cmd"]).strip()
        out.append({"cmd": cmd, "desc": str(it.get("desc", "")), "why": str(it.get("why", "")),
                    "tool": cmd.split()[0], "source": p})
    return out or None
