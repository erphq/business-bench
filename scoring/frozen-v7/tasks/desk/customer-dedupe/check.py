"""Custom grader for customer-dedupe: phone numbers carried over per person.

Keyed by Email (strip+lower). Phones compare on digits only, and an 11-digit
number with a leading 1 counts the same as its 10-digit form, so both
"(415) 555-0142" and "+1 415 555 0142" are accepted. Blank must stay blank.
At least 95% of the reference people must match, and every planted blank-phone duplicate
must keep the non-blank phone (exact).
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd


def _norm_col(c) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _find(ws: str, name: str):
    hits = sorted(glob.glob(os.path.join(ws, name)))
    if not hits:
        hits = sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def _read(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(path, dtype=str)
    else:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding_errors="replace")
    df.columns = [_norm_col(c) for c in df.columns]
    return df.fillna("")


def _phone(v) -> str:
    d = re.sub(r"\D", "", str(v))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d


def _k(v) -> str:
    return str(v).strip().lower()


def _name_tokens(first, last) -> tuple:
    toks = re.findall(r"[a-z]+", f"{first} {last}".lower())
    return tuple(sorted(t for t in toks if len(t) > 1))  # middle initials may sit in either column


def check_name_split(ws: str, ref: str) -> dict:
    """The template has First Name and Last Name; a file that leaves Last Name blank on most rows,
    or that puts other people's names on a person, is not an import an owner would accept. Casing
    is out of scope (the owner's email says so); the split and the tokens are graded leniently."""
    name = "first and last name split populated (>=90% rows, tokens match the reference)"
    p = _find(ws, "hubspot_import.csv")
    if not p:
        return {"name": name, "passed": False, "detail": "no hubspot_import.csv in workspace"}
    df = _read(p)
    for c in ("email", "first_name", "last_name"):
        if c not in df.columns:
            return {"name": name, "passed": False, "detail": f"column {c!r} missing; have {list(df.columns)}"}
    rdf = _read(os.path.join(ref, "hubspot_import.csv"))
    rmap = {_k(r["email"]): r for r in rdf.to_dict("records")}
    rows = [r for r in df.to_dict("records") if _k(r["email"]) in rmap]
    if not rows:
        return {"name": name, "passed": False, "detail": "no rows share an email with the reference"}
    split = sum(1 for r in rows if str(r["first_name"]).strip() and str(r["last_name"]).strip())
    match = sum(1 for r in rows if _name_tokens(r["first_name"], r["last_name"]) == _name_tokens(rmap[_k(r["email"])]["first_name"], rmap[_k(r["email"])]["last_name"]))
    ok = split >= 0.9 * len(rows) and match >= 0.9 * len(rows)
    return {"name": name, "passed": ok, "detail": f"{split}/{len(rows)} rows have both names, {match}/{len(rows)} match the reference tokens (need 90% each)"}


def check(ws: str, ref: str) -> list[dict]:
    return check_phones(ws, ref) + [check_name_split(ws, ref)]


def check_phones(ws: str, ref: str) -> list[dict]:
    name = "phone numbers match by email (>=95%, 10 or 11 digits)"
    p = _find(ws, "hubspot_import.csv")
    if not p:
        return {"name": name, "passed": False, "detail": "no hubspot_import.csv in workspace"}
    df = _read(p)
    for c in ("email", "phone_number"):
        if c not in df.columns:
            return {"name": name, "passed": False, "detail": f"column {c!r} missing; have {list(df.columns)}"}
    rdf = _read(os.path.join(ref, "hubspot_import.csv"))
    gmap = {_k(r["email"]): r for r in df.to_dict("records")}
    total = hits = 0
    wrong: list[str] = []
    for r in rdf.to_dict("records"):
        k = _k(r["email"])
        total += 1
        g = gmap.get(k)
        ok = g is not None and _phone(g.get("phone_number", "")) == _phone(r.get("phone_number", ""))
        hits += ok
        if not ok:
            wrong.append(k)
    acc = hits / total if total else 0.0
    out = [{"name": name, "passed": acc >= 0.95,
            "detail": f"{hits}/{total} = {acc:.3f}; wrong={wrong[:8]}"}]

    # The planted trap: people whose duplicate rows include a blank phone must keep the
    # non-blank one. Derived from the source sheet itself, so it holds for any seed, and
    # exact, so the 95% floor above cannot absorb a first-row-wins dedupe.
    src = _find(os.path.join(os.path.dirname(os.path.abspath(ref)), "workspace"), "customers.xlsx") \
        or _find(ws, "customers.xlsx")
    trap_name = "blank-phone duplicates keep the non-blank phone"
    if src:
        try:
            raw = pd.read_excel(src, header=None, dtype=str).fillna("")
            hdr = next(i for i, row in raw.iterrows() if any(re.search(r"e-?mail", str(v), re.I) for v in row))
            sdf = raw.iloc[hdr + 1:].copy(); sdf.columns = [_norm_col(c) for c in raw.iloc[hdr]]
            ecol = next(c for c in sdf.columns if re.search(r"e_?mail", c)); pcol = next(c for c in sdf.columns if "phone" in c)
            groups: dict[str, list[str]] = {}
            for e, ph in zip(sdf[ecol], sdf[pcol]):
                k = _k(e)
                if k and k not in ("n/a", "-", "none"):
                    groups.setdefault(k, []).append(_phone(ph))
            traps = {k: next(x for x in v if x) for k, v in groups.items()
                     if len(v) >= 2 and any(not x for x in v) and any(x for x in v)}
            bad = [k for k, want in sorted(traps.items()) if _phone((gmap.get(k) or {}).get("phone_number", "")) != want]
            out.append({"name": trap_name, "passed": bool(traps) and not bad,
                        "detail": f"{len(traps) - len(bad)}/{len(traps)} kept the non-blank phone" + (f"; lost: {bad}" if bad else "")})
        except Exception as e:
            out.append({"name": trap_name, "passed": False, "detail": f"grader error: {type(e).__name__}: {e}"})
    return out
