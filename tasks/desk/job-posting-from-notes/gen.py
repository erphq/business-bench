#!/usr/bin/env python3
"""job-posting-from-notes: a physio clinic's hiring kickoff notes and email thread to a front desk job posting.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * the manager's kickoff notes guess an hourly rate; HR's email gives the approved range, which the law says the
    posting must carry                                                           (check: pay range)
  * last year's posting sits in the folder with an older range, the downtown address and the Spanish requirement
                                                                                 (checks: pay range; old addresses left out; language requirement withdrawn)
  * the kickoff notes say Monday to Friday daytime; the manager's later email moves the role to Tuesday to Saturday
    evenings                                                                     (checks: schedule days; schedule hours)
  * the owner withdraws the Spanish requirement and says not to mention language at all (check: language requirement withdrawn)
  * Northside moved: the notes say the Ridge Rd suite, the email gives the new building's address (checks: clinic address; old addresses left out)
  * CPR certification can be earned after hire; last year's posting required it up front (check: CPR timing)
  * the application address and deadline come from HR's email                   (check: how to apply)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CLINIC = "Riverbend Physio"
DOMAIN = "riverbendphysio.com"

def build(seed: int) -> dict:
    r = rng(seed)
    lo, hi = r.choice([(20.00, 23.50), (21.00, 24.50), (19.50, 23.00)])
    guess = hi - 2.0
    old_lo, old_hi = lo - 2.0, hi - 2.5
    start_h, end_h = r.choice([("10:00", "6:30"), ("11:00", "7:30"), ("9:30", "6:00")])
    new_no = r.choice([4410, 4630, 5120]); old_no = r.choice([2250, 2380, 2715]); down_no = r.choice([118, 126, 212])
    deadline = date(2026, 10, r.choice([9, 12, 16]))
    cpr_days = r.choice([60, 90])
    mgr, hr, owner = (f"{a} {b}" for a, b in people(r, 3))
    return dict(lo=lo, hi=hi, guess=guess, old_lo=old_lo, old_hi=old_hi, start_h=start_h, end_h=end_h, new_no=new_no, old_no=old_no,
                down_no=down_no, deadline=deadline, cpr_days=cpr_days, mgr=mgr, hr=hr, owner=owner)

def pr(x: float) -> str: return f"${x:,.2f}"

def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    M, H, O = d["mgr"].split()[0], d["hr"].split()[0], d["owner"]
    dl = d["deadline"].strftime("%B %-d, %Y")
    write_text(os.path.join(ws, "hiring_kickoff_notes.txt"),
        f"HIRING KICKOFF - Front Desk Patient Coordinator\nAug 28, 2026 - notes by {M}\n\n"
        "Role: Front Desk Patient Coordinator, full-time, Northside clinic\n"
        f"Where: Northside - our suite at {d['old_no']} Ridge Rd, Tacoma\n"
        "Start: mid October\n\n"
        "What they do:\n- check patients in and out, answer phones\n- schedule and reschedule visits in WebPT\n"
        "- verify insurance benefits before first visits\n- collect copays and balances\n\n"
        "Must have:\n- at least 1 year front desk or reception experience, ideally healthcare\n- comfortable with insurance verification (we will train on our payers)\n"
        "- bilingual Spanish/English REQUIRED\n"
        f"- CPR/BLS - fine if they get it within {d['cpr_days']} days of hire, we pay for the class\n\n"
        "Schedule: Mon-Fri 8:00-4:30\n"
        f"Pay: around {pr(d['guess'])}/hr, a bit more for someone great\n")
    write_email_thread(os.path.join(ws, "email_thread_front_desk_posting.txt"), [
        {"from": f"{d['hr']} <{H.lower()}@{DOMAIN}>", "to": f"{d['mgr']} <{M.lower()}@{DOMAIN}>", "date": "Wed, 2 Sep 2026 10:15", "subject": "front desk coordinator - approved",
         "body": (f"The Front Desk Patient Coordinator requisition is approved. The approved pay range is {pr(d['lo'])} to {pr(d['hi'])} per hour, depending on experience. "
                  "Washington's pay transparency law means the posting has to show the range, so please don't post a single number.\n\n"
                  "Benefits to list: medical and dental, 401(k) with a 3% match, 10 days PTO plus paid holidays.\n\n"
                  f"Applications go to jobs@{DOMAIN} with a resume. Close the posting on {dl}.\n\n{H}")},
        {"from": f"{d['mgr']} <{M.lower()}@{DOMAIN}>", "to": f"{d['hr']} <{H.lower()}@{DOMAIN}>, {O} <owner@{DOMAIN}>", "date": "Fri, 4 Sep 2026 16:40", "subject": "RE: front desk coordinator - approved",
         "body": (f"Thanks {H}. One change from my kickoff notes: this person will cover our new evening and Saturday hours, so the schedule is Tuesday through Saturday, "
                  f"{d['start_h']} a.m. to {d['end_h']} p.m. And Northside is moving before they start - the posting should give the new building, "
                  f"{d['new_no']} Ridge Rd, Tacoma, not the old suite at {d['old_no']}.\n\n{M}")},
        {"from": f"{O} <owner@{DOMAIN}>", "to": f"{d['mgr']} <{M.lower()}@{DOMAIN}>, {d['hr']} <{H.lower()}@{DOMAIN}>", "date": "Sun, 6 Sep 2026 21:03", "subject": "RE: front desk coordinator - approved",
         "body": ("Please take the Spanish requirement out. We already have two bilingual people at Northside and I don't want to scare off good applicants. "
                  "Don't mention language at all in the posting.\n\nOtherwise looks good.")}])
    write_text(os.path.join(ws, "posting_2024_front_desk.md"),
        f"# Front Desk Coordinator - {CLINIC} Downtown\n\n**Location:** {d['down_no']} Main St, Tacoma, WA\n**Schedule:** Monday-Friday, 8:00 a.m.-4:30 p.m.\n"
        f"**Pay:** {pr(d['old_lo'])}-{pr(d['old_hi'])} per hour\n\n"
        "## About the role\n\nBe the first friendly face our patients see. You'll check patients in, schedule visits and keep the front desk running smoothly.\n\n"
        "## Requirements\n\n- 1+ year of front desk experience in a healthcare setting\n- Bilingual English/Spanish required\n- Current CPR certification required\n\n"
        f"## To apply\n\nSend your resume to careers@{DOMAIN}.\n")

    posting = f"""# Front Desk Patient Coordinator - {CLINIC} Northside

