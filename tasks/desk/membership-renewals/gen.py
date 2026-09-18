#!/usr/bin/env python3
"""membership-renewals: October renewal list and lapsed members for a heritage museum, with the grace rule.

    python gen.py [--seed N] [--naive DIR]

Business: Hollis Creek Heritage Museum in Burlington. The membership system exports every member paid since
July 2025. Its Status column flips to Expired the day after expiry and never marks monthly sustainers anything
but Active. The membership coordinator's note carries the museum's grace rule.

Traps (each caught by a check, see task.yaml):
  * the grace rule: an annual member stays a member for 30 days after the expiration date, a monthly sustainer
    for 10 days after the paid-through date; members in grace are on neither list, and the system's Expired
    status ignores grace (checks: members on the list; list per member)
  * boundary days: a membership whose grace ends on the report date is still in grace   (check: list per member)
  * monthly sustainers have no expiration in the export and always show Active; they are paid through one month
    after their last charge, are never due, and lapse when the charges stop; one stopped in October 2025 and
    looks due under an annual reading                          (checks: members on the list; expiry dates)
  * comped memberships (board, volunteers, honorary) are left off both lists          (check: members on the list)
  * members who upgraded have an older record under a new member number; only the newest record counts
                                                                                     (check: members on the list)
"""
from __future__ import annotations
import argparse
import calendar
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

REPORT = date(2026, 9, 15)
DUE_MONTH = (2026, 10)
ANNUAL_GRACE, MONTHLY_GRACE = 30, 10
LEVELS = [("Individual", "Annual", 55.0), ("Dual", "Annual", 80.0), ("Family", "Annual", 100.0), ("Patron", "Annual", 250.0),
          ("Student", "Annual", 25.0), ("Sustainer", "Monthly", 10.0)]


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def classify(mem: dict) -> tuple[str | None, date]:
    """(list, expires) for the newest non-comp record; list is DUE, LAPSED or None."""
    if mem["term"] == "Annual":
        exp = add_months(mem["paid"], 12)
        if REPORT > exp + timedelta(days=ANNUAL_GRACE):
            return "LAPSED", exp
        if (exp.year, exp.month) == DUE_MONTH:
            return "DUE", exp
        return None, exp
    thru = add_months(mem["paid"], 1)
    if REPORT > thru + timedelta(days=MONTHLY_GRACE):
        return "LAPSED", thru
    return None, thru


