"""Resolve the "(checks: A; B)" references in task.yaml trap sentences to the task's check names.

Trap sentences cite checks by a short form of their name ("Cedar Point cost" for "Cedar Point cost
(unbilled time in, credits netted)", "memo names both loss-makers" for "memo names both loss-making jobs").
A citation resolves to the one check whose name covers every word of it, comparing words by their first
three letters so "makers" meets "making". Anything else is reported as unresolved or ambiguous rather than
guessed. Pure functions, linear in the number of traps x checks of one task.
"""
from __future__ import annotations

import re

_CITE = re.compile(r"\(\s*checks?\s*:\s*([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$", re.I)
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "and", "in", "on", "to", "for", "is", "at", "by", "with"}


def _stems(text: str) -> list[str]:
    return [w[:3] for w in _WORD.findall(text.lower()) if w not in _STOP]


def citations(trap_text: str) -> list[str]:
    """The check citations at the end of one trap sentence, in order. [] when the sentence cites none."""
    m = _CITE.search(trap_text.strip())
    if not m:
        return []
    return [c.strip() for c in m.group(1).split(";") if c.strip()]


def resolve(cite: str, check_names: list[str]) -> tuple[str | None, str]:
    """(check name, status) where status is 'ok', 'unresolved' or 'ambiguous'."""
    want = _stems(cite)
    if not want:
        return None, "unresolved"
    same = [n for n in check_names if n.lower() == cite.lower()]
    if len(same) == 1:
        return same[0], "ok"
    exact = [n for n in check_names if n.lower().startswith(cite.lower())]
    if len(exact) == 1:
        return exact[0], "ok"
    hits = []
    for n in check_names:
        have = set(_stems(n))
        if all(w in have for w in want):
            hits.append(n)
    if len(hits) == 1:
        return hits[0], "ok"
    return None, "ambiguous" if hits else "unresolved"


def trap_links(task: dict) -> list[dict]:
    """One record per trap sentence: its text, its citations, and what each resolves to."""
    names = [c.get("name", c.get("type", "")) for c in task.get("checks") or []]
    out = []
    for i, text in enumerate(task.get("traps") or []):
        cites = []
        for c in citations(text):
            name, status = resolve(c, names)
            part = None
            for sep in (":", ",", " - "):
                if status == "ok" or sep not in c:
                    continue
                # "page structure: top donors" cites one assertion inside a multi-part check;
                # "row count, 62 activities" adds the expected value after the check's name
                head, rest = (x.strip() for x in c.split(sep, 1))
                h_name, h_status = resolve(head, names)
                if h_status == "ok":
                    name, status, part = h_name, h_status, rest
            cites.append({"cite": c, "check": name, "part": part, "status": status})
        out.append({"index": i, "text": text, "cites": cites})
    return out
