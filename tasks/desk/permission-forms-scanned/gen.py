#!/usr/bin/env python3
"""permission-forms-scanned: scanned field-trip permission slips matched to a class roster for the school office.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * every slip is an image-only scan; OCR is the only way in                         (checks: student and guardian names; permission and signature)
  * three families used last year's form, which opens "I, <guardian>, parent or legal guardian of <student>", so
    the guardian's name comes first                                                 (check: student and guardian names)
  * two guardians have a different last name from the child and one slip calls the child by a nickname; the roster
    spelling and id are what the office wants                                       (checks: one row per roster student; student and guardian names)
  * one slip ticks "may attend" but was never signed; the note says an unsigned slip grants nothing
                                                                                    (checks: permission and signature; photo release)
  * one parent ticked "may NOT attend"                                              (check: permission and signature)
  * one family sent two slips; the later one changes the photo release, and it was scanned first
                                                                                    (checks: photo release; date signed)
  * one roster student returned nothing and still needs a row                       (checks: one row per roster student; permission and signature)
  * a slip for a sibling in Room 2 is in the stack and is not on the roster         (checks: row count; other-class slip left out)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

NICK = {"Elizabeth": "Liz", "Jonathan": "Jon", "Matthew": "Matt", "Nicholas": "Nick", "Christopher": "Chris", "Daniel": "Danny",
        "Anthony": "Tony", "Rebecca": "Becca", "Joshua": "Josh", "Margaret": "Maggie", "Stephanie": "Steph", "Kimberly": "Kim"}
SCHOOL = "FERNBROOK MONTESSORI"
TEACHER = "Amara Osei"
TRIP = "Quarry Road Nursery Pumpkin Farm"

def phone_fmt(d: str, style: int) -> str:
    return [f"({d[:3]}) {d[3:6]}-{d[6:]}", f"{d[:3]}-{d[3:6]}-{d[6:]}", f"{d[:3]}.{d[3:6]}.{d[6:]}", f"{d[:3]} {d[3:6]} {d[6:]}"][style % 4]

def build(seed: int) -> dict:
    r = rng(seed)
    lasts = r.sample(LAST, 16)
    kid_pool = [f for f in FIRST if f not in NICK]
    firsts = r.sample(kid_pool, 12)
    firsts[3] = r.choice(sorted(NICK))
    students = []
    for i in range(12):
        students.append(dict(id=f"FM-{2040 + i * 7}", first=firsts[i], last=lasts[i]))
    adult_pool = [f for f in FIRST if f not in firsts and f not in NICK.values()]
    g_first = r.sample(adult_pool, 13)
    phones = []
    while len(phones) < 13:
        p = phone_digits(r)
        if p not in phones: phones.append(p)
    for i, s in enumerate(students):
        s["g_first"] = g_first[i]
        s["g_last"] = lasts[12 + (0 if i == 2 else 1)] if i in (2, 7) else s["last"]
        s["phone"] = phones[i]
    # outcomes (by index; the draw order above is seeded, the structure is fixed)
    base = dict(form="current", attend=True, photo=True, signed=True, returned=True)
    plan = {0: {}, 1: dict(form="old"), 2: dict(form="old", photo=False), 3: dict(nick=True), 4: dict(attend=False, photo=False),
            5: dict(signed=False), 6: dict(double=True), 7: {}, 8: dict(form="old"), 9: dict(returned=False), 10: dict(photo=False), 11: {}}
    sign_days = [date(2026, 9, d) for d in (14, 15, 15, 16, 14, 17, 18, 16, 21, 14, 17, 15)]
    for i, s in enumerate(students):
        s.update(base); s.update(plan[i]); s["date"] = sign_days[i]
    s6 = students[6]; s6["early_date"] = date(2026, 9, 11); s6["early_photo"] = False; s6["photo"] = True
    # a Room 2 sibling of student 10 (same guardian), not on the roster
    sib_first = r.choice([f for f in FIRST if f not in firsts and f not in g_first and all(f.lower() not in x.lower() for x in firsts + g_first)
                          and not any(x.lower() in f.lower() for x in firsts + g_first)])
    sibling = dict(first=sib_first, last=students[10]["last"], g_first=students[10]["g_first"], g_last=students[10]["g_last"],
                   phone=students[10]["phone"], date=date(2026, 9, 17))
    return dict(students=students, sibling=sibling)

def current_form(student_name, room, guardian, phone, attend, photo, signed, dstr):
    return [SCHOOL, "FIELD TRIP PERMISSION FORM", "", f"Trip: {TRIP}", "Date: Friday, October 9, 2026", f"Room: {room}", "",
            f"Student name: {student_name}", f"Parent/guardian name: {guardian}", f"Daytime phone: {phone}", "",
            f"[{'X' if attend else ' '}] My child MAY attend this trip.", f"[{' ' if attend else 'X'}] My child may NOT attend this trip.", "",
            "Photo release (newsletter and website):", f"[{'X' if photo else ' '}] Yes, photos are OK", f"[{' ' if photo else 'X'}] No photos please", "",
            f"Parent/guardian signature: {guardian if signed else '____________________'}", f"Date: {dstr if signed else '__________'}"]

def old_form(student_name, guardian, phone, photo, dstr):
    return [SCHOOL, "PERMISSION TO PARTICIPATE", "", f"I, {guardian},", "parent or legal guardian of", f"{student_name}, give permission",
            "for my child to take part in the class", f"trip to {TRIP.replace(' Pumpkin Farm', '')}", "on October 9, 2026.", "",
            "Photos may be taken for school use", "(circle one):", "   (YES)    NO" if photo else "    YES    (NO)", "",
            f"Phone: {phone}", "", f"Signed: {guardian}", f"Date: {dstr}"]

def emit(seed: int) -> None:
    d = build(seed); S = d["students"]; sib = d["sibling"]
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "permission_slips"); os.makedirs(F, exist_ok=True)
    dfmt = [lambda x: f"{x.month}/{x.day}/{x.year}", lambda x: x.strftime("%B %-d, %Y"), lambda x: x.strftime("%-d %b %Y")]
    pages = []  # (lines, seed offset)
    for i, s in enumerate(S):
        if not s["returned"]:
            continue
        sname = f"{NICK[s['first']] if s.get('nick') else s['first']} {s['last']}"
        gname = f"{s['g_first']} {s['g_last']}"
        ph = phone_fmt(s["phone"], i)
        dstr = dfmt[i % 3](s["date"])
        if s["form"] == "old":
            pages.append(old_form(sname, gname, ph, s["photo"], dstr))
        else:
            pages.append(current_form(sname, "4 (Upper Elementary)", gname, ph, s["attend"], s["photo"], s["signed"], dstr))
        if s.get("double"):
            pages.append(current_form(sname, "4 (Upper Elementary)", gname, ph, True, s["early_photo"], True, dfmt[(i + 1) % 3](s["early_date"])))
    pages.append(current_form(f"{sib['first']} {sib['last']}", "2 (Lower Elementary)", f"{sib['g_first']} {sib['g_last']}",
                              phone_fmt(sib["phone"], 1), True, True, True, dfmt[0](sib["date"])))
    r = rng(seed + 99)
    order = list(range(len(pages)))
    r.shuffle(order)
    # the later of the two slips from the same family must be scanned before the earlier one
    later = next(k for k, s in enumerate(S) if s.get("double"))
    idx_later = sum(1 for s in S[:later] if s["returned"]) + sum(1 for s in S[:later] if s.get("double"))
    a, b = order.index(idx_later), order.index(idx_later + 1)
    if a > b:
        order[a], order[b] = order[b], order[a]
    for n, pi in enumerate(order):
        write_scan_pdf(os.path.join(F, f"Scan_2026-09-22_{n + 1:03d}.pdf"), pages[pi], font_size=32, seed=seed * 31 + n,
                       skew_deg=[0.5, -0.7, 0.9, -0.4][n % 4], noise=500 + 40 * (n % 5))

    roster = [[s["id"], s["last"], s["first"], r.choice(["4", "5", "6"])] for s in S]
    rrng = rng(seed + 5); rrng.shuffle(roster)
    write_csv(os.path.join(ws, "room4_roster.csv"), ["Student ID", "Last Name", "First Name", "Grade"], sorted(roster, key=lambda x: (x[1], x[2])),
              preamble=["Fernbrook Montessori - Room 4 class list 2026-27", ""], bom=True, crlf=True)
    write_text(os.path.join(ws, "note_from_ms_osei.txt"),
        "Hi,\n\nThe permission slips for the pumpkin farm trip on October 9 are scanned in the permission_slips folder. "
        "The office needs a consents.csv with one row for every student on my roster, with these columns:\n\n"
        "student_id, student_name, guardian_name, guardian_phone, form_returned, permission, photo_release, signed, date_signed\n\n"
        "student_name the way it is on the roster (First Last). guardian_name is the parent or guardian who filled in the slip. "
        "form_returned, permission, photo_release and signed are yes or no. date_signed as YYYY-MM-DD.\n\n"
        "A slip only counts if a parent or guardian signed it: if it isn't signed, put no for permission and photo release and leave the date blank. "
        "If a family sent in more than one slip, the most recent one is the one that counts. For anyone who hasn't returned a slip, "
        "put no in the yes/no columns and leave guardian, phone and date blank.\n\n"
        f"Thank you!\n{TEACHER}\nRoom 4\n")

    header = ["student_id", "student_name", "guardian_name", "guardian_phone", "form_returned", "permission", "photo_release", "signed", "date_signed"]
    rows = []
    for s in sorted(S, key=lambda x: x["id"]):
        if not s["returned"]:
            rows.append([s["id"], f"{s['first']} {s['last']}", "", "", "no", "no", "no", "no", ""]); continue
        yn = lambda b: "yes" if b else "no"
        ok = s["signed"]
        rows.append([s["id"], f"{s['first']} {s['last']}", f"{s['g_first']} {s['g_last']}", s["phone"], "yes",
                     yn(ok and s["attend"]), yn(ok and s["photo"]), yn(ok), s["date"].isoformat() if ok else ""])
    write_csv(os.path.join(ref, "consents.csv"), header, rows)
    write_csv(os.path.join(sol, "consents.csv"), header, rows)
    ids = {k: S[k]["id"] for k in range(12)}
    write_json(os.path.join(ref, "notes.json"), {"old_form": [ids[1], ids[2], ids[8]], "nickname": ids[3], "declined": ids[4], "unsigned": ids[5],
                                                  "two_slips": ids[6], "no_slip": ids[9], "different_last_name": [ids[2], ids[7]],
                                                  "room2_sibling": f"{sib['first']} {sib['last']}"})
    write_task_yaml(HERE, {
        "id": "permission-forms-scanned", "track": "desk", "category": "extraction",
        "title": "Match the scanned field trip slips to the class roster",
        "ask": "Ms. Osei scanned the field trip permission slips that came back. Please match them up with her class roster and save it as consents.csv - her note says what the office needs.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "every slip is an image-only scan with a slight skew and dust; there is no text layer (checks: student and guardian names; permission and signature)",
            "three families used last year's form, which reads 'I, <guardian>, parent or legal guardian of <student>', so the guardian's name comes first (check: student and guardian names)",
            f"two guardians have a different last name from the child, and the slip for {S[3]['first']} {S[3]['last']} calls the child {NICK[S[3]['first']]}; the roster id and spelling are what the office wants (checks: one row per roster student; student and guardian names)",
            "one slip ticks 'may attend' and 'Yes' for photos but the signature and date lines are blank; per the note it grants nothing (checks: permission and signature; photo release)",
            "one parent ticked 'may NOT attend'; a reading that looks for the word attend marks it yes (check: permission and signature)",
            "one family sent two slips, a week apart; the later one switches the photo release to yes and was scanned before the earlier one (checks: photo release; date signed)",
            "one roster student returned nothing and still needs a row with no in the yes/no columns (checks: one row per roster student; permission and signature)",
            "a signed slip for a Room 2 sibling of a Room 4 student is in the stack and is not on the roster (checks: row count; other-class slip left out)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "consents.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per roster student", "path": "consents.csv", "column": "student_id", "ref": "consents.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "consents.csv", "equals_ref": "consents.csv"},
            {"type": "csv_values_match", "name": "student and guardian names", "path": "consents.csv", "ref": "consents.csv", "key": "student_id",
             "columns": ["student_name", "guardian_name"], "normalize": ["alnum"], "min_accuracy": 1.0,
             "must_match_keys": [ids[1], ids[2], ids[3], ids[7], ids[8]]},
            {"type": "csv_values_match", "name": "guardian phone", "path": "consents.csv", "ref": "consents.csv", "key": "student_id",
             "columns": ["guardian_phone"], "normalize": ["digits"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "permission and signature", "path": "consents.csv", "ref": "consents.csv", "key": "student_id",
             "columns": ["form_returned", "permission", "signed"], "min_accuracy": 1.0, "must_match_keys": [ids[4], ids[5], ids[9]]},
            {"type": "csv_values_match", "name": "photo release", "path": "consents.csv", "ref": "consents.csv", "key": "student_id",
             "columns": ["photo_release"], "min_accuracy": 1.0, "must_match_keys": [ids[5], ids[6]]},
            {"type": "csv_values_match", "name": "date signed", "path": "consents.csv", "ref": "consents.csv", "key": "student_id",
             "columns": ["date_signed"], "min_accuracy": 1.0, "must_match_keys": [ids[5], ids[6]]},
            {"type": "text_not_contains", "name": "other-class slip left out", "path": "consents.csv", "phrases": [sib["first"]]},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
