"""Fill placeholders, confirm risky commands, run, and self-heal from failures."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys

from how import risk, store

PLACEHOLDER = re.compile(r"<([^<>]+)>")
DIM, RESET, RED, YELLOW, GREEN, BOLD = "\033[2m", "\033[0m", "\033[31m", "\033[33m", "\033[32m", "\033[1m"

# Error messages that say "you forgot a parameter", across common CLI frameworks.
_FLAG_PATTERNS = [
    re.compile(r'required flag\(s\) ((?:"[^"]+"(?:,\s*)?)+) not set'),          # cobra (gh, kubectl, docker)
    re.compile(r"the following arguments are required: (.+)"),                  # argparse
    re.compile(r"[Mm]issing (?:required )?(?:option|flag|argument|parameter)s?:?\s+['\"`]?(--?[\w-]+)"),
    re.compile(r"[Oo]ption ['\"`]?(--?[\w-]+)['\"`]? is required"),
    re.compile(r"must (?:provide|specify|pass|set)\b[^\n]*"),                    # gh: must provide `--title` and `--body`
    re.compile(r"(--[\w-]+) (?:is|are) required"),
    re.compile(r"required option ['\"`]?(--?[\w-]+)"),                          # click
]
_POSITIONAL_PATTERNS = [
    re.compile(r"requires (?:at least|exactly) (\d+) arg"),                     # docker, cobra
    re.compile(r"accepts (?:at least |between )?(\d+)(?: and \d+)? arg\(s\), received 0"),
    re.compile(r"(?:missing|requires an?) (?:required )?(?:positional )?argument", re.I),
    re.compile(r"(?:not enough|too few) arguments", re.I),
]


def diagnose(stderr: str):
    """Return (flags, positional_count) the error says were missing."""
    flags, positional = [], 0
    for i, pat in enumerate(_FLAG_PATTERNS):
        for m in pat.finditer(stderr):
            found = re.findall(r"--?[A-Za-z][\w-]*", m.group(0))
            if i == 0:  # cobra quotes bare names: required flag(s) "title", "body" not set
                found = ["--" + n.lstrip("-") for n in re.findall(r'"([^"]+)"', m.group(1))]
            for f in found:
                if f not in flags and not re.fullmatch(r"-(?:h|-help)", f):
                    flags.append(f)
            # argparse lists positionals by bare name: "required: name, --flag"
            if "arguments are required" in m.group(0):
                for name in re.split(r",\s*|\s+", m.group(1)):
                    if name and not name.startswith("-"):
                        positional += 1
    for pat in _POSITIONAL_PATTERNS:
        m = pat.search(stderr)
        if m:
            n = int(m.group(1)) if m.groups() and m.group(1) and m.group(1).isdigit() else 1
            positional = max(positional, n)
    return flags, positional


def apply_heals(template: str) -> tuple[str, list]:
    """Add anything a previous failure taught us this command needs."""
    h = store.heals().get(template)
    if not h:
        return template, []
    notes, cmd = [], template
    have_pos = len(PLACEHOLDER.findall(template))
    for i in range(have_pos, h.get("positional", 0)):
        cmd += f" <arg{i + 1}>"
        notes.append(f"a positional argument")
    for f in h.get("flags", []):
        if not re.search(rf"(^|\s){re.escape(f)}(\s|=|$)", cmd):
            cmd += f" {f} <{f.lstrip('-')}>"
            notes.append(f)
    return cmd, notes


def fill(cmd: str) -> str | None:
    """Prompt for each <placeholder>. Returns None if the user bails out."""
    names = list(dict.fromkeys(PLACEHOLDER.findall(cmd)))
    if names:
        print(f"{DIM}fill in the blanks (enter = keep placeholder, ctrl-c = cancel){RESET}")
    for name in names:
        try:
            val = input(f"  {BOLD}{name}{RESET}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if val:
            q = val if re.fullmatch(r"[\w./:@=,+%-]+", val) else _quote(val)
            cmd = cmd.replace(f"<{name}>", q)
    return cmd


def _quote(s: str) -> str:
    if os.name == "nt":
        return '"' + s.replace('"', '\\"') + '"'
    return shlex.quote(s)


def copy_to_clipboard(text: str) -> bool:
    for argv in (["clip"], ["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-b", "-i"]):
        try:
            subprocess.run(argv, input=text.encode("utf-16le" if argv == ["clip"] else "utf-8"),
                           check=True, capture_output=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            continue
    return False


def confirm(cmd: str, level: str) -> bool:
    try:
        if level == risk.DANGER:
            print(f"{RED}▲ destructive:{RESET} this can delete or overwrite things.")
            return input(f"  type {BOLD}yes{RESET} to run: ").strip().lower() == "yes"
        if level == risk.WRITE:
            return input(f"{YELLOW}●{RESET} this changes state. run it? [Y/n] ").strip().lower() in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return True


def execute(cmd: str) -> tuple[int, str]:
    """Run through the user's shell, stream stdout, capture stderr for diagnosis."""
    print(f"{DIM}$ {cmd}{RESET}", flush=True)
    try:
        p = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE)
        _, err = p.communicate()
    except KeyboardInterrupt:
        return 130, ""
    err = (err or b"").decode("utf-8", errors="replace")
    if err:
        sys.stderr.write(err)
    return p.returncode, err


