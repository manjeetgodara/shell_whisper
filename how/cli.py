"""how — type what you want in plain English, get the command.

  how docker apps on same network       search, pick with arrow keys, run
  how learn gh                          teach `how` every gh command from its --help
  how forget gh | how tools | how heals
"""
from __future__ import annotations

import argparse
import sys

from how import __version__, ai, learn, picker, risk, search, store

DIM, RESET, BOLD = "\033[2m", "\033[0m", "\033[1m"
SUBCOMMANDS = {"learn", "forget", "tools", "heals"}


def _out_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def cmd_learn(argv):
    p = argparse.ArgumentParser(prog="how learn", description="Learn a CLI tool from its --help output.")
    p.add_argument("tool")
    p.add_argument("--depth", type=int, default=3, help="how many subcommand levels to read (default 3)")
    a = p.parse_args(argv)
    print(f"reading `{a.tool} --help` recursively…")
    entries = learn.learn(a.tool, depth=a.depth)
    counts = {lvl: sum(e["risk"] == lvl for e in entries) for lvl in (risk.READ, risk.WRITE, risk.DANGER)}
    print(f"learned {BOLD}{len(entries)}{RESET} {a.tool} commands: "
          f"\033[32m{counts[risk.READ]} read-only{RESET}, \033[33m{counts[risk.WRITE]} modify{RESET}, "
          f"\033[31m{counts[risk.DANGER]} destructive{RESET}")
    for e in entries[:5]:
        print(f"  {DIM}{e['cmd']}  — {e['desc']}{RESET}")
    if len(entries) > 5:
        print(f"  {DIM}…try: how {a.tool} <what you want>{RESET}")
    return 0


def cmd_query(argv):
    p = argparse.ArgumentParser(prog="how", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", nargs="+", help="what you want to do, in plain English")
    p.add_argument("-n", type=int, default=7, help="number of suggestions")
    p.add_argument("--ai", dest="ai", action="store_true", default=None, help="force Claude ranking")
    p.add_argument("--no-ai", dest="ai", action="store_false", help="offline ranking only")
    p.add_argument("-p", "--print", action="store_true", help="print the best match and exit (for scripts)")
    p.add_argument("--version", action="version", version=f"how {__version__}")
    a = p.parse_args(argv)
    query = " ".join(a.query)

    results = search.rank(query, limit=max(a.n, 15))
    use_ai = ai.available() if a.ai is None else a.ai
    if use_ai:
        print(f"{DIM}asking Claude…{RESET}", end="\r", flush=True)
        smart = ai.suggest(query, results, n=a.n)
        print(" " * 20, end="\r")
        if smart:
            known = {e["cmd"]: e for e in results}
            results = [{**known.get(s["cmd"], {}), **s} for s in smart]
        elif a.ai:
            print(f"{DIM}(Claude unavailable — showing offline matches){RESET}")
    results = results[: a.n]
    for e in results:
        e["risk"] = e.get("risk") or risk.classify(e["cmd"], e.get("desc", ""))

    if not results:
        print(f"no idea yet. try other words, or teach me a tool: {BOLD}how learn <tool>{RESET}")
        return 1
    if a.print:
        print(results[0]["cmd"])
        return 0
    chosen = picker.pick(results)
    if not chosen:
        return 0
    from how import runner
    return runner.run_entry(chosen, chosen["cmd"])


def main(argv=None):
    _out_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 0
    head = argv[0]
    try:
        if head == "learn":
            return cmd_learn(argv[1:])
        if head == "forget" and len(argv) == 2:
            ok = learn.forget(argv[1])
            print(f"forgot {argv[1]}" if ok else f"never learned {argv[1]}")
            return 0 if ok else 1
        if head == "tools" and len(argv) == 1:
            data = store.learned()
            if not data:
                print("no tools learned yet. try: how learn gh")
            for tool, entries in sorted(data.items()):
                print(f"  {tool:<12} {len(entries)} commands")
            return 0
        if head == "heals" and len(argv) == 1:
            data = store.heals()
            if not data:
                print("no failures learned from yet.")
            for cmd, h in data.items():
                need = h["flags"] + ([f"{h['positional']} positional"] if h["positional"] else [])
                print(f"  {cmd}\n    {DIM}needs: {', '.join(need)}{RESET}")
            return 0
        if head == "--":
            argv = argv[1:]
        return cmd_query(argv)
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
