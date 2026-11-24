"""Tiny JSON persistence under ~/.how (override with HOW_HOME)."""
import json
import os
from pathlib import Path


def home() -> Path:
    p = Path(os.environ.get("HOW_HOME") or Path.home() / ".how")
    p.mkdir(parents=True, exist_ok=True)
    return p


def load(name: str, default):
    f = home() / f"{name}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(name: str, data) -> None:
    f = home() / f"{name}.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


# --- learned tools: {tool: [entry, ...]} -------------------------------------
def learned() -> dict:
    return load("learned", {})


def learned_entries() -> list:
    return [e for entries in learned().values() for e in entries]


# --- self-heal memory: {cmd_template: {"flags": [...], "positional": n}} ------
def heals() -> dict:
    return load("heal", {})


def add_heal(cmd: str, flags=(), positional: int = 0) -> bool:
    """Remember what a command needed. Returns True if anything new was learned."""
    data = heals()
    h = data.setdefault(cmd, {"flags": [], "positional": 0})
    before = (list(h["flags"]), h["positional"])
    for f in flags:
        if f not in h["flags"]:
            h["flags"].append(f)
    h["positional"] = max(h["positional"], positional)
    save("heal", data)
    return (h["flags"], h["positional"]) != before


# --- usage history: {cmd_template: times_picked} -----------------------------
def bump_usage(cmd: str) -> None:
    data = load("usage", {})
    data[cmd] = data.get(cmd, 0) + 1
    save("usage", data)


def usage() -> dict:
    return load("usage", {})
