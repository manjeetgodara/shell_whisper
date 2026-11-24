"""`how learn <tool>`: teach `how` a CLI by recursively reading its --help."""
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from how import risk, store

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|.\x08")
# "  run         Create and run…"  /  "  auth:   Authenticate…"  /  "  compose*  Docker Compose"
CMD_LINE = re.compile(r"^\s{1,8}([a-z][a-z0-9_-]*)(?:\s*,\s*[a-z][\w-]*)*\*?:?\s{2,}(\S.*)$")
SKIP_SECTION = re.compile(r"option|flag|example|usage|environment|learn more|feedback|inherited|"
                          r"argument|alias|json field|see also|exit|topic", re.I)
REQUIRED_FLAG = re.compile(r"^\s*(?:-\w,\s*)?(--[\w-]+)(?:\s+(\w+))?\s+.*\((?:required|REQUIRED)\)")
SKIP_NAMES = {"help", "completion", "version", "__complete", "__completenoerr"}


def run_help(argv, timeout=10):
    env = dict(os.environ, NO_COLOR="1", PAGER="cat", GH_PAGER="cat", GIT_PAGER="cat",
               TERM="dumb", COLUMNS="200", GH_NO_UPDATE_NOTIFIER="1")
    try:
        p = subprocess.run(argv + ["--help"], capture_output=True, timeout=timeout, env=env,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    text = (p.stdout or b"") + b"\n" + (p.stderr or b"")
    return ANSI.sub("", text.decode("utf-8", errors="replace"))


def parse_subcommands(text: str):
    """Return [(name, description)] found in command-listing sections of help text."""
    out, section_ok, seen = [], True, set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        is_header = (not line[:1].isspace() and (stripped.endswith(":") or stripped.isupper()
                                                 or re.match(r"^[A-Z][A-Z ]+$", stripped))) \
            or (not line[:1].isspace() and len(stripped.split()) <= 6 and not CMD_LINE.match(line))
        if is_header:
            section_ok = not SKIP_SECTION.search(stripped)
            continue
        if not section_ok:
            continue
        m = CMD_LINE.match(line)
        if m and m.group(1) not in seen and m.group(1) not in SKIP_NAMES:
            seen.add(m.group(1))
            out.append((m.group(1), m.group(2).strip().rstrip(".")))
    return out


def parse_usage(text: str, path):
    """Turn the Usage line into a template with <placeholders> for required positionals."""
    m = re.search(r"(?im)^\s*usage:?\s*(.*)$", text)
    if not m:
        return " ".join(path)
    line = m.group(1).strip()
    if not line:  # "USAGE\n  gh pr create [flags]"
        rest = text[m.end():].lstrip("\r\n")
        line = rest.splitlines()[0].strip() if rest else ""
    words = line.split()
    # Drop the leading command words, whatever binary name the tool prints for itself.
    last = path[-1]
    if last in words:
        words = words[words.index(last) + 1:]
    elif len(path) == 1:
        words = words[1:]
    line = " ".join(words)
    line = re.sub(r"\{\s*([^{}|]+?)\s*(\|[^{}]*)?\}", r"\1", line)  # "{<number> | <url>}" -> "<number>"
    line = re.sub(r"\[[^\[\]]*\]", "", line)          # optional bits
    line = re.sub(r"\[[^\[\]]*\]", "", line)          # nested optional
    line = re.sub(r"\s*\|\s*(<[^>]+>|[A-Z][A-Z0-9_]*|-)(?=\s|$)", "", line)  # "PATH | URL | -" -> "PATH"
    parts = []
    for w in line.split():
        if w.startswith("<") or w.startswith("-"):
            parts.append(w)
        elif re.fullmatch(r"[A-Z][A-Z0-9_]*(\.\.\.)?", w):
            parts.append("<" + w.rstrip(".").lower() + ">")
        elif re.fullmatch(r"[a-z][\w-]*", w) and w in ("flags", "options", "command"):
            continue
    required = []
    for l in text.splitlines():
        r = REQUIRED_FLAG.match(l)
        if r:
            required.append(f"{r.group(1)} <{(r.group(2) or r.group(1).lstrip('-')).lower()}>")
    return " ".join(path + parts + required)


def learn(tool: str, depth: int = 3, workers: int = 16, echo=print):
    exe = shutil.which(tool)
    if not exe:
        raise SystemExit(f"how: can't find `{tool}` on your PATH")
    entries, frontier, visited = [], [((tool,), f"{tool}")], set()
    root_help = run_help([exe])
    if not root_help.strip():
        raise SystemExit(f"how: `{tool} --help` printed nothing")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        level = 0
        helps = {(tool,): root_help}
        descs = {(tool,): ""}
        while frontier and level <= depth:
            # Fetch help for everything on this level in parallel.
            todo = [p for p, _ in frontier if p not in helps]
            for p, h in zip(todo, pool.map(lambda p: run_help([exe, *p[1:]]), todo)):
                helps[p] = h
            next_frontier = []
            for path, _ in frontier:
                if path in visited:
                    continue
                visited.add(path)
                text = helps.get(path, "")
                subs = parse_subcommands(text) if level < depth else []
                # A command listing its own name as a sub is a parse artefact.
                subs = [(n, d) for n, d in subs if n != path[-1]]
                if subs:
                    for name, desc in subs:
                        child = path + (name,)
                        descs[child] = desc
                        next_frontier.append((child, desc))
                elif len(path) > 1:
                    cmd = parse_usage(text, list(path))
                    desc = descs.get(path, "")
                    entries.append({
                        "cmd": cmd, "desc": desc or " ".join(path),
                        "why": f"Learned from `{' '.join(path)} --help`.",
                        "tags": " ".join(path[1:]), "tool": tool, "source": "learned",
                        "risk": risk.classify(cmd, desc),
                    })
            echo(f"  depth {level}: {len(frontier)} command(s) read, {len(entries)} learned so far",
                 end="\r" if sys.stdout.isatty() else "\n")
            frontier = next_frontier
            level += 1
    echo("")
    data = store.learned()
    data[tool] = entries
    store.save("learned", data)
    return entries


def forget(tool: str) -> bool:
    data = store.learned()
    if tool in data:
        del data[tool]
        store.save("learned", data)
        return True
    return False