**Location:** {d['new_no']} Ridge Rd, Tacoma, WA
**Schedule:** Full-time, Tuesday through Saturday, {d['start_h']} a.m. to {d['end_h']} p.m.
**Pay:** {pr(d['lo'])} to {pr(d['hi'])} per hour, depending on experience

## About the role

You'll be the first person our patients meet at {CLINIC} Northside. You check patients in and out, answer the phones, schedule and reschedule visits in WebPT, verify insurance benefits before first visits, and collect copays and balances.

## What you bring

- At least 1 year of front desk or reception experience, ideally in healthcare
- Comfort with insurance verification (we train you on our payers)
- CPR/BLS certification within {d['cpr_days']} days of hire; we pay for the class

## Benefits

- Medical and dental
- 401(k) with a 3% match
- 10 days PTO plus paid holidays

## How to apply

Email your resume to jobs@{DOMAIN} by {dl}.
"""
    write_text(os.path.join(sol, "posting.md"), posting)
    write_json(os.path.join(ref, "notes.json"), {k: (v.isoformat() if isinstance(v, date) else v) for k, v in d.items()})

    def money_rx(x: float) -> str:
        whole = int(x); cents = round((x - whole) * 100)
        body = f"{whole}\\.{cents:02d}" if cents else f"{whole}(\\.00)?"
        return rf"(?<![\d.,]){body}(?!\d|,\d|\.\d)"
    sh, eh = d["start_h"], d["end_h"]
    mon = d["deadline"].strftime("%B").lower()
    write_task_yaml(HERE, {
        "id": "job-posting-from-notes", "track": "desk", "category": "drafting",
        "title": "Write the front desk coordinator job posting",
        "ask": f"Can you write the job posting for the Northside front desk coordinator from {M}'s kickoff notes and the email thread? Save it as posting.md so I can put it up this week.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"{M}'s kickoff notes say around {pr(d['guess'])} an hour; HR's email gives the approved range {pr(d['lo'])} to {pr(d['hi'])} and says the posting must show a range (check: pay range)",
            f"last year's downtown posting is in the folder with {pr(d['old_lo'])}-{pr(d['old_hi'])}, {d['down_no']} Main St, Monday-Friday hours and a Spanish requirement (checks: pay range; old addresses left out; language requirement withdrawn)",
            f"the kickoff notes say Mon-Fri 8:00-4:30; {M}'s later email moves the role to Tuesday through Saturday, {sh} a.m. to {eh} p.m. (checks: schedule days; schedule hours)",
            "the owner withdraws the Spanish requirement and asks that language not be mentioned at all (check: language requirement withdrawn)",
            f"the kickoff notes give Northside's old suite at {d['old_no']} Ridge Rd; the email says the posting should give the new building at {d['new_no']} Ridge Rd (checks: clinic address; old addresses left out)",
            f"CPR/BLS can be earned within {d['cpr_days']} days of hire; last year's posting required current certification (check: CPR timing)",
            f"the application email and the {dl} closing date are only in HR's email (check: how to apply)",
        ],
        "checks": [
            {"type": "text_sentence_matches", "name": "pay range", "path": "posting.md",
             "all": [money_rx(d["lo"]), money_rx(d["hi"]), r"(hour|\bhr\b|hourly)"], "none": [money_rx(d["guess"]), money_rx(d["old_lo"])]},
            {"type": "text_sentence_matches", "name": "schedule days", "path": "posting.md",
             "all": [r"\btue(s|sday)?\b", r"\bsat(urday)?\b"], "none": [r"\bmon(day)?\b\s*(-|–|—|to|through|thru)\s*\bfri"]},
            {"type": "custom", "name": "schedule hours", "module": "check.py"},
            {"type": "text_sentence_matches", "name": "clinic address", "path": "posting.md", "all": [rf"\b{d['new_no']}\s+ridge"]},
            {"type": "text_not_contains", "name": "old addresses left out", "path": "posting.md", "phrases": [f"{d['old_no']} Ridge", f"{d['down_no']} Main"]},
            {"type": "text_not_contains", "name": "language requirement withdrawn", "path": "posting.md", "phrases": ["spanish", "bilingual"]},
            {"type": "text_sentence_matches", "name": "CPR timing", "path": "posting.md",
             "all": [r"\b(cpr|bls)\b", rf"(?<![\d.,]){d['cpr_days']}(?!\d)", r"\bdays?\b"]},
            {"type": "text_sentence_matches", "name": "how to apply", "path": "posting.md",
             "all": [rf"jobs@{DOMAIN.replace('.', '[.]')}", rf"({mon}|{mon[:3]}\.?)\s+{d['deadline'].day}(st|nd|rd|th)?\b|\b{d['deadline'].day}(st|nd|rd|th)?\s+(of\s+)?{mon[:3]}|\b10/{d['deadline'].day}\b|2026-10-{d['deadline'].day:02d}|\b{mon[:3]}\.$"]},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
