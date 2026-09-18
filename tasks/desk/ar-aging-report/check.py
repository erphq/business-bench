"""The memo names each of the three customers with the most past due on 31 August, each with its past-due amount.

A name and its amount must share one sentence or one line (a list item or a table row), so a memo that lists every
customer without the right figures, or ranks by total balance, does not pass. Amounts are accepted within 0.5%
($56,977.67, 56977.67, $56,978) or written in thousands within 1% ($57.0k). The expected customers and figures come
from reference/notes.json, so nothing here is pinned to a seed.
"""
import glob
import json
import os
import re

NUM = re.compile(r"\(?-?\$?\s?(\d[\d,]*(?:\.\d+)?)\s?(k|K|thousand)?\b")


def _key(name):
    words = re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split()
    if words and words[0] == "the":
        words = words[1:]
    return " ".join(words[:2])


def _norm(text):
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())


def _numbers(text):
    out = []
    for m in NUM.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.append((v * 1000, 0.01) if m.group(2) else (v, 0.005))
    return out


def check(ws, ref):
    name = "memo names the top three past-due customers"
    hits = sorted(glob.glob(os.path.join(ws, "memo.md"))) or sorted(glob.glob(os.path.join(ws, "**", "memo.md"), recursive=True))
    if not hits:
        return [{"name": name, "passed": False, "detail": "memo.md not found"}]
    try:
        top = json.load(open(os.path.join(ref, "notes.json")))["top3"]
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"reference unreadable: {e}"}]
    text = open(hits[0], encoding="utf-8", errors="replace").read()
    pieces = [p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9*#|-])|\n+", text) if p.strip()]
    results = []
    for t in top:
        key, want = _key(t["customer"]), float(t["past_due"])
        ok = False
        for piece in pieces:
            if key not in _norm(piece):
                continue
            if any(abs(v - want) <= max(want * tol, 1.0) for v, tol in _numbers(piece)):
                ok = True
                break
        results.append({"name": f"{name}: {t['customer']}", "passed": ok,
                        "detail": f"found with ${want:,.2f}" if ok else f"no sentence or line names {t['customer']} with ${want:,.2f} past due"})
    return results
