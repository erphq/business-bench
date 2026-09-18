#!/usr/bin/env python3
"""policy-update-memo: a moving company's 2025 crew policies, the final 2026 policies, an earlier 2026 draft and the
owner's email become a staff memo listing what changed.

    python gen.py [--seed N]

Business: a local and long-distance moving company with a dozen crews. The office rewrote the crew policies; the
owner wants one memo to all crews that says what is different.

Traps (each caught by a check, see task.yaml):
  * five things really changed (overtime approval, per diem, tips, mileage, damage reporting); each must be stated
    with its new rule                                      (checks: overtime approval; per diem; tip split; mileage; damage reporting)
  * the phone-use-while-driving clause moved from the end of the handbook to section 2 with identical wording, so a
    section-by-section comparison reports it as removed and added; it is not a change  (check: moved clause and effective date)
  * the 2026 draft v1 in the folder carries different numbers (90 minutes, $60, $0.67, two hours) that the owner did
    not approve                                            (checks: overtime approval; per diem; mileage; damage reporting)
  * the final PDF says effective October 1, 2026; the owner's email moves it to November 1 so payroll can load the
    new rates and says the memo must give November 1       (check: moved clause and effective date)
  * every section after the first is renumbered, so matching by section number pairs unrelated rules  (check: moved clause and effective date)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

COMPANY = "Keel & Crate Movers"
DOMAIN = "keelandcrate.com"
PDF_EFFECTIVE = date(2026, 10, 1)
EFFECTIVE = date(2026, 11, 1)


def build(seed: int) -> dict:
    r = rng(seed * 19 + 7)
    ppl, firsts = [], set()
    while len(ppl) < 3:
        f, l = person(r)
        if f not in firsts:
            firsts.add(f); ppl.append((f, l))
    P = {k: {"first": f, "last": l, "full": f"{f} {l}"} for k, (f, l) in zip(["owner", "office", "dispatch"], ppl)}
    old_pd, new_pd, draft_pd = r.choice([(45, 55, 60), (40, 55, 50), (45, 60, 55)])
    old_mi, new_mi, draft_mi = r.choice([("0.58", "0.70", "0.67"), ("0.55", "0.68", "0.72"), ("0.60", "0.72", "0.67")])
    boots = r.choice([120, 150])
    return dict(P=P, old_pd=old_pd, new_pd=new_pd, draft_pd=draft_pd, old_mi=old_mi, new_mi=new_mi, draft_mi=draft_mi, boots=boots)


def sections(d: dict, version: str) -> list[tuple[str, str]]:
    """version: old | new | draft. Returns ordered (heading, text)."""
    ot = {"old": "2 hours", "new": "1 hour", "draft": "90 minutes"}[version]
    pd = {"old": d["old_pd"], "new": d["new_pd"], "draft": d["draft_pd"]}[version]
    mi = {"old": d["old_mi"], "new": d["new_mi"], "draft": d["draft_mi"]}[version]
    tips = ("Cash and card tips are pooled for each job and split equally among the crew members who worked that job."
            if version == "old" else
            "Cash and card tips are pooled for each job and split among the crew members who worked that job in proportion to the hours each of them worked on it.")
    dmg = {"old": "Report any damage to a customer's property or belongings to the dispatcher within 24 hours of finishing the job, with photos.",
           "new": "Report any damage to a customer's property or belongings to your crew lead and the dispatcher before the crew leaves the customer's home, with photos.",
           "draft": "Report any damage to a customer's property or belongings to the dispatcher within two hours of finishing the job, with photos."}[version]
    clock = ("Crews clock in at the yard on the tablet by the dispatch window and clock out there at the end of the day. "
             "Travel time from the yard to the first job and back from the last job is paid time.")
    phone = ("Drivers may not hold or use a phone while the truck is moving. Set navigation before leaving the yard or the job; "
             "the crew member riding in the cab handles calls and texts.")
    ovt = (f"Overtime must be approved by the dispatcher before a crew works more than {ot} past the scheduled end of a job. "
           "Call dispatch as soon as it is clear the job will run over.")
    perdiem = (f"Crew members on overnight long-distance jobs receive a per diem of ${pd} for each night away from home, paid with the next payroll. "
               "The company books and pays for lodging directly.")
    mileage = (f"If dispatch asks you to drive your own vehicle to a job site or to pick up supplies, the company reimburses ${mi} per mile. "
               "Log the trip on the mileage sheet the same week.")
    uniform = "Company shirts must be worn on every job. Each crew member is issued three shirts a year and one jacket every two years."
    boots = f"Steel- or composite-toe boots are required on every job. The company reimburses up to ${d['boots']} per calendar year with a receipt."
    base = [("Clocking in and out", clock), ("Overtime", ovt), ("Long-distance per diem", perdiem), ("Tips", tips),
            ("Using your own vehicle", mileage), ("Damage to customer property", dmg), ("Uniforms", uniform), ("Safety boots", boots)]
    phone_sec = ("Phone use while driving", phone)
    if version == "old":
        return base + [phone_sec]
    return [base[0], phone_sec] + base[1:]


def emit(seed: int) -> None:
    d = build(seed)
    P = d["P"]
    ws, ref, sol = task_dirs(HERE)
    # ---- old handbook (markdown)
    old = sections(d, "old")
    md = [f"# {COMPANY} - Crew Policies", "", "_Revised March 2025. Effective March 1, 2025._", ""]
    for i, (h, t) in enumerate(old, 1):
        md += [f"## {i}. {h}", "", t, ""]
    write_text(os.path.join(ws, "crew_policies_2025.md"), "\n".join(md))
    # ---- final 2026 PDF
    new = sections(d, "new")
    blocks = [("title", f"{COMPANY}"), ("h", "Crew Policies 2026"), ("small", f"Final, approved by {P['owner']['full']}, August 28, 2026"),
              ("right", f"Effective: {PDF_EFFECTIVE.strftime('%B %-d, %Y')}"), ("hr", None)]
    for i, (h, t) in enumerate(new, 1):
        blocks += [("h", f"{i}. {h}"), ("p", t)]
    write_pdf_document(os.path.join(ws, "crew_policies_2026_FINAL.pdf"), blocks, font="Times-Roman", base_size=11)
    # ---- draft v1 PDF
    draft = sections(d, "draft")
    blocks = [("title", "DRAFT v1 - for review"), ("small", f"{COMPANY} crew policies 2026 - circulated July 14, 2026 - not approved"), ("hr", None)]
    for i, (h, t) in enumerate(draft, 1):
        blocks += [("h", f"{i}. {h}"), ("p", t)]
    write_pdf_document(os.path.join(ws, "crew_policies_2026_draft_v1.pdf"), blocks, font="Helvetica", base_size=10, pagesize="a4")
    # ---- owner's email
    write_email_thread(os.path.join(ws, "email_from_owner.txt"), [
        {"from": f"{P['office']['full']} <{P['office']['first'].lower()}@{DOMAIN}>", "to": f"{P['owner']['full']} <{P['owner']['first'].lower()}@{DOMAIN}>",
         "date": "Fri, 28 Aug 2026 15:10", "subject": "Crew policies 2026 - final",
         "body": "Final version attached with your edits from this morning, effective October 1 as we discussed.\n\n" + P['office']['first']},
        {"from": f"{P['owner']['full']} <{P['owner']['first'].lower()}@{DOMAIN}>", "to": f"{P['office']['first'].lower()}@{DOMAIN}",
         "date": "Thu, 10 Sep 2026 18:02", "subject": "RE: Crew policies 2026 - final",
         "body": ("Change of plan on the start date. Payroll can't load the new per diem and mileage rates before the October 1 run, so the new policies "
                  "take effect November 1, 2026 instead. I'm not reprinting the PDF for one date, so the memo to the crews has to give November 1.\n\n"
                  "The memo should go to every crew and tell them what's actually different from last year's policies, in plain words, "
                  "so nobody has to read both documents side by side.\n\n" + P['owner']['first'])},
    ])

    facts = {"effective": EFFECTIVE.isoformat(), "pdf_effective": PDF_EFFECTIVE.isoformat(), "new_pd": d["new_pd"], "draft_pd": d["draft_pd"],
             "new_mi": d["new_mi"], "draft_mi": d["draft_mi"]}
    write_json(os.path.join(ref, "facts.json"), facts)
    memo = (f"# Memo: changes to crew policies\n\n"
            f"To: All crews\nFrom: {P['owner']['full']}\nDate: September 14, 2026\n\n"
            f"Our updated crew policies take effect on November 1, 2026. Most of the handbook is the same as last year. These are the five things that changed:\n\n"
            f"1. **Overtime approval.** You now need the dispatcher's approval before working more than 1 hour past a job's scheduled end. Last year the limit was 2 hours.\n"
            f"2. **Per diem.** The per diem for overnight long-distance jobs goes up from ${d['old_pd']} to ${d['new_pd']} per night away.\n"
            f"3. **Tips.** Pooled tips are no longer split equally; each crew member's share is in proportion to the hours they worked on the job.\n"
            f"4. **Mileage.** When dispatch asks you to drive your own vehicle, reimbursement goes up from ${d['old_mi']} to ${d['new_mi']} per mile.\n"
            f"5. **Damage reporting.** Report damage to your crew lead and the dispatcher, with photos, before the crew leaves the customer's home. "
            f"It used to be within 24 hours of finishing the job.\n\n"
            "The rule on phone use while driving has moved to section 2 of the handbook, but its wording has not changed. "
            "Clocking in and out, uniforms and safety boots are unchanged.\n\n"
            "Questions go to the office.\n")
    write_text(os.path.join(sol, "memo.md"), memo)

    nm = lambda x: x.replace(".", r"\.")
    write_task_yaml(HERE, {
        "id": "policy-update-memo", "track": "desk", "category": "drafting",
        "title": "Memo to the crews on the 2026 policy changes",
        "ask": (f"We've rewritten the crew policies for 2026. Please write the memo that goes to all the crews telling them what changed - "
                f"both versions are in the folder and {P['owner']['first']}'s email has the notes. Save it as memo.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "five rules really changed (overtime approval 2 hours to 1 hour, per diem, tips split by hours, mileage rate, damage reported before leaving the home); each must be stated with its new rule (checks: overtime approval; per diem; tip split; mileage; damage reporting)",
            "the phone-use-while-driving clause moved from section 9 to section 2 with identical wording, so a section-by-section comparison reports it as removed and added (check: moved clause and effective date)",
            f"the 2026 draft v1 in the folder carries unapproved numbers (90 minutes, ${d['draft_pd']} per diem, ${d['draft_mi']} a mile, two hours for damage reports) (checks: overtime approval; per diem; mileage; damage reporting)",
            "the final PDF says effective October 1, 2026; the owner's later email moves it to November 1 and says the memo must give November 1 (check: moved clause and effective date)",
            "every section after the first is renumbered in the 2026 version, so matching by section number pairs unrelated rules (check: moved clause and effective date)",
        ],
        "checks": [
            {"type": "file_exists", "name": "memo.md exists", "path": "memo.md"},
            {"type": "text_sentence_matches", "name": "overtime approval", "path": "memo.md",
             "all": [r"overtime|past (the|a) (job'?s )?scheduled end|runs? over|approv", r"(\b1\b|\bone\b|\ban\b)[\s-]*hours?\b|\b60[\s-]*min"],
             "none": [r"\b90[\s-]*min|\b1\.5[\s-]*hours?|hour and a half"]},
            {"type": "text_sentence_matches", "name": "per diem", "path": "memo.md",
             "all": [r"per[\s-]?diem|overnight|night away|daily allowance", rf"\$\s?{d['new_pd']}\b"], "none": [rf"\$\s?{d['draft_pd']}\b"]},
            {"type": "text_sentence_matches", "name": "tip split", "path": "memo.md",
             "all": [r"\btip", r"hours|proportion|pro[\s-]?rat"]},
            {"type": "text_sentence_matches", "name": "mileage", "path": "memo.md",
             "all": [r"mile|own (vehicle|car)|personal (vehicle|car)", rf"(\$\s?0?{nm(d['new_mi'][1:])}\b|\b{d['new_mi'][2:]}\s*(cents|¢))"],
             "none": [rf"(0?{nm(d['draft_mi'][1:])}\b|\b{d['draft_mi'][2:]}\s*(cents|¢))"]},
            {"type": "text_sentence_matches", "name": "damage reporting", "path": "memo.md",
             "all": [r"damage", r"before (you |the crew |crews |we |they |your crew )?(leav|depart|go)|while (you are |the crew is |still )?(at|on site|in the)|on[\s-]?site"],
             "none": [r"\b(2|two)\s*hours"]},
            {"type": "custom", "name": "moved clause and effective date", "module": "check.py"},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
