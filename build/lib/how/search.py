"""Local ranking: BM25 over command + description + keywords, with synonyms and history boost."""
import math
import re
from collections import Counter

from how import kb, risk, store

STOP = set("a an the to of in on for with my me i how do can is are be it this that and or all from by "
           "what which show me want need using use get".split()) - {"get", "show"}

# Query word -> words it should also match.
SYNONYMS = {
    "delete": "remove rm prune destroy", "remove": "delete rm prune", "kill": "stop terminate",
    "start": "run up launch", "launch": "run start", "list": "ls show get", "see": "show list view inspect",
    "logs": "log output", "log": "logs", "shell": "exec sh bash", "enter": "exec shell",
    "same": "together shared", "talk": "communicate network connect", "space": "disk size df",
    "pr": "pull request", "issue": "issues", "repo": "repository", "undo": "reset revert restore rollback",
    "port": "ports", "copy": "cp", "find": "search grep", "container": "containers", "image": "images",
    "network": "networks", "restart": "reboot", "k8s": "kubectl kubernetes", "kubernetes": "kubectl",
    "branch": "branches", "clean": "prune cleanup", "free": "prune clean", "running": "ps",
}


def stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(text: str):
    return [stem(w) for w in re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower()) if w not in STOP]


def expand(query_tokens):
    out = list(query_tokens)
    for t in query_tokens:
        for k, v in SYNONYMS.items():
            if stem(k) == t:
                out += [stem(x) for x in v.split()]
    return out


def all_entries():
    seen, out = set(), []
    for e in list(store.learned_entries()) + list(kb.entries()):
        if e["cmd"] not in seen:
            seen.add(e["cmd"])
            out.append(e)
    return out


def rank(query: str, limit: int = 8, entries=None):
    entries = entries if entries is not None else all_entries()
    q_raw = tokens(query)
    if not q_raw:
        return []
    q = expand(q_raw)
    docs = [tokens(f'{e["cmd"]} {e["cmd"]} {e["desc"]} {e.get("tags", "")}') for e in entries]
    n = len(docs)
    avgdl = sum(map(len, docs)) / max(n, 1)
    df = Counter(t for d in docs for t in set(d))
    usage = store.usage()
    tools_in_query = {t for t in q_raw}
    k1, b = 1.4, 0.6

    scored = []
    for e, d in zip(entries, docs):
        tf = Counter(d)
        s = 0.0
        for t in set(q):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            weight = 1.0 if t in q_raw else 0.45  # synonyms count less than the user's own words
            s += weight * idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        if s <= 0:
            continue
        if stem(e["tool"].lower()) in tools_in_query:
            s *= 1.6  # user named the tool
        s += 0.3 * math.log1p(usage.get(e["cmd"], 0))
        scored.append((s, e))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, e in scored[:limit]:
        e = dict(e)
        e["risk"] = e.get("risk") or risk.classify(e["cmd"], e["desc"])
        out.append(e)
    return out
