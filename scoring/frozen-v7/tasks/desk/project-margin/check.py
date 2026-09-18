"""The memo says the worst job is losing money.

The worst job (reference/notes.json "worst_job") must be tied to a loss. Sentences are split the way the grader splits
them (line breaks always end one). The loss may be stated

  * in a sentence naming the job, with a loss word (loss, losses, lost, loses, losing, loss-making, negative, deficit,
    shortfall, under water, in the red, below zero, unprofitable, overspent, cost more than) or a signed or bracketed
    negative figure ("-46,716.33", "-$46,716.33", "(46,716.33)");
  * in the sentence just before or after one naming the job, when that sentence names no other job
    ("Umber Ceramics Studio has no invoiced revenue yet. That leaves it $46,716.33 in the red.");
  * in the heading or lead-in line above a list or table that carries the job ("## Loss-making jobs" then
    "- Umber Ceramics Studio").

Whichever of these carries the claim must not say the job broke even, had no loss, or is not losing money.
Job names come from reference/job_margins.csv.
"""
import csv
import fnmatch
import glob
import json
import os
import re

_ABBREV = re.compile(r'\b(?:a\.m|p\.m|e\.g|i\.e|etc|vs|approx|dept|mr|mrs|ms|dr|st|ave|rd|blvd|inc|co|corp|ltd|llc|jr|sr|'
                     r'jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\.$', re.I)

LOSS = re.compile(r"\blos(s|ses|t|es|ing)\b|\bnegative\b|\bdeficits?\b|\bshortfalls?\b|\bunder\s?-?water\b|\bin the red\b|"
                  r"\bbelow zero\b|\bunprofitable\b|\bnot profitable\b|\bovers?pent\b|\bcost(s|ing)?\s+(us\s+)?more than\b|"
                  r"\bspent more than\b", re.I)
NEG_FIGURE = re.compile(r"(?<![\w$.,])[-−–]\$?\d|\$\s?[-−]\d|\(\s?\$?\d{1,3}(,\d{3})*\.\d+\s?\)|\(\s?\$?\d{1,3}(,\d{3})+\s?\)")
NONE = re.compile(r"\bbroke even\b|\bno (loss|losses)\b|(\bnot|n't)\s+(yet\s+)?(losing|a loss|loss-making|unprofitable|negative|"
                  r"in the red|under\s?-?water)\b", re.I)
ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s|^\s*\|")


def split_sentences(t):
    out = []
    for line in re.split(r"\n+", t):
        parts = []
        for x in re.split(r"(?<=[.!?])\s+", line):
            x = x.strip()
            if not x:
                continue
            if parts and _ABBREV.search(parts[-1]):
                parts[-1] = parts[-1] + " " + x
            else:
                parts.append(x)
        out.extend(parts)
    return out


def _find(ws, name):
    hits = sorted(glob.glob(os.path.join(ws, name))) or sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    if not hits:
        for base, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if d not in (".proto", ".codex", "node_modules", ".git")]
            hits += [os.path.join(base, f) for f in files if fnmatch.fnmatch(f.lower(), name)]
        hits.sort()
    return hits[0] if hits else None


def _lossy(s):
    return bool(LOSS.search(s) or NEG_FIGURE.search(s))


def check(ws, ref):
    name = "memo says the worst job is losing money"
    p = _find(ws, "memo.md")
    if not p:
        return [{"name": name, "passed": False, "detail": "memo.md not found"}]
    notes = json.load(open(os.path.join(ref, "notes.json"), encoding="utf-8"))
    with open(os.path.join(ref, "job_margins.csv"), encoding="utf-8") as f:
        jobs = [r["job"] for r in csv.DictReader(f) if r["code"].upper() != "ALL"]
    worst = notes["worst_job"]
    key = lambda job: re.compile(r"\b" + re.escape(job.split()[0]) + r"\b", re.I)
    worst_rx = key(worst)
    others = [key(j) for j in jobs if j != worst]
    names_other = lambda s: any(o.search(s) for o in others)
    text = open(p, encoding="utf-8", errors="replace").read()

    sents = split_sentences(text)
    for i, s in enumerate(sents):
        if not worst_rx.search(s):
            continue
        if _lossy(s) and not NONE.search(s):
            return [{"name": name, "passed": True, "detail": f"sentence: {s[:160]!r}"}]
        for j in (i - 1, i + 1):
            if 0 <= j < len(sents):
                n = sents[j]
                if _lossy(n) and not names_other(n) and not NONE.search(n) and not NONE.search(s):
                    return [{"name": name, "passed": True, "detail": f"adjacent sentences: {s[:100]!r} / {n[:100]!r}"}]

    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if not (worst_rx.search(ln) and ITEM.search(ln)) or NONE.search(ln):
            continue
        k = i - 1
        while k >= 0 and (not lines[k].strip() or ITEM.search(lines[k]) or re.match(r"^\s{2,}\S", lines[k])):
            k -= 1
        if k >= 0 and _lossy(lines[k]) and not NONE.search(lines[k]):
            return [{"name": name, "passed": True, "detail": f"list under {lines[k].strip()[:80]!r}: {ln.strip()[:80]!r}"}]
    return [{"name": name, "passed": False, "detail": f"no sentence, neighbouring sentence or list heading ties {worst} to a loss"}]
