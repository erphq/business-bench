"""Each customer's reminder carries its own facts, and only the customers who should get one do.

Files are matched to customers by the customer's first name word in the file name, case- and punctuation-insensitively
(reminders/Umber_Ceramics.md, reminders/umber-ceramics.md). An invoice is found by its digits; its balance and days past
due must sit on its own line or the few lines after it, before the next invoice. Days past due are accepted within one day.
Credit hold counts as mentioned when a sentence names a hold or COD without a negation. Expected values come from
reference/notes.json, so nothing here is pinned to a seed.
"""
import glob
import json
import os
import re

NUM = re.compile(r"\(?-?[$€£]?\s?\d[\d,]*(?:\.\d+)?\)?")
HOLD = re.compile(r"(credit hold|on hold|\bhold\b|\bc\.?o\.?d\b|cash on delivery)", re.I)
NEG = re.compile(r"\b(not|no|no longer|never|won't|will not|isn't|aren't|without)\b", re.I)
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def _nums(text):
    out = []
    for m in NUM.finditer(text):
        try:
            out.append(float(re.sub(r"[^0-9.\-]", "", m.group(0)).lstrip("-") or "x"))
        except ValueError:
            pass
    return out


def _has(nums, want, tol):
    return any(abs(v - want) <= tol for v in nums)


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _holds(text):
    return [s for s in _sentences(text) if HOLD.search(s) and not NEG.search(s)]


def _date_re(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    mon = MONTHS[m - 1]
    return re.compile(rf"({mon}|{mon[:3]}\.?|{mon[:4]}\.?)\s+0?{d}\b|\b0?{d}(st|nd|rd|th)?\s+(of\s+)?({mon}|{mon[:3]})\b|\b0?{m}/0?{d}\b|\b{y}-{m:02d}-{d:02d}\b", re.I)


def _files(ws):
    base = os.path.join(ws, "reminders")
    if not os.path.isdir(base):
        hits = [p for p in glob.glob(os.path.join(ws, "**", "reminders"), recursive=True) if os.path.isdir(p) and "/.proto" not in p and "/.codex" not in p]
        base = hits[0] if hits else base
    return sorted(p for p in glob.glob(os.path.join(base, "*")) if os.path.isfile(p) and p.lower().endswith((".md", ".txt", ".markdown")))


def check(ws, ref):
    try:
        notes = json.load(open(os.path.join(ref, "notes.json")))
    except Exception as e:
        return [{"name": "per-customer reminder facts", "passed": False, "detail": f"reference unreadable: {e}"}]
    custs = notes["customers"]
    files = _files(ws)
    by_cust = {}
    for p in files:
        stem = re.sub(r"[^a-z0-9]", "", os.path.basename(p).lower())
        for c in custs:
            if c["key"] in stem:
                by_cust.setdefault(c["label"], p)
    texts = {k: open(p, encoding="utf-8", errors="replace").read() for k, p in by_cust.items()}
    res = []

    want = {c["label"] for c in custs if c["gets_file"]}
    got = set(by_cust)
    missing = sorted(c["name"] for c in custs if c["label"] in want - got)
    extra = sorted(c["name"] for c in custs if c["label"] in got - want)
    res.append({"name": "one reminder per customer with a past-due balance", "passed": not missing and not extra,
                "detail": f"{len(got & want)}/{len(want)} present; missing={missing} unexpected={extra}"})

    all_inv = {n: c["label"] for c in custs for n in c["all_invoices"]}
    bad_lines, bad_total, bad_plan, bad_hold, bad_excl = [], [], [], [], []
    for c in custs:
        k = c["label"]
        if k not in texts:
            continue
        t = texts[k]
        lines = t.splitlines()
        digits = lambda no: re.compile(rf"(?<!\d){no.split('-')[-1]}(?!\d)")
        own = [digits(n) for n in c["all_invoices"]]
        # invoices belonging to someone else, or excluded from this customer's reminder
        for n, owner in all_inv.items():
            if owner != k and digits(n).search(t):
                bad_excl.append(f"{c['name']} mentions {n} of another customer")
        for n in c["excluded"]:
            if digits(n).search(t):
                bad_excl.append(f"{c['name']} mentions excluded {n}")
        if c["kind"] == "plan":
            if not _has(_nums(t), float(c["installment"]), 0.011):
                bad_plan.append(f"{c['name']}: installment {c['installment']:,.2f} not stated")
            if not _date_re(c["next_due"]).search(t):
                bad_plan.append(f"{c['name']}: next installment date {c['next_due']} not stated")
            listed = [n["no"] for n in c["past_due"] if digits(n["no"]).search(t)]
            if listed:
                bad_plan.append(f"{c['name']}: plan reminder lists invoices {listed}")
            if _holds(t):
                bad_hold.append(f"{c['name']} (payment plan) mentions credit hold: {_holds(t)[0][:80]!r}")
            continue
        for inv in c["past_due"]:
            rx = digits(inv["no"])
            idx = next((i for i, ln in enumerate(lines) if rx.search(ln)), None)
            if idx is None:
                bad_lines.append(f"{c['name']}: {inv['no']} missing"); continue
            end = idx + 1
            while end < len(lines) and end < idx + 6 and not any(o.search(lines[end]) for o in own):
                end += 1
            window = "\n".join(lines[idx:end])
            nums = _nums(window.replace(inv["no"].split("-")[-1], " "))
            if not _has(nums, inv["balance"], 0.011):
                bad_lines.append(f"{c['name']}: {inv['no']} balance {inv['balance']:,.2f} not with it")
            if not _has(nums, inv["days"], 1.0):
                bad_lines.append(f"{c['name']}: {inv['no']} {inv['days']} days past due not with it")
        if not _has(_nums(t), c["total"], 0.011):
            bad_total.append(f"{c['name']}: total {c['total']:,.2f}")
        hs = _holds(t)
        if c["hold"] and not hs:
            bad_hold.append(f"{c['name']}: no credit hold paragraph")
        if not c["hold"] and hs:
            bad_hold.append(f"{c['name']}: credit hold mentioned but nothing is over 60 days: {hs[0][:80]!r}")

    res.append({"name": "each standard reminder lists its past-due invoices with balance and days past due", "passed": not bad_lines,
                "detail": "; ".join(bad_lines[:6]) or "all invoice lines carry their own balance and days"})
    res.append({"name": "each standard reminder states its total past due", "passed": not bad_total,
                "detail": "missing " + "; ".join(bad_total[:6]) if bad_total else "totals stated"})
    res.append({"name": "payment plan reminders give the next installment and list no invoices", "passed": not bad_plan,
                "detail": "; ".join(bad_plan[:6]) or "plan reminders correct"})
    res.append({"name": "credit hold paragraph only where an invoice is more than 60 days past due", "passed": not bad_hold,
                "detail": "; ".join(bad_hold[:6]) or "credit hold placed correctly"})
    res.append({"name": "disputed, not-yet-due, paid and other customers' invoices left out", "passed": not bad_excl,
                "detail": "; ".join(bad_excl[:6]) or "no stray invoices"})
    return res
