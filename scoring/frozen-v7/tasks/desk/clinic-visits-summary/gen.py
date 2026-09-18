#!/usr/bin/env python3
"""clinic-visits-summary: visits per provider per month and the no-show rate for a physio clinic.

    python gen.py [--seed N] [--naive DIR]

Business: a three-room physical therapy clinic whose scheduler was replaced in February, so the Q1
export carries both systems' wording for the same statuses and the providers' names in four spellings.

Traps (each caught by a check, see task.yaml):
  * one provider appears under four spellings, another under two    (checks: merged provider visits; merged provider quarter visits)
  * "Arrived" and "Completed" are the two systems' words for a kept visit (checks: clinic total visits; merged provider visits)
  * walk-ins are visits but were never on the book, so they are out of the no-show rate (checks: clinic total visits; no-show rates)
  * cancellations are not no-shows and not visits; rescheduled rows are the old slot (checks: no-show count; no-show rates)
  * the cancellation-fee billing export looks like a visit list and is not one (check: clinic total visits)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403


def cent_tol(expected: float, rel: float = 0.01) -> float:
    """rel_tol for a workbook figure that ties to the cent: the largest power of ten keeping expected x rel_tol
    under 1.00 (never looser than rel). Figures involving conversion, proration or an estimate declare
    `rounding: <reason>` on the check instead and keep rel_tol at most 0.001."""
    import math
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))



# bizgen.write_xlsx leaves openpyxl's save-time wall clock in docProps/core.xml, so two runs a
# second apart produce different bytes and the validator's determinism check fails intermittently.
# Local workaround (tasks/lib is not ours to change): pin dcterms:modified and re-freeze the zip.
import io as _io  # noqa: E402
import re as _re  # noqa: E402
import zipfile as _zip  # noqa: E402


def stable_xlsx(path: str, sheets: dict, creator: str = "Export") -> None:
    write_xlsx(path, sheets, creator=creator)
    with _zip.ZipFile(path) as z:
        items = sorted((n, z.read(n)) for n in z.namelist())
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as out:
        for name, data in items:
            if name == "docProps/core.xml":
                data = _re.sub(rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>",
                               b'<dcterms:modified xsi:type="dcterms:W3CDTF">2026-01-15T09:00:00Z</dcterms:modified>',
                               data)
            zi = _zip.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = _zip.ZIP_DEFLATED
            out.writestr(zi, data)
    write_bytes(path, buf.getvalue())

MONTHS = ["2026-01", "2026-02", "2026-03"]
MONTH_NUM = {"2026-01": 1, "2026-02": 2, "2026-03": 3}
MONTH_DAYS = {1: 31, 2: 28, 3: 31}
VISIT_TYPES = ["Initial evaluation", "Follow-up", "Follow-up", "Follow-up", "Re-evaluation"]
KEPT_WORDS = ["Completed", "Arrived"]
NOSHOW_WORDS = ["No Show", "No-show", "NOSHOW", "No show"]
CANCEL_WORDS = ["Cancelled", "Canceled", "Cancelled by patient", "Cancelled - clinic"]
ROOMS = ["Room 1", "Room 2", "Room 3", "Gym floor"]


def alias_forms(first: str, last: str, cred: str) -> list[str]:
    return [f"{first} {last}", f"{last}, {first}", f"{first[0]}. {last}", f"{first} {last}".upper(),
            f"{first} {last}, {cred}"]


def build(seed: int) -> dict:
    r = rng(seed)
    # four providers with distinct last names and distinct first initials
    while True:
        cand = people(r, 4)
        lasts = [l for _, l in cand]
        inits = [f[0] for f, _ in cand]
        if len(set(lasts)) == 4 and len(set(inits)) == 4:
            break
    creds = ["PT", "DPT", "PT", "OT"]
    provs = []
    for i, (f, l) in enumerate(cand):
        # provider 0 shows up under four spellings, provider 1 under two, the rest under one
        n_alias = {0: 4, 1: 2}.get(i, 1)
        provs.append({"first": f, "last": l, "name": f"{f} {l}", "cred": creds[i],
                      "aliases": alias_forms(f, l, creds[i])[:n_alias] if n_alias > 1 else [f"{f} {l}"],
                      "room": ROOMS[i]})
    if len(provs[0]["aliases"]) == 4:
        provs[0]["aliases"] = alias_forms(provs[0]["first"], provs[0]["last"], provs[0]["cred"])[:4]
    if len(provs[1]["aliases"]) == 2:
        provs[1]["aliases"] = [provs[1]["name"], f"{provs[1]['name']}, {provs[1]['cred']}"]

    rows, seq = [], 70000
    for p in provs:
        for m in MONTHS:
            mn = MONTH_NUM[m]
            kept = r.randint(34, 48)
            walkin = r.randint(4, 8)
            noshow = r.randint(4, 9)
            cancel = r.randint(6, 12)
            resched = r.randint(3, 6)
            for kind, n in (("kept", kept), ("walkin", walkin), ("noshow", noshow),
                            ("cancel", cancel), ("resched", resched)):
                for _ in range(n):
                    seq += 1
                    d = date(2026, mn, r.randint(1, MONTH_DAYS[mn]))
                    if kind == "kept":
                        status = r.choice([KEPT_WORDS[0], KEPT_WORDS[1], KEPT_WORDS[1]] if mn >= 2 else [KEPT_WORDS[0]])
                        vtype = r.choice(VISIT_TYPES)
                        appt = f"A-{seq}"
                    elif kind == "walkin":
                        status = r.choice(KEPT_WORDS)
                        vtype = "Walk-in"
                        appt = ""
                    elif kind == "noshow":
                        status = r.choice(NOSHOW_WORDS)
                        vtype = r.choice(VISIT_TYPES)
                        appt = f"A-{seq}"
                    elif kind == "cancel":
                        status = r.choice(CANCEL_WORDS)
                        vtype = r.choice(VISIT_TYPES)
                        appt = f"A-{seq}"
                    else:
                        status = "Rescheduled"
                        vtype = r.choice(VISIT_TYPES)
                        appt = f"A-{seq}"
                    rows.append({"appt": appt, "date": d, "prov": p, "kind": kind, "status": status,
                                 "vtype": vtype, "pat": f"PT-{r.randint(10000, 99999)}",
                                 "mins": r.choice([30, 45, 45, 60]), "k": r.random()})
    rows.sort(key=lambda x: (x["date"], x["k"]))
    # spread each provider's spellings over their rows
    for x in rows:
        al = x["prov"]["aliases"]
        x["shown"] = al[(sum(ord(c) for c in (x["appt"] or x["pat"])) + x["date"].day) % len(al)]

    # ---- truth ----
    visits, noshows, onbook = {}, {}, {}
    for x in rows:
        key = (x["prov"]["name"], f"{x['date'].year}-{x['date'].month:02d}")
        if x["kind"] in ("kept", "walkin"):
            visits[key] = visits.get(key, 0) + 1
        if x["kind"] == "noshow":
            noshows[key] = noshows.get(key, 0) + 1
        if x["kind"] in ("kept", "noshow"):
            onbook[key] = onbook.get(key, 0) + 1
    tot_visits = {p["name"]: sum(v for (n, _), v in visits.items() if n == p["name"]) for p in provs}
    tot_noshow = {p["name"]: sum(v for (n, _), v in noshows.items() if n == p["name"]) for p in provs}
    tot_onbook = {p["name"]: sum(v for (n, _), v in onbook.items() if n == p["name"]) for p in provs}
    rates = {p["name"]: round(tot_noshow[p["name"]] / tot_onbook[p["name"]], 4) for p in provs}

    # ---- the cancellation-fee billing export (a distractor that looks like visits) ----
    fees = []
    for x in [y for y in rows if y["kind"] in ("noshow", "cancel")]:
        if r.random() < 0.45:
            fees.append({"fee": f"F-{r.randint(3000, 3999)}{len(fees)}", "date": x["date"],
                         "prov": f"{x['prov']['last']} {x['prov']['first'][0]}", "pat": x["pat"],
                         "amt": r.choice([35.0, 50.0, 50.0, 75.0]),
                         "why": "No-show fee" if x["kind"] == "noshow" else "Late cancellation fee"})
    fees.sort(key=lambda f: (f["date"], f["fee"]))
    return {"provs": provs, "rows": rows, "fees": fees, "visits": visits, "noshows": noshows,
            "onbook": onbook, "tot_visits": tot_visits, "tot_noshow": tot_noshow,
            "tot_onbook": tot_onbook, "rates": rates,
            "clinic_visits": sum(tot_visits.values()), "clinic_noshow": sum(tot_noshow.values()),
            "clinic_onbook": sum(tot_onbook.values())}


def acceptable(d: dict) -> bool:
    p0 = d["provs"][0]["name"]
    feb = (p0, "2026-02")
    if feb not in d["visits"]:
        return False
    rows_p0_feb = [x for x in d["rows"] if x["prov"]["name"] == p0 and x["date"].month == 2]
    # the four spellings must all be used by provider 0, and at least two of them in February
    shown_all = {x["shown"] for x in d["rows"] if x["prov"]["name"] == p0}
    if len(shown_all) < 4 or len({x["shown"] for x in rows_p0_feb}) < 3:
        return False
    walk = sum(1 for x in rows_p0_feb if x["kind"] == "walkin")
    arrived = sum(1 for x in rows_p0_feb if x["kind"] in ("kept", "walkin") and x["status"] == "Arrived")
    if walk < 3 or arrived < 6:
        return False
    # the pinned monthly cell must not collide with that provider's other figures
    others = [v for (n, _), v in d["visits"].items() if n == p0] + [d["tot_visits"][p0], d["tot_noshow"][p0], d["tot_onbook"][p0]]
    if sum(1 for v in others if abs(v - d["visits"][feb]) <= 1) > 1:
        return False
    # provider 1's no-show count must be distinct from their visit counts
    p1 = d["provs"][1]["name"]
    if d["tot_noshow"][p1] in [v for (n, _), v in d["visits"].items() if n == p1] + [d["tot_visits"][p1], d["tot_onbook"][p1]]:
        return False
    # the clinic total must move if the fee export is merged or walk-ins dropped
    if len(d["fees"]) < 0.05 * d["clinic_visits"]:
        return False
    if sum(1 for x in d["rows"] if x["kind"] == "walkin") < 0.05 * d["clinic_visits"]:
        return False
    # the two rates that get pinned must differ from each other and from a denominator that
    # wrongly includes cancellations or walk-ins
    for p in (d["provs"][0]["name"], d["provs"][1]["name"]):
        cancels = sum(1 for x in d["rows"] if x["prov"]["name"] == p and x["kind"] == "cancel")
        wrong = d["tot_noshow"][p] / (d["tot_onbook"][p] + cancels)
        if abs(wrong - d["rates"][p]) < 0.1 * d["rates"][p]:
            return False
    if abs(d["rates"][d["provs"][0]["name"]] - d["rates"][d["provs"][1]["name"]]) < 0.08 * d["rates"][d["provs"][0]["name"]]:
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_sheets(data_rows: list[list], names: list[str]) -> dict:
    n = len(data_rows) + 1
    rows = []
    for i, name in enumerate(names, start=2):
        line = [name]
        for j, m in enumerate(MONTHS):
            c = chr(ord("B") + j)
            line.append(f"=SUMIFS(Data!$E$2:$E${n},Data!$D$2:$D${n},$A{i},Data!$C$2:$C${n},{c}$1)")
        line += [f"=SUM(B{i}:D{i})",
                 f"=SUMIFS(Data!$F$2:$F${n},Data!$D$2:$D${n},$A{i})",
                 f"=SUMIFS(Data!$G$2:$G${n},Data!$D$2:$D${n},$A{i})",
                 f'=IF(G{i}=0,"n/a",ROUND(F{i}/G{i},4))']
        rows.append(line)
    last = 1 + len(names)
    rows.append(["All providers"] + [f"=SUM({c}2:{c}{last})" for c in "BCDEFG"] +
                [f'=IF(G{last + 1}=0,"n/a",ROUND(F{last + 1}/G{last + 1},4))'])
    rows.append([])
    rows.append(["Visits include walk-ins. The no-show rate is no-shows over appointments that were on the book "
                 "(kept plus no-shows); walk-ins and cancellations are not in that denominator."])
    return {
        "Data": {"header": ["appt_id", "date", "month", "provider", "is_visit", "is_no_show", "on_the_book"],
                 "rows": data_rows, "widths": {"D": 22}},
        "Report": {"header": ["Provider"] + MONTHS + ["Total visits", "No-shows", "Appointments on the book", "No-show rate"],
                   "rows": rows, "widths": {"A": 24, "E": 12, "F": 11, "G": 24, "H": 13}},
    }


def clean_rows(d: dict) -> list[list]:
    out = []
    for x in sorted(d["rows"], key=lambda y: (y["date"], y["appt"] or y["pat"])):
        if x["kind"] not in ("kept", "walkin", "noshow"):
            continue
        out.append([x["appt"] or "(walk-in)", x["date"].isoformat(), f"{x['date'].year}-{x['date'].month:02d}",
                    x["prov"]["name"], 1 if x["kind"] in ("kept", "walkin") else 0,
                    1 if x["kind"] == "noshow" else 0, 1 if x["kind"] in ("kept", "noshow") else 0])
    return out


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    provs = d["provs"]
    names = [p["name"] for p in provs]

    # ---- workspace ----
    vrows = []
    for x in d["rows"]:
        style = (sum(ord(c) for c in (x["appt"] or x["pat"])) % 3)
        vrows.append([x["appt"], date_variant(x["date"], [0, 1, 6][style]), x["shown"], x["pat"],
                      x["vtype"], x["status"], x["mins"]])
    write_csv(os.path.join(ws, "visits_export_q1_2026.csv"),
              ["Appt ID", "Date", "Provider", "Patient ID", "Visit Type", "Status", "Duration (min)"], vrows,
              preamble=["Riverbend Physio - appointment export", "01/01/2026 to 03/31/2026 (both schedulers)"],
              bom=True)
    stable_xlsx(os.path.join(ws, "provider_roster.xlsx"), {"Roster": {
        "merged_title": "Treating providers - Q1 2026",
        "header": ["Provider", "Credential", "Room", "Started", "Notes"],
        "rows": [[p["name"], p["cred"], p["room"], date(2019 + i, 3 + i, 4 + i),
                  "Covers walk-ins on Fridays" if i == 0 else ""] for i, p in enumerate(provs)],
        "widths": {"A": 24, "E": 30}}}, creator="Practice manager")
    write_csv(os.path.join(ws, "cancellation_fees_billing.csv"),
              ["Fee ID", "Service Date", "Provider", "Patient", "Fee", "Reason"],
              [[f["fee"], date_variant(f["date"], 1), f["prov"], f["pat"], money_str(f["amt"], 1), f["why"]]
               for f in d["fees"]],
              preamble=["Billing export - patient fees", "Not a visit list"])
    write_text(os.path.join(ws, "front_desk_notes.txt"),
               "How we count visits (from the front desk)\n"
               "\n"
               "A visit is a patient we actually treated. The old scheduler wrote Completed and the new one writes\n"
               "Arrived; they mean the same thing. Walk-ins are treated patients too, so they are visits, even\n"
               "though they never had an appointment number.\n"
               "\n"
               "The no-show rate is no-shows out of the appointments that were on the book that day - the ones we\n"
               "kept plus the ones nobody turned up for. Cancellations came off the book with notice, so they do\n"
               "not count against a provider, and walk-ins were never on the book to begin with.\n"
               "\n"
               "A Rescheduled row is the old slot for an appointment that moved; the new slot has its own row.\n"
               "\n"
               "Everyone on the roster should be on the report, under the name on the roster - the schedulers\n"
               "never agreed on how to write us down.\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "visits_by_provider_month.csv"), ["provider", "month", "visits", "no_shows", "on_the_book"],
              [[n, m, d["visits"].get((n, m), 0), d["noshows"].get((n, m), 0), d["onbook"].get((n, m), 0)]
               for n in names for m in MONTHS])
    write_csv(os.path.join(ref, "provider_totals.csv"), ["provider", "visits", "no_shows", "on_the_book", "no_show_rate"],
              [[n, d["tot_visits"][n], d["tot_noshow"][n], d["tot_onbook"][n], f"{d['rates'][n]:.4f}"] for n in names] +
              [["ALL", d["clinic_visits"], d["clinic_noshow"], d["clinic_onbook"],
                f"{d['clinic_noshow'] / d['clinic_onbook']:.4f}"]])
    write_json(os.path.join(ref, "notes.json"), {
        "no_show_rates": {p["last"]: d["rates"][p["name"]] for p in provs},
        "clinic_no_show_rate": round(d["clinic_noshow"] / d["clinic_onbook"], 4),
        "provider_aliases": {p["name"]: p["aliases"] for p in provs},
        "walk_in_visits": sum(1 for x in d["rows"] if x["kind"] == "walkin"),
        "fee_rows": len(d["fees"])})

    # ---- reference solution ----
    stable_xlsx(os.path.join(sol, "visits.xlsx"), report_sheets(clean_rows(d), names), creator="reference")

    p0, p1 = names[0], names[1]
    write_task_yaml(HERE, {
        "id": "clinic-visits-summary", "track": "desk", "category": "reports",
        "title": "Visits per provider and the no-show rate for Q1",
        "ask": ("Can you pull our Q1 numbers out of the scheduler export - how many visits each provider did in each "
                "month, and how bad our no-show problem is? Save it as visits.xlsx with live formulas. The front desk "
                "notes say how we count them.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"{provs[0]['last']} appears under four spellings in the export ('{provs[0]['aliases'][0]}', "
            f"'{provs[0]['aliases'][1]}', '{provs[0]['aliases'][2]}', '{provs[0]['aliases'][3]}') and "
            f"{provs[1]['last']} under two; a group-by on the raw provider column splits them into separate rows "
            "(checks: merged provider February visits; merged provider quarter visits)",
            "the clinic changed schedulers in February, so a kept visit is written 'Completed' in January and mostly "
            "'Arrived' afterwards; counting only 'Completed' loses a third of the quarter "
            "(checks: merged provider February visits; clinic total visits)",
            "walk-ins are visits with no appointment id, and they are treated patients, but they were never on the "
            "book so they stay out of the no-show denominator (checks: clinic total visits; no-show rates)",
            "cancellations are spelled four ways and are neither visits nor no-shows; 'Rescheduled' rows are the "
            "vacated slot and must not be counted twice (checks: no-show count; no-show rates)",
            "the cancellation-fee billing export carries a provider, a date and a patient on every row and looks like "
            "a second visit list; merging it inflates every count (check: clinic total visits)",
            "dates come in three formats and the export carries a two-line preamble and a BOM "
            "(check: clinic total visits)",
        ],
        "checks": [
            {"type": "file_exists", "name": "visits.xlsx exists", "path": "visits.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "visits.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "visits.xlsx"},
            {"type": "xlsx_value_present", "name": "merged provider February visits", "path": "visits.xlsx",
             "expected": d["visits"][(p0, "2026-02")], "rel_tol": cent_tol(d["visits"][(p0, "2026-02")], 0.001), "near_text": provs[0]["last"].lower()},
            {"type": "xlsx_value_present", "name": "merged provider quarter visits", "path": "visits.xlsx",
             "expected": d["tot_visits"][p0], "rel_tol": cent_tol(d["tot_visits"][p0], 0.001), "near_text": provs[0]["last"].lower()},
            {"type": "xlsx_value_present", "name": "second provider no-show count", "path": "visits.xlsx",
             "expected": d["tot_noshow"][p1], "rel_tol": cent_tol(d["tot_noshow"][p1], 0.001), "near_text": provs[1]["last"].lower()},
            {"type": "xlsx_value_present", "name": "clinic total visits", "path": "visits.xlsx",
             "expected": d["clinic_visits"], "rel_tol": cent_tol(d["clinic_visits"], 0.002), "near_text": "total"},
            {"type": "custom", "name": "no-show rates per provider", "module": "check.py"},
        ],
    })
    print(f"seed={seed} rows={len(d['rows'])} fee_rows={len(d['fees'])} providers={names}")
    print("aliases:", {p['name']: p['aliases'] for p in provs})
    print("visits:", d["tot_visits"], "noshows:", d["tot_noshow"], "onbook:", d["tot_onbook"])
    print("rates:", d["rates"], "clinic visits:", d["clinic_visits"])
    print("pinned feb cell:", p0, d["visits"][(p0, "2026-02")])


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcut: group by the provider column as written, count every row that is not
    a cancellation as a visit, and use every appointment as the no-show denominator."""
    os.makedirs(out, exist_ok=True)
    rows, names = [], []
    for x in sorted(d["rows"], key=lambda y: (y["date"], y["appt"] or y["pat"])):
        if x["shown"] not in names:
            names.append(x["shown"])
        if x["status"] in CANCEL_WORDS:
            continue
        rows.append([x["appt"] or "", x["date"].isoformat(), f"{x['date'].year}-{x['date'].month:02d}", x["shown"],
                     1 if x["status"] == "Completed" else 0, 1 if x["status"] in NOSHOW_WORDS else 0, 1])
    stable_xlsx(os.path.join(out, "visits.xlsx"), report_sheets(rows, sorted(names)), creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 400 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
