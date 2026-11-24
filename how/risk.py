"""Infer how dangerous a command is from the command itself."""
import re

READ, WRITE, DANGER = "read-only", "modifies", "destructive"

_DANGER_WORDS = {
    "delete", "del", "remove", "rm", "rmi", "rmdir", "prune", "purge", "destroy",
    "drop", "kill", "killall", "pkill", "wipe", "erase", "truncate", "uninstall",
    "reset", "revoke", "terminate", "shred", "format", "mkfs", "dd", "clean",
    "archive", "close", "down", "unpublish", "deprecate", "taint", "drain",
}
_WRITE_WORDS = {
    "create", "add", "new", "set", "edit", "update", "upgrade", "push", "install",
    "start", "stop", "restart", "run", "exec", "merge", "rebase", "commit", "apply",
    "build", "deploy", "publish", "rename", "mv", "move", "cp", "copy", "chmod",
    "chown", "tag", "connect", "disconnect", "login", "logout", "enable", "disable",
    "write", "sync", "pull", "checkout", "switch", "fork", "clone", "import", "mkdir",
    "touch", "scale", "rollout", "patch", "label", "annotate", "pause", "unpause",
    "reopen", "comment", "review", "approve", "transfer", "cherry-pick", "stash",
    "init", "config", "configure", "up", "attach", "cordon", "upload", "download",
}
_READ_WORDS = {
    "list", "ls", "get", "show", "view", "status", "describe", "inspect", "logs",
    "log", "help", "version", "search", "diff", "info", "top", "ps", "cat", "find",
    "grep", "check", "whoami", "history", "stats", "browse", "explain", "events",
    "head", "tail", "less", "du", "df", "which", "where", "env", "watch", "blame",
    "lsof", "netstat", "ss", "ping", "nslookup", "dig", "free", "uptime", "journalctl",
    "findstr", "port", "whois", "traceroute", "tree", "pwd", "wc", "sort", "stat",
}
_DANGER_FLAGS = re.compile(
    r"(^|\s)(--force\b|--hard\b|-rf\b|-fr\b|--all\b.*\b(rm|prune|delete)|"
    r"--delete\b|--prune\b|--no-preserve-root\b|-D\b|--purge\b|--volumes\b)"
)
_DANGER_PATTERNS = re.compile(r">\s*/dev/sd|:\(\)\s*\{|\bsudo\s+rm\b|\bgit\s+push\b.*--force")
_CURL_WRITES = re.compile(r"\s(-X|--request|-d|--data\S*|-F|--form|-T)(\s|=|$)")


def classify(cmd: str, description: str = "") -> str:
    words = re.findall(r"[a-z][a-z-]*", cmd.lower())
    # Skip the tool name itself (e.g. `rm` IS the tool, but `docker` isn't a verb).
    verbs = words[1:] if len(words) > 1 else words
    if _DANGER_PATTERNS.search(cmd) or _DANGER_FLAGS.search(cmd):
        return DANGER
    if re.search(r"\breset\s+--soft\b", cmd):
        return WRITE  # moves the branch pointer only; files are untouched
    if words and words[0] == "curl":
        return WRITE if _CURL_WRITES.search(cmd) else READ
    if words and words[0] in {"rm", "rmdir", "shred", "dd", "mkfs", "kill", "killall", "pkill"}:
        return DANGER
    if any(v in _DANGER_WORDS for v in verbs):
        return DANGER
    if any(v in _WRITE_WORDS for v in verbs) or (words and words[0] in _WRITE_WORDS):
        return WRITE
    if any(v in _READ_WORDS for v in verbs) or (words and words[0] in _READ_WORDS):
        return READ
    # Fall back to the description's wording.
    d = description.lower()
    if re.search(r"\b(delete|remove|destroy|permanently|prune|kill)\b", d):
        return DANGER
    if re.search(r"\b(create|update|modify|change|set|add|start|stop|write)\b", d):
        return WRITE
    if re.search(r"\b(list|show|display|view|print|get)\b", d):
        return READ
    return WRITE  # unknown: be cautious, but not alarmist


BADGE = {READ: ("\033[32m", "●"), WRITE: ("\033[33m", "●"), DANGER: ("\033[31m", "▲")}