def run_entry(entry: dict, template_cmd: str, action: str = "ask") -> int:
    """Full flow for one chosen command. `template_cmd` is the key for self-heal memory."""
    cmd, notes = apply_heals(entry["cmd"])
    if notes:
        print(f"{GREEN}🩹 learned from a past failure:{RESET} also needs {', '.join(notes)}")

    if action == "ask":
        try:
            choice = input(f"{BOLD}[enter]{RESET} run · {BOLD}c{RESET} copy · {BOLD}p{RESET} print · "
                           f"{BOLD}q{RESET} quit > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        action = {"": "run", "r": "run", "c": "copy", "p": "print"}.get(choice, "quit")
    if action == "quit":
        return 0

    filled = fill(cmd)
    if filled is None:
        return 1
    store.bump_usage(template_cmd)

    if action == "print":
        print(filled)
        return 0
    if action == "run" and re.match(r"cd\s+\S", filled):
        # A child process can't change the parent shell's directory, so running it would do nothing.
        print(f"{DIM}cd only works in your own shell — paste it there.{RESET}")
        action = "copy"
    if action == "copy":
        print(f"{GREEN}copied{RESET}  {filled}" if copy_to_clipboard(filled) else filled)
        return 0

    level = risk.classify(filled, entry.get("desc", ""))
    level = max(level, entry.get("risk", risk.READ), key=[risk.READ, risk.WRITE, risk.DANGER].index)
    if not confirm(filled, level):
        print("cancelled")
        return 1

    code, err = execute(filled)
    if code == 0:
        return 0

    flags, positional = diagnose(err)
    if not (flags or positional):
        return code
    # Store against the template so the lesson applies next time, whatever values are used.
    new = store.add_heal(template_cmd, flags, positional)
    missing = ", ".join(flags + ([f"{positional} positional arg(s)"] if positional else []))
    print(f"\n{GREEN}🩹 self-heal:{RESET} it looks like the command needed {BOLD}{missing}{RESET}. "
          + ("I'll remember that." if new else "I already knew; filling it in now."))
    try:
        again = input("  retry with the missing parameters? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return code
    if again not in ("", "y", "yes"):
        return code
    # Keep the values the user already typed: only append what was missing.
    retry = filled
    for i in range(max(0, positional - len(PLACEHOLDER.findall(entry["cmd"])))):
        retry += f" <arg{i + 1}>"
    for f in flags:
        if not re.search(rf"(^|\s){re.escape(f)}(\s|=|$)", retry):
            retry += f" {f} <{f.lstrip('-')}>"
    retry = fill(retry)
    if retry is None or not confirm(retry, level):
        return code
    code, _ = execute(retry)
    return code
