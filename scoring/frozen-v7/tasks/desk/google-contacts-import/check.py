"""google-contacts-import custom checks.

phones typed: for every contact (keyed on Last Name), the (label, number) pairs across Phone 1..3 equal the
reference pairs, whatever slot each pair sits in. Numbers compare on digits (a leading 1 is ignored), labels
case-insensitively. Every multi-number, labelled or wrapped-line contact is inside this exact comparison.

notes carried and names clean: every fragment the reference puts in Notes (the Notes column, bracketed
remarks, instructions typed in the phone cell, wrapped-line notes) appears in that contact's Notes, and no
First/Middle/Last Name cell carries brackets, digits or a comma.
"""
from __future__ import annotations
import csv, glob, io, json, os, re


def _norm_col(c) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _find(ws: str, name: str):
    hits = sorted(glob.glob(os.path.join(ws, name))) or sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def _rows(path: str) -> list[dict]:
    if path.lower().endswith((".xlsx", ".xlsm")):
        import pandas as pd
        df = pd.read_excel(path, dtype=str).fillna("")
        return [{_norm_col(k): str(v) for k, v in rec.items()} for rec in df.to_dict("records")]
    text = open(path, "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    return [{_norm_col(k): (v or "") for k, v in rec.items() if k is not None} for rec in csv.DictReader(io.StringIO(text))]


def _digits(v: str) -> str:
    d = re.sub(r"\D", "", v or "")
    return d[1:] if len(d) == 11 and d.startswith("1") else d


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def check(ws: str, ref: str) -> list[dict]:
    names = ["phones typed", "notes carried and names clean"]
    p = _find(ws, "google_contacts.csv")
    if not p:
        return [{"name": n, "passed": False, "detail": "google_contacts.csv not found"} for n in names]
    try:
        rows = _rows(p)
    except Exception as e:  # unreadable deliverable
        return [{"name": n, "passed": False, "detail": f"unreadable: {e}"} for n in names]
    truth = json.load(open(os.path.join(ref, "truth.json")))
    by_last = {}
    for row in rows:
        by_last.setdefault(row.get("last_name", "").strip().lower(), row)

    bad_ph = []
    for last, pairs in truth["phones"].items():
        row = by_last.get(last.lower())
        if row is None:
            bad_ph.append(f"{last}: missing"); continue
        got = sorted((row.get(f"phone_{i}_label", "").strip().lower(), _digits(row.get(f"phone_{i}_value", "")))
                     for i in (1, 2, 3) if _digits(row.get(f"phone_{i}_value", "")))
        want = sorted((lab.lower(), dig) for lab, dig in pairs)
        if got != want:
            bad_ph.append(f"{last}: {got} != {want}")
    ok_ph = not bad_ph
    out = [{"name": names[0], "passed": ok_ph,
            "detail": (f"{len(truth['phones'])} contacts match" if ok_ph else f"{len(bad_ph)} wrong: " + " | ".join(bad_ph[:4]))}]

    bad_notes, bad_names = [], []
    for last, frags in truth["notes"].items():
        row = by_last.get(last.lower())
        if row is None:
            bad_notes.append(f"{last}: missing"); continue
        have = _squash(row.get("notes", ""))
        miss = [f for f in frags if _squash(f) not in have]
        if miss:
            bad_notes.append(f"{last}: missing {miss}")
    for row in rows:
        for c in ("first_name", "middle_name", "last_name"):
            v = row.get(c, "")
            if re.search(r"[()\[\]0-9,]", v):
                bad_names.append(f"{c}={v!r}")
    ok = not bad_notes and not bad_names
    detail = "all note fragments present, names clean" if ok else "; ".join((bad_notes[:4] + bad_names[:4]))
    out.append({"name": names[1], "passed": ok, "detail": detail})
    return out