def build(seed: int) -> dict:
    r = rng(seed)
    names = people(r, 190)
    members = []

    def add(level, paid, method="Card", note="", email=None, name=None, tag=""):
        lv = next(l for l in LEVELS if l[0] == level)
        f, l = name or names[len(members)]
        if not email:
            taken = {m["email"] for m in members}
            email = email_for(r, f, l)
            while email in taken:
                email = email_for(r, f, l)
        members.append({"level": level, "term": lv[1], "amount": 0.0 if method == "Comp" else lv[2], "paid": paid,
                        "method": method, "note": note, "first": f, "last": l,
                        "email": email, "tag": tag, "joined": min(paid, date(r.randint(2012, 2025), r.randint(1, 12), r.randint(1, 28)))})
        return members[-1]

    annual_levels = [l[0] for l in LEVELS if l[1] == "Annual"]
    # ---- fixed trap members ----
    add(r.choice(annual_levels), date(2025, 8, 16), tag="boundary_in")      # grace ends on the report date: in grace
    add(r.choice(annual_levels), date(2025, 8, 15), tag="boundary_lapsed")  # grace ended the day before: lapsed
    add(r.choice(annual_levels), date(2025, 9, 2))                  # expired 2 Sep, in grace
    add(r.choice(annual_levels), date(2025, 8, 27))                 # in grace
    add("Sustainer", date(2026, 8, 5))                              # thru 5 Sep, grace ends 15 Sep: in grace
    add("Sustainer", date(2026, 8, 4))                              # lapsed
    add("Sustainer", date(2025, 10, r.randint(2, 27)))              # stopped in October 2025: lapsed, not due
    add("Sustainer", date(2026, 6, r.randint(2, 27)))               # stopped in June: lapsed
    add("Family", date(2025, 10, r.randint(3, 26)), "Comp", "Board of trustees")   # comp due in October
    add("Individual", date(2025, 7, r.randint(3, 26)), "Comp", "Volunteer - docent")  # comp past grace
    add("Patron", date(2025, 10, r.randint(3, 26)), "Comp", "Honorary")
    # upgrades: old record and new record share a person
    for old_level, old_paid, new_level, new_paid in (("Individual", date(2025, 7, r.randint(6, 28)), "Family", date(2026, 3, r.randint(2, 27))),
                                                     ("Dual", date(2025, 10, r.randint(6, 28)), "Patron", date(2026, 5, r.randint(2, 27)))):
        old = add(old_level, old_paid, note="")
        add(new_level, new_paid, note=f"Upgraded from {old_level}", email=old["email"], name=(old["first"], old["last"]))
        members[-1]["joined"] = old["joined"]
    # ---- everyone else ----
    while len(members) < 168:
        level = r.choices([l[0] for l in LEVELS], weights=[30, 16, 22, 5, 5, 22])[0]
        if level == "Sustainer":
            paid = day_in(r, date(2026, 8, 16), date(2026, 9, 14))   # charges still going through
            paid = paid.replace(day=min(paid.day, 28))
        else:
            paid = day_in(r, date(2025, 7, 1), date(2026, 9, 12))
            while paid in (date(2025, 8, 15), date(2025, 8, 16)):
                paid = day_in(r, date(2025, 7, 1), date(2026, 9, 12))
        method = r.choices(["Card", "Check", "Cash", "Comp"], weights=[70, 18, 6, 6])[0]
        add(level, paid, method, "Volunteer" if method == "Comp" else "")
    order = list(range(len(members)))
    r.shuffle(order)
    members = [members[i] for i in order]
    for i, m in enumerate(members):
        m["id"] = f"HC-{4100 + i * 3 + r.randint(0, 2)}"
    # newest record per email
    newest = {}
    for m in members:
        k = m["email"].lower()
        if k not in newest or m["paid"] > newest[k]["paid"]:
            newest[k] = m
    out = []
    for m in members:
        lst, exp = classify(m)
        m["expires"], m["list_raw"] = exp, lst
        if m["method"] == "Comp" or newest[m["email"].lower()] is not m:
            continue
        if lst:
            out.append({"id": m["id"], "name": f"{m['first']} {m['last']}", "email": m["email"], "list": lst, "expires": exp.isoformat()})
    out.sort(key=lambda x: (x["list"], x["expires"], x["id"]))
    return {"members": members, "out": out}


def naive_rows(d: dict) -> list[list]:
    """System status and expiration: Expired means lapsed, October expirations are due, no grace, comps and
    superseded records kept, monthly sustainers taken at face value (Active)."""
    rows = []
    for m in d["members"]:
        if m["term"] != "Annual":
            continue
        exp = add_months(m["paid"], 12)
        if exp < REPORT:
            rows.append([m["id"], f"{m['first']} {m['last']}", m["email"], "LAPSED", exp.isoformat()])
        elif (exp.year, exp.month) == DUE_MONTH:
            rows.append([m["id"], f"{m['first']} {m['last']}", m["email"], "DUE", exp.isoformat()])
    return rows


