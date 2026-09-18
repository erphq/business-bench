"""woocommerce-orders-to-journal: journals balance.

Every journal in journal.csv has total debits equal to total credits (to the cent), the whole file's debits equal
its credits, no amount is negative, no line carries both a debit and a credit, and the file covers at least the
reference's journals (so an empty or truncated file cannot balance its way to a pass).
"""
from __future__ import annotations
import csv, glob, io, os, re


def _norm_col(c) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _find(ws: str, name: str):
    hits = sorted(glob.glob(os.path.join(ws, name))) or sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def read_rows(path: str) -> list[dict]:
    if path.lower().endswith((".xlsx", ".xlsm")):
        import pandas as pd
        df = pd.read_excel(path, dtype=str).fillna("")
        return [{_norm_col(k): str(v) for k, v in rec.items()} for rec in df.to_dict("records")]
    text = open(path, "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    return [{_norm_col(k): (v or "") for k, v in rec.items() if k is not None} for rec in csv.DictReader(io.StringIO(text))]


def amount(v) -> float | None:
    s = str(v or "").strip()
    if not s:
        return 0.0
    neg = s.startswith("(") or s.startswith("-")
    t = re.sub(r"[^0-9.]", "", s)
    if not t:
        return None
    try:
        x = float(t)
    except ValueError:
        return None
    return -x if neg else x


def check(ws: str, ref: str) -> list[dict]:
    name = "journals balance"
    p = _find(ws, "journal.csv")
    if not p:
        return [{"name": name, "passed": False, "detail": "journal.csv not found"}]
    try:
        rows = read_rows(p)
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"unreadable: {e}"}]
    ref_journals = {r.get("journal_no", "").strip().lower() for r in read_rows(os.path.join(ref, "journal.csv"))}
    sums: dict[str, list[float]] = {}
    problems = []
    for i, row in enumerate(rows, 2):
        jn = row.get("journal_no", "").strip().lower()
        dr, cr = amount(row.get("debit")), amount(row.get("credit"))
        if dr is None or cr is None:
            problems.append(f"line {i}: unreadable amount"); continue
        if dr < 0 or cr < 0:
            problems.append(f"line {i}: negative amount")
        if dr and cr:
            problems.append(f"line {i}: both debit and credit")
        s = sums.setdefault(jn, [0.0, 0.0])
        s[0] += dr; s[1] += cr
    unbalanced = [f"{j} dr {d:.2f} cr {c:.2f}" for j, (d, c) in sorted(sums.items()) if abs(d - c) > 0.005]
    tot_dr = sum(d for d, _ in sums.values()); tot_cr = sum(c for _, c in sums.values())
    missing = sorted(ref_journals - set(sums))
    ok = rows and not problems and not unbalanced and abs(tot_dr - tot_cr) <= 0.005 and not missing
    detail = (f"{len(sums)} journals balance; total debits {tot_dr:.2f} = credits {tot_cr:.2f}" if ok else
              "; ".join(filter(None, [f"{len(unbalanced)} unbalanced: {unbalanced[:4]}" if unbalanced else "",
                                      f"file debits {tot_dr:.2f} vs credits {tot_cr:.2f}" if abs(tot_dr - tot_cr) > 0.005 else "",
                                      f"missing journals {missing[:6]}" if missing else "", "; ".join(problems[:4]),
                                      "no rows" if not rows else ""])))
    return [{"name": name, "passed": bool(ok), "detail": detail}]
