"""The parking lot pole lights were dropped from the job, so the proposal must not price them.

Mentioning them is allowed (an exclusions line such as "parking lot poles are not included" is normal in a proposal);
pricing them is not. The check fails when a line or sentence that names the poles carries a dollar figure, or when the
pole retrofit's 2026 unit price or its five-pole amount appears anywhere. Figures come from reference/notes.json.
"""
import glob
import json
import os
import re

POLE = re.compile(r"(\bpoles?\b|parking[\s-]+lot\s+light)", re.I)
MONEY = re.compile(r"\$\s?\d|\b\d[\d,]*\.\d{2}\b")
NUM = re.compile(r"\(?-?[$€£]?\s?\d[\d,]*(?:\.\d+)?\)?")


def _nums(text):
    out = []
    for mm in NUM.finditer(text):
        try:
            out.append(float(re.sub(r"[^0-9.]", "", mm.group(0))))
        except ValueError:
            pass
    return out


def check(ws, ref):
    name = "pole lights dropped"
    hits = sorted(glob.glob(os.path.join(ws, "proposal.md"))) or sorted(
        h for h in glob.glob(os.path.join(ws, "**", "proposal.md"), recursive=True) if "/.proto" not in h and "/.codex" not in h)
    if not hits:
        return [{"name": name, "passed": False, "detail": "proposal.md not found"}]
    try:
        notes = json.load(open(os.path.join(ref, "notes.json")))
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"reference unreadable: {e}"}]
    text = open(hits[0], encoding="utf-8", errors="replace").read()
    pieces = [p for p in re.split(r"(?<=[.!?])\s+|\n+", text) if p.strip()]
    priced = [p for p in pieces if POLE.search(p) and MONEY.search(p)]
    nums = _nums(text)
    figures = [f for f in (notes["pole_unit"], notes["pole_amount"]) if any(abs(v - f) < 0.005 for v in nums)]
    ok = not priced and not figures
    if ok:
        detail = "no pole pricing"
    elif priced:
        detail = f"poles priced: {priced[0][:120]!r}"
    else:
        detail = f"pole figures present: {figures}"
    return [{"name": name, "passed": ok, "detail": detail}]