def acceptable(d: dict) -> bool:
    lists = [x["list"] for x in d["out"]]
    return lists.count("DUE") >= 8 and lists.count("LAPSED") >= 10


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["member_id", "name", "email", "list", "expires"]
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_csv(os.path.join(naive_dir, "renewals.csv"), header, naive_rows(d))
        return
    ws, ref, sol = task_dirs(HERE)

    rows = []
    for m in sorted(d["members"], key=lambda m: (m["last"], m["first"], m["paid"])):
        annual = m["term"] == "Annual"
        exp = add_months(m["paid"], 12) if annual else None
        status = ("Expired" if exp < REPORT else "Active") if annual else "Active"
        email = m["email"].upper() if m["note"].startswith("Upgraded") and sum(map(ord, m["id"])) % 2 else m["email"]
        rows.append([m["id"], m["first"], m["last"], email, m["level"], m["term"], m["paid"].strftime("%m/%d/%Y"),
                     f"{m['amount']:.2f}", m["method"], exp.strftime("%m/%d/%Y") if exp else "", status,
                     m["joined"].strftime("%m/%d/%Y"), m["note"]])
    write_csv(os.path.join(ws, "members_export_2026-09-15.csv"),
              ["Member #", "First Name", "Last Name", "Email", "Level", "Term", "Last Payment", "Amount", "Payment Method",
               "Expiration", "Status", "Member Since", "Notes"], rows,
              preamble=["Hollis Creek Heritage Museum - Membership Export", "Members with a payment on or after 07/01/2025 | run 09/15/2026 07:02"],
              bom=True, crlf=True)
    sept = [m for m in d["members"] if m["term"] == "Annual" and (add_months(m["paid"], 12).year, add_months(m["paid"], 12).month) == (2026, 9)]
    write_csv(os.path.join(ws, "renewal_letters_mailed_2026-08-14.csv"), ["Member #", "Name", "Level", "Expires", "Letter"],
              [[m["id"], f"{m['first']} {m['last']}", m["level"], add_months(m["paid"], 12).strftime("%m/%d/%Y"), "September renewal - first notice"]
               for m in sorted(sept, key=lambda m: m["paid"]) if m["method"] != "Comp"])
    write_text(os.path.join(ws, "note_from_leila.txt"),
               "Renewal list for October - and the lapsed list\n"
               "\n"
               "Every month I send renewal letters to members whose membership runs out the following month, and a\n"
               "'we miss you' letter to members who have lapsed. It's the 15th of September, so this round is\n"
               "October renewals.\n"
               "\n"
               "A few rules, because the export does not know them:\n"
               "\n"
               "1. Grace period. Members keep their benefits for a while after their membership runs out, and they\n"
               "   are still members during that time. Annual members get 30 days after their expiration date;\n"
               "   monthly sustainers get 10 days after the date they are paid through. Count the grace days from\n"
               "   the day after: a membership that expires on 1 August is in grace through 31 August and lapsed from\n"
               "   1 September. Anyone still in their grace period goes on neither list - the front desk handles them.\n"
               "   The Status column in the export says Expired the day after expiry, so please don't go by it.\n"
               "\n"
               "2. Monthly sustainers are charged every month on the same day, so each charge pays them through the\n"
               "   same date the next month. The system shows them Active forever and leaves Expiration blank - go by\n"
               "   the last payment. They renew automatically, so they are never on the renewal list, only on the\n"
               "   lapsed list if the charges have stopped.\n"
               "\n"
               "3. Comped memberships (board, volunteers, honorary - Payment Method says Comp) don't get either letter.\n"
               "\n"
               "4. When someone upgrades, the system gives them a new member number and leaves the old record behind.\n"
               "   Same email means same person; only their newest record counts.\n"
               "\n"
               "Please save it as renewals.csv, one line per member who gets a letter: member_id, name, email,\n"
               "list (DUE or LAPSED) and expires - the date the membership ran out or runs out (for sustainers the\n"
               "paid-through date), written like 2026-10-04.\n"
               "\n"
               "Thank you!\n"
               "Leila\n")

    # ---- reference ----
    ref_rows = [[x["id"], x["name"], x["email"], x["list"], x["expires"]] for x in d["out"]]
    write_csv(os.path.join(ref, "renewals.csv"), header, ref_rows)
    write_csv(os.path.join(sol, "renewals.csv"), header, ref_rows)
    by_id = {m["id"]: m for m in d["members"]}
    special = {"annual_grace_boundary_in": [m["id"] for m in d["members"] if m["tag"] == "boundary_in"],
               "annual_grace_boundary_lapsed": [m["id"] for m in d["members"] if m["tag"] == "boundary_lapsed"],
               "comps": [m["id"] for m in d["members"] if m["method"] == "Comp"],
               "superseded": [m["id"] for m in d["members"] if any(o is not m and o["email"].lower() == m["email"].lower() and o["paid"] > m["paid"] for o in d["members"])],
               "monthly_lapsed": [x["id"] for x in d["out"] if by_id[x["id"]]["term"] == "Monthly"]}
    write_json(os.path.join(ref, "notes.json"), {"report_date": REPORT.isoformat(), **special,
                                                  "due": sum(1 for x in d["out"] if x["list"] == "DUE"),
                                                  "lapsed": sum(1 for x in d["out"] if x["list"] == "LAPSED")})
    must = special["annual_grace_boundary_lapsed"] + special["monthly_lapsed"]
    newest_ids = {x["id"] for x in d["out"]}
    in_grace = sum(1 for m in d["members"] if m["term"] == "Annual" and m["method"] != "Comp" and m["list_raw"] is None
                   and add_months(m["paid"], 12) < REPORT)
    comp_listed = sum(1 for m in d["members"] if m["method"] == "Comp" and m["list_raw"])
    n_monthly = len(special["monthly_lapsed"])

    write_task_yaml(HERE, {
        "id": "membership-renewals", "track": "desk", "category": "spreadsheet",
        "title": "October renewal letters and the lapsed list",
        "ask": ("Leila needs this month's letter lists: who is due to renew in October and who has lapsed. Work it out from "
                "the membership export and save renewals.csv - her note has the museum's rules.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the grace rule: annual members stay members for 30 days after expiration and sustainers for 10 days after "
            "their paid-through date, and anyone in grace is on neither list; the export's Status says Expired the day "
            f"after expiry, so filtering on it lists {in_grace} annual members who are still in grace "
            "(checks: members on the list; row count)",
            "grace days count from the day after expiry: the member who expired on 2026-08-16 is in grace through "
            "2026-09-15 (the report date) and stays off, while the one who expired on 2026-08-15 is lapsed; ending grace "
            "on day 30 lists the first, and waiting until more than 31 days have passed misses the second "
            "(checks: members on the list; list per member)",
            "monthly sustainers have a blank Expiration and always show Active; they are paid through one month after "
            f"the last charge and lapse 10 days later, so {n_monthly} who stopped paying are lapsed (the boundary sustainer "
            "charged 2026-08-05 is still in grace), and the one who stopped in October 2025 looks due for October "
            "under an annual reading (checks: list per member; expiry dates)",
            f"{comp_listed} comped memberships (board, volunteers, honorary) would be due or lapsed and get no letter "
            "(check: members on the list)",
            "two members upgraded and left an old record under another member number with the same email (one in "
            "capitals); the old Individual record looks lapsed and the old Dual record looks due in October "
            "(check: members on the list)",
            "last month's September mailing list sits in the folder as a distractor, and the export has a two-line "
            "preamble, a BOM and CRLF endings (check: members on the list)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "renewals.csv", "columns": header},
            {"type": "csv_set_equal", "name": "members on the list", "path": "renewals.csv", "column": "member_id",
             "ref": "renewals.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "renewals.csv", "equals_ref": "renewals.csv"},
            {"type": "csv_values_match", "name": "list per member", "path": "renewals.csv", "ref": "renewals.csv",
             "key": "member_id", "columns": ["list"], "min_accuracy": 1.0, "must_match_keys": must},
            {"type": "csv_values_match", "name": "expiry dates", "path": "renewals.csv", "ref": "renewals.csv",
             "key": "member_id", "columns": ["expires"], "min_accuracy": 1.0},
        ],
    })
    print(f"seed={seed} members={len(d['members'])} due={sum(1 for x in d['out'] if x['list']=='DUE')} lapsed={sum(1 for x in d['out'] if x['list']=='LAPSED')}")
    print(special)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(300):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 300 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
