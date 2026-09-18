"""Every vendor keeps a usable phone: 10 digits, or 11 with a leading 1, matching the reference digits."""
import csv, glob, os, re

def _digits(s):
    d = re.sub(r"\D", "", s or "")
    return d[1:] if len(d) == 11 and d.startswith("1") else d

def check(ws, ref):
    paths = glob.glob(os.path.join(ws, "vendors.csv"))
    if not paths:
        return [{"name": "phone carried over", "passed": False, "detail": "vendors.csv not found"}]
    def load(p):
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        return {(r.get("email") or r.get("Email") or "").strip().lower(): r for r in rows}
    out, truth = load(paths[0]), load(os.path.join(ref, "vendors.csv"))
    bad = []
    for email, t in truth.items():
        got = out.get(email)
        if got is None:
            bad.append(f"{email}: missing"); continue
        phone = next((v for k, v in got.items() if k and k.strip().lower() == "phone"), "")
        if _digits(phone) != _digits(t["phone"]):
            bad.append(f"{email}: {phone!r}")
    return [{"name": "phone carried over", "passed": not bad, "detail": "; ".join(bad[:6]) if bad else f"{len(truth)} phones match"}]
