"""Arrow-key picker with no dependencies (Windows console + POSIX terminals)."""
import os
import re
import shutil
import sys

from how.risk import BADGE

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

RESET, DIM, BOLD, CYAN, REV = "\033[0m", "\033[2m", "\033[1m", "\033[36m", "\033[7m"

if os.name == "nt":
    os.system("")  # turns on ANSI escape processing in the Windows console
    import msvcrt

    def read_key():
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
        return {"\r": "enter", "\x1b": "esc", "\x03": "esc"}.get(ch, ch)
else:
    import termios
    import tty

    def read_key():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                return {"[A": "up", "[B": "down"}.get(seq, "esc")
            return {"\r": "enter", "\n": "enter", "\x03": "esc"}.get(ch, ch)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _render(items, idx):
    lines = []
    for i, e in enumerate(items):
        color, mark = BADGE[e["risk"]]
        cmd = e["cmd"]
        if i == idx:
            lines.append(f" {CYAN}❯{RESET} {color}{mark}{RESET} {BOLD}{cmd}{RESET}")
            lines.append(f"     {e['desc']}")
            if e.get("why"):
                lines.append(f"     {DIM}why: {e['why']}{RESET}")
        else:
            lines.append(f"   {color}{mark}{RESET} {cmd}  {DIM}{e['desc']}{RESET}")
    lines.append(f"{DIM}  ↑/↓ move · enter select · 1-9 jump · q quit   "
                 f"\033[32m●\033[2m read-only \033[33m●\033[2m modifies \033[31m▲\033[2m destructive{RESET}")
    return lines


def pick(items):
    """Return the chosen entry, or None."""
    if not items:
        return None
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return _pick_numbered(items)
    idx, drawn = 0, 0
    sys.stdout.write("\033[?25l")  # hide cursor
    try:
        while True:
            if drawn:
                sys.stdout.write(f"\033[{drawn}F\033[J")  # move up and clear
            lines = _render(items, idx)
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()
            cols = max(shutil.get_terminal_size().columns, 20)
            drawn = sum(max(1, -(-len(_ANSI.sub("", l)) // cols)) for l in lines)
            k = read_key()
            if k in ("up", "k"):
                idx = (idx - 1) % len(items)
            elif k in ("down", "j", "\t"):
                idx = (idx + 1) % len(items)
            elif k.isdigit() and 1 <= int(k) <= len(items):
                idx = int(k) - 1
            elif k == "enter":
                return items[idx]
            elif k in ("esc", "q"):
                return None
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def _pick_numbered(items):
    for i, e in enumerate(items, 1):
        print(f"{i}. {e['cmd']}  — {e['desc']}")
    try:
        choice = input("pick #: ").strip()
    except EOFError:
        return None
    return items[int(choice) - 1] if choice.isdigit() and 1 <= int(choice) <= len(items) else None
