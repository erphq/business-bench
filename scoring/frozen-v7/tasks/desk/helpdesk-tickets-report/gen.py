#!/usr/bin/env python3
"""helpdesk-tickets-report: a month of internal IT helpdesk tickets to tickets per category and SLA breaches.

    python gen.py [--seed N] [--naive DIR]

Business: the IT team at a title company (about 120 staff). The ops meeting wants May's ticket volume by
category and how many tickets missed their resolution target. The export is raw; the rules are in the
2026 service-level policy and in Gwen's email.

Traps (each caught by a check, see task.yaml):
  * priorities are spelled nine ways (P1, Urgent, 1 - Critical, Hi, Medium, ...)       (check: total SLA breaches)
  * targets are business hours (Mon-Fri 08:00-18:00, clock starts at the next opening) (checks: Network breaches; total breaches)
  * Memorial Day (25 May) is a company holiday; the clock does not run                  (check: Network breaches)
  * an open ticket already past its target at export time is a breach                  (check: total SLA breaches)
  * Merged and Spam tickets are not tickets; late-April tickets resolved in May are not May tickets
                                                                                        (checks: Email tickets; total tickets)
  * the 2024 policy (08:00-17:00, P3 16 hours) is still in the folder                   (check: total SLA breaches)
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from datetime import date, datetime, time, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CATEGORIES = ["Hardware", "Software", "Network", "Accounts & Access", "Email", "Printers"]
CAT_WEIGHT = [0.20, 0.22, 0.13, 0.20, 0.15, 0.10]
CAT_BREACH = {"Hardware": 0.16, "Software": 0.12, "Network": 0.24, "Accounts & Access": 0.08, "Email": 0.10, "Printers": 0.18}
PRIOS = ["P1", "P2", "P3", "P4"]
PRIO_WEIGHT = [0.08, 0.22, 0.50, 0.20]
TARGET = {"P1": 4, "P2": 8, "P3": 24, "P4": 40}
OLD_TARGET = {"P1": 4, "P2": 8, "P3": 16, "P4": 40}
SPELLINGS = {"P1": ["P1", "Urgent", "1 - Critical", "URGENT", "Critical"],
             "P2": ["P2", "High", "2 - High", "Hi", "high"],
             "P3": ["P3", "Normal", "3 - Normal", "Medium", "med"],
             "P4": ["P4", "Low", "4 - Low", "low"]}
OFFICIAL = {"p1": "P1", "critical": "P1", "1 - critical": "P1", "p2": "P2", "high": "P2", "2 - high": "P2",
            "p3": "P3", "normal": "P3", "3 - normal": "P3", "p4": "P4", "low": "P4", "4 - low": "P4"}
HOLIDAYS = {date(2026, 5, 25)}
EXPORT_AT = datetime(2026, 6, 1, 7, 45)
SUBJECTS = {
    "Hardware": ["Laptop will not boot", "Docking station not detecting monitors", "Keyboard keys sticking", "New monitor request",
                 "Laptop battery swelling", "Webcam not working in Teams", "Scanner at closing desk dead"],
    "Software": ["Excel crashes opening closing statements", "Adobe license expired", "SoftPro slow to load", "Install DocuSign plugin",
                 "Windows update stuck", "Outlook add-in missing", "Title plant search errors"],
    "Network": ["VPN drops every few minutes", "Wi-Fi down in conference room B", "Branch office cannot reach file server",
                "Slow internet at Eastside branch", "Cannot map S: drive", "Firewall blocking county recorder site"],
    "Accounts & Access": ["Password reset", "New hire account setup", "MFA device replaced", "Access to escrow share",
                          "Locked out after vacation", "Offboarding - disable account"],
    "Email": ["Phishing email reported", "Shared mailbox not syncing", "Cannot send attachments over 10MB", "Calendar invites missing",
              "Distribution list update", "Out of office not working"],
    "Printers": ["Check printer jammed", "Toner low 2nd floor", "Printer offline in closing room", "Scan to folder failing"],
}
TECHS = ["Gwen Adeyemi", "Luis Ortiz", "Priya Shah", "Tom Becker"]


# --------------------------------------------------------------------------- business-hours clock

def _bday(d: date, holidays=HOLIDAYS) -> bool:
    return d.weekday() < 5 and d not in holidays


def bh_between(a: datetime, b: datetime, open_h=8, close_h=18, holidays=HOLIDAYS) -> float:
    if b <= a:
        return 0.0
    total, d = 0.0, a.date()
    while d <= b.date():
        if _bday(d, holidays):
            s = max(a, datetime.combine(d, time(open_h)))
            e = min(b, datetime.combine(d, time(close_h)))
            if e > s:
                total += (e - s).total_seconds() / 3600
        d += timedelta(days=1)
    return total


def add_bh(a: datetime, hours: float) -> datetime:
    cur, left = a, hours * 60.0
    while True:
        if not _bday(cur.date()) or cur.time() >= time(18):
            nd = cur.date() + timedelta(days=1)
            while not _bday(nd):
                nd += timedelta(days=1)
            cur = datetime.combine(nd, time(8))
            continue
        if cur.time() < time(8):
            cur = datetime.combine(cur.date(), time(8))
        avail = (datetime.combine(cur.date(), time(18)) - cur).total_seconds() / 60
        if left <= avail:
            return cur + timedelta(minutes=left)
        left -= avail
        cur = datetime.combine(cur.date(), time(18))


def _minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


# --------------------------------------------------------------------------- draw

def build(seed: int) -> dict:
    r = rng(seed)
    tickets = []

    def created_in(start: date, end: date) -> datetime:
        d = day_in(r, start, end)
        if _bday(d) and r.random() < 0.82:
            return datetime(d.year, d.month, d.day, r.randint(8, 17), r.randint(0, 59), r.randint(0, 59))
        if d.weekday() < 5:
            h = r.choice([6, 7, 18, 19, 20, 21])
        else:
            h = r.randint(9, 20)
        return datetime(d.year, d.month, d.day, h, r.randint(0, 59), r.randint(0, 59))

    def new(cat, prio, created, status, resolved, kind):
        t = {"cat": cat, "prio": prio, "created": created, "status": status, "resolved": resolved, "kind": kind,
             "spelling": r.choice(SPELLINGS[prio]), "subject": r.choice(SUBJECTS[cat]), "tech": r.choice(TECHS),
             "requester": " ".join(person(r))}
        tickets.append(t)
        return t

    # ordinary May tickets, resolved
    for _ in range(r.randint(236, 252)):
        cat = r.choices(CATEGORIES, CAT_WEIGHT)[0]
        prio = r.choices(PRIOS, PRIO_WEIGHT)[0]
        created = created_in(date(2026, 5, 1), date(2026, 5, 27))
        tgt = TARGET[prio]
        if prio == "P1" and not (_bday(created.date()) and time(8) <= created.time() < time(18)) and r.random() < 0.5:
            resolved = _minute(created + timedelta(minutes=r.randint(35, 150)))   # on-call fixed it the same evening
        else:
            ratio = r.uniform(1.15, 2.6) if r.random() < CAT_BREACH[cat] else r.uniform(0.06, 0.88)
            resolved = _minute(add_bh(created, tgt * ratio))
        new(cat, prio, created, r.choice(["Resolved", "Resolved", "Closed"]), resolved, "may")
    # the holiday weekend: Network tickets opened Friday 22 May, fixed Tuesday 26 May - inside target only if the clock skips Monday
    for prio, c_h, c_m, r_h, r_m in [("P1", 16, 31, 9, 42), ("P2", 13, 52, 11, 20), ("P2", 15, 5, 13, 35)]:
        new("Network", prio, datetime(2026, 5, 22, c_h, c_m, r.randint(0, 59)), "Resolved", datetime(2026, 5, 26, r_h, r_m), "may")
    # still open at export
    for _ in range(12):
        cat = r.choices(CATEGORIES, CAT_WEIGHT)[0]
        prio = r.choices(PRIOS, [0.06, 0.24, 0.45, 0.25])[0]
        created = created_in(date(2026, 5, 14), date(2026, 5, 29))
        new(cat, prio, created, r.choice(["Open", "Pending - waiting on user", "In progress"]), None, "may")
    # merged duplicates and spam: not tickets
    for i in range(9):
        cat = "Email" if i < 3 else r.choices(CATEGORIES, CAT_WEIGHT)[0]
        created = created_in(date(2026, 5, 1), date(2026, 5, 29))
        new(cat, r.choices(PRIOS, PRIO_WEIGHT)[0], created, "Merged", _minute(created + timedelta(minutes=r.randint(5, 90))), "merged")
    for _ in range(6):
        created = created_in(date(2026, 5, 1), date(2026, 5, 29))
        t = new("Email", "P3", created, "Spam", _minute(created + timedelta(minutes=r.randint(2, 40))), "spam")
        t["subject"] = r.choice(["You have (3) undelivered messages", "Invoice #88213 attached", "RE: wire instructions update", "Your mailbox is full"])
    # late-April tickets resolved in May: in the export because they were updated in May
    for i in range(10):
        cat = "Email" if i < 2 else r.choices(CATEGORIES, CAT_WEIGHT)[0]
        prio = r.choices(PRIOS, PRIO_WEIGHT)[0]
        created = created_in(date(2026, 4, 27), date(2026, 4, 30))
        resolved = _minute(add_bh(datetime(2026, 5, 1, 8, 0), r.uniform(0.3, 26.0)))
        new(cat, prio, created, "Closed", resolved, "april")

    tickets.sort(key=lambda t: t["created"])
    for i, t in enumerate(tickets):
        t["id"] = f"INC-{20411 + i}"
    for t in tickets:
        end = t["resolved"] or EXPORT_AT
        t["elapsed"] = round(bh_between(t["created"], end), 2)
        t["breach"] = t["elapsed"] > TARGET[t["prio"]]
        t["counted"] = t["kind"] == "may"
    return {"tickets": tickets}


def summarize(tickets, counted=lambda t: t["counted"], breach=lambda t: t["breach"]) -> dict:
    out = {c: [0, 0] for c in CATEGORIES}
    for t in tickets:
        if counted(t):
            out[t["cat"]][0] += 1
            out[t["cat"]][1] += 1 if breach(t) else 0
    out["_total"] = [sum(out[c][0] for c in CATEGORIES), sum(out[c][1] for c in CATEGORIES)]
    return out


def variants(d: dict) -> dict:
    T = d["tickets"]
    may = lambda t: t["counted"]
    cal = lambda t: ((t["resolved"] or EXPORT_AT) - t["created"]).total_seconds() / 3600 > TARGET[t["prio"]]
    no_hol = lambda t: bh_between(t["created"], t["resolved"] or EXPORT_AT, holidays=set()) > TARGET[t["prio"]]
    no_open = lambda t: t["breach"] and t["resolved"] is not None
    naive_p = lambda t: t["elapsed"] > TARGET[OFFICIAL.get(t["spelling"].lower(), "P3")]
    old = lambda t: bh_between(t["created"], t["resolved"] or EXPORT_AT, close_h=17) > OLD_TARGET[t["prio"]]
    return {"calendar": summarize(T, may, cal), "holiday": summarize(T, may, no_hol), "open": summarize(T, may, no_open),
            "spelling": summarize(T, may, naive_p), "old_policy": summarize(T, may, old),
            "all_rows": summarize(T, lambda t: True)}


def acceptable(d: dict) -> bool:
    T = d["tickets"]
    s = summarize(T)
    v = variants(d)
    # nothing sits on the edge of its target
    if any(abs(t["elapsed"] - TARGET[t["prio"]]) < 0.1 for t in T if t["counted"]):
        return False
    tot_t, tot_b = s["_total"]
    for k in ("calendar", "holiday", "open", "spelling", "old_policy"):
        if v[k]["_total"][1] == tot_b:
            return False
    if v["calendar"]["Network"][1] == s["Network"][1] or v["holiday"]["Network"][1] == s["Network"][1]:
        return False
    if v["all_rows"]["Email"][0] == s["Email"][0] or v["all_rows"]["_total"][0] == tot_t:
        return False
    # open tickets: some already breached, some not yet due
    opens = [t for t in T if t["resolved"] is None]
    if not (2 <= sum(t["breach"] for t in opens) <= len(opens) - 3):
        return False
    # pinned counts distinct on their rows and away from the policy's target hours
    for a, b in (s["Network"], s["Email"], s["_total"]):
        if a == b or a in TARGET.values() or b in TARGET.values() or b < 5:
            return False
    if s["Email"][0] in (s["Network"][1],) or tot_b in [s[c][0] for c in CATEGORIES]:
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def report_workbook(rows: list[list]) -> dict:
    """rows: [ticket_id, category, priority, created, resolved, status, target_h, business_h, breached, counted]"""
    n = len(rows) + 1
    summ = []
    for i, c in enumerate(CATEGORIES, start=2):
        summ.append([c, f"=COUNTIFS(Tickets!$B$2:$B${n},$A{i},Tickets!$J$2:$J${n},1)",
                     f"=SUMIFS(Tickets!$I$2:$I${n},Tickets!$B$2:$B${n},$A{i},Tickets!$J$2:$J${n},1)",
                     f'=IF(B{i}=0,0,ROUND(C{i}/B{i},4))'])
    last = len(CATEGORIES) + 1
    summ.append(["Total", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", f'=IF(B{last+1}=0,0,ROUND(C{last+1}/B{last+1},4))'])
    summ.append([])
    summ.append(["Priority", "Tickets", "SLA breaches", "Target (business hours)"])
    base = len(summ) + 2
    for k, p in enumerate(PRIOS):
        i = base + k
        summ.append([p, f"=COUNTIFS(Tickets!$C$2:$C${n},$A{i},Tickets!$J$2:$J${n},1)",
                     f"=SUMIFS(Tickets!$I$2:$I${n},Tickets!$C$2:$C${n},$A{i},Tickets!$J$2:$J${n},1)", TARGET[p]])
    summ.append([])
    summ.append(["May 2026 tickets by the day they were opened. Merged and Spam tickets and tickets opened in April are left out. "
                 "Targets run in business hours (Mon-Fri 08:00-18:00, not on Memorial Day); an open ticket past its target at "
                 "export (1 June 07:45) is a breach."])
    return {"Summary": {"header": ["Category", "Tickets", "SLA breaches", "Breach rate"], "rows": summ,
                        "widths": {"A": 22, "B": 10, "C": 14, "D": 22}},
            "Tickets": {"header": ["ticket_id", "category", "priority", "created", "resolved", "status", "target_hours",
                                   "business_hours", "breached", "counted"], "rows": rows,
                        "widths": {"B": 18, "D": 20, "E": 20, "F": 24}}}


def memo_text(d: dict) -> str:
    T = d["tickets"]
    s = summarize(T)
    tot_t, tot_b = s["_total"]
    worst = max(CATEGORIES, key=lambda c: (s[c][1] / s[c][0]) if s[c][0] else 0)
    worst_line = (f"- {worst} had the worst breach rate: {s[worst][1]} of {s[worst][0]} tickets.\n" if worst != "Network"
                  else "- Network had the worst breach rate.\n")
    opens = [t for t in T if t["counted"] and t["resolved"] is None and t["breach"]]
    return f"""# Helpdesk, May 2026

We opened {tot_t} tickets in May. {tot_b} tickets breached their SLA ({tot_b / tot_t:.1%}), measured in business hours
under the 2026 policy.

{worst_line}- Network took {s['Network'][0]} tickets with {s['Network'][1]} breaches. The three Network tickets opened on the Friday before
  Memorial Day and fixed on Tuesday morning are inside target, because the clock does not run on the holiday.
- {len(opens)} of the breaches are tickets still open at the export on 1 June that are already past their target:
  {', '.join(t['id'] for t in opens)}.

Merged duplicates, spam, and the late-April tickets that were closed in May are not counted.
"""


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    T = d["tickets"]
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    s = summarize(T)
    tot_t, tot_b = s["_total"]

    # ---- workspace
    write_csv(os.path.join(ws, "helpdesk_tickets_export_2026-06-01.csv"),
              ["Ticket ID", "Subject", "Category", "Priority", "Status", "Created", "Resolved", "Assigned To", "Requester"],
              [[t["id"], t["subject"], t["cat"], t["spelling"], t["status"], fmt_dt(t["created"]),
                fmt_dt(t["resolved"]), t["tech"], t["requester"]] for t in T], bom=True)
    write_text(os.path.join(ws, "IT_service_levels_2026.txt"),
               "Meridian Title - IT service levels\n"
               "Effective 1 January 2026. Replaces the 2024 document.\n\n"
               "1. Priorities\n\n"
               "P1 Critical  - a branch or a closing cannot proceed. The old helpdesk called this Urgent and imported\n"
               "               tickets still show it that way.\n"
               "P2 High      - one person cannot work, or a deadline today is at risk.\n"
               "P3 Normal    - everything else with a workaround. Tickets raised from the web form show Medium.\n"
               "P4 Low       - requests and questions.\n\n"
               "2. Resolution targets\n\n"
               "P1   4 business hours\n"
               "P2   8 business hours\n"
               "P3  24 business hours\n"
               "P4  40 business hours\n\n"
               "3. Business hours\n\n"
               "Monday to Friday, 08:00 to 18:00 local time. The clock only runs inside business hours. A ticket opened\n"
               "in the evening or at the weekend starts its clock when we next open. Company holidays are not business\n"
               "days; in the first half of 2026 those are 1 January, 19 January, 16 February and 25 May (Memorial Day).\n\n"
               "4. What counts as a breach\n\n"
               "A ticket breaches when it is resolved after its target. Time to resolve is measured from Created to\n"
               "Resolved in business hours.\n")
    write_text(os.path.join(ws, "IT_service_levels_2024.txt"),
               "Meridian Title - IT service levels (2024)\n\n"
               "Business hours: Monday to Friday 08:00 to 17:00.\n\n"
               "Targets (business hours): Urgent 4, High 8, Normal 16, Low 40.\n\n"
               "Measured from ticket creation to resolution.\n")
    write_email_thread(os.path.join(ws, "email_from_gwen.txt"), [
        {"from": "Gwen Adeyemi <gwen@meridiantitle.com>", "to": "you", "date": "Mon, 1 Jun 2026 08:05",
         "subject": "May helpdesk numbers for Thursday",
         "body": ("I pulled the ticket export first thing this morning. For the ops meeting I need May's tickets by category "
                  "and how many missed the SLA, using this year's policy.\n\n"
                  "May means tickets opened in May. The export is everything updated during the month, so it also has a few "
                  "April tickets we closed in the first days of May - those were in April's numbers already.\n\n"
                  "Anything with status Merged was a duplicate of another ticket and Spam is spam, neither is a ticket.")},
        {"from": "Gwen Adeyemi <gwen@meridiantitle.com>", "to": "you", "date": "Mon, 1 Jun 2026 08:19",
         "subject": "RE: May helpdesk numbers for Thursday",
         "body": ("One more thing. Some tickets are still open. If one of them is already past its target it has breached, "
                  "whether or not we close it today - count it. If it is not due yet, it has not breached.")}])

    # ---- reference
    write_csv(os.path.join(ref, "category_summary.csv"), ["category", "tickets", "sla_breaches"],
              [[c, s[c][0], s[c][1]] for c in CATEGORIES] + [["Total", tot_t, tot_b]])
    v = variants(d)
    write_json(os.path.join(ref, "notes.json"), {
        "export_time": EXPORT_AT.isoformat(), "total_tickets": tot_t, "total_breaches": tot_b,
        "open_breached": [t["id"] for t in T if t["counted"] and t["resolved"] is None and t["breach"]],
        "holiday_weekend_tickets": [t["id"] for t in T if t["created"].date() == date(2026, 5, 22) and t["cat"] == "Network"
                                    and t["resolved"] and t["resolved"].date() == date(2026, 5, 26)],
        "excluded": {k: sum(1 for t in T if t["kind"] == k) for k in ("merged", "spam", "april")},
        "naive_total_breaches": {k: v[k]["_total"][1] for k in ("calendar", "holiday", "open", "spelling", "old_policy")},
        "naive_total_tickets_all_rows": v["all_rows"]["_total"][0]})

    # ---- reference solution
    rows = [[t["id"], t["cat"], t["prio"], fmt_dt(t["created"]), fmt_dt(t["resolved"]), t["status"], TARGET[t["prio"]],
             t["elapsed"], 1 if t["breach"] else 0, 1 if t["counted"] else 0] for t in T]
    write_xlsx(os.path.join(sol, "tickets_report.xlsx"), report_workbook(rows), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    write_task_yaml(HERE, {
        "id": "helpdesk-tickets-report", "track": "desk", "category": "reports",
        "title": "May helpdesk tickets by category and SLA breaches",
        "ask": ("Can you turn the helpdesk export into May's report for Thursday's ops meeting - tickets per category and how "
                "many breached the SLA? Save it as tickets_report.xlsx with live formulas, and write the headline in memo.md. "
                "Gwen's email and the policy in the folder say how we count.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "priorities are spelled nine ways across old-helpdesk imports and the web form (P1, Urgent, 1 - Critical, Hi, Medium, med, ...); "
            "the 2026 policy says Urgent is P1 Critical and Medium is P3 Normal, and reading an unrecognised spelling as a default "
            "target moves the breach count (check: total SLA breaches)",
            "targets are business hours, Monday to Friday 08:00-18:00, and a ticket opened in the evening or at the weekend starts "
            "its clock at the next opening; elapsed calendar hours turn most overnight P1/P2 tickets into breaches "
            "(checks: Network SLA breaches; total SLA breaches)",
            "25 May is Memorial Day and the clock does not run; three Network tickets opened on Friday 22 May and fixed on Tuesday "
            "morning are inside target only if the holiday is skipped (check: Network SLA breaches)",
            "tickets still open at the export (1 June 07:45) have no Resolved time; Gwen's second email counts those already past "
            "target as breaches, and dropping them understates the total (check: total SLA breaches)",
            "Merged duplicates and Spam are in the export, and so are ten tickets opened in late April and closed in May; none are "
            "May tickets, and Email carries spam, merges and April tickets (checks: Email tickets; total tickets)",
            "the superseded 2024 policy (08:00-17:00, Normal 16 hours) sits beside the 2026 one (check: total SLA breaches)",
            "the memo must state the breach count in a sentence (check: memo states the breach count)",
        ],
        "checks": [
            {"type": "file_exists", "name": "tickets_report.xlsx exists", "path": "tickets_report.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "tickets_report.xlsx", "min_count": 8},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "tickets_report.xlsx"},
            {"type": "xlsx_value_present", "name": "Email tickets (no merged, spam or April tickets)", "path": "tickets_report.xlsx",
             "expected": s["Email"][0], "rel_tol": 0.001, "near_text": "email"},
            {"type": "xlsx_value_present", "name": "Network SLA breaches (business hours, holiday skipped)", "path": "tickets_report.xlsx",
             "expected": s["Network"][1], "rel_tol": 0.001, "near_text": "network"},
            {"type": "xlsx_value_present", "name": "total tickets", "path": "tickets_report.xlsx",
             "expected": tot_t, "rel_tol": 0.001, "near_text": "total"},
            {"type": "xlsx_value_present", "name": "total SLA breaches", "path": "tickets_report.xlsx",
             "expected": tot_b, "rel_tol": 0.001, "near_text": "total"},
            {"type": "text_sentence_matches", "name": "memo states the breach count", "path": "memo.md",
             "all": [r"(breach|missed|outside (the |their |its )?(sla|target)|over (the |their |its )?(sla|target)|\blate\b|overdue|exceeded|past (the |their |its )?target)",
                     rf"(?<![\d.,]){tot_b}(?![\d]|[.,]\d)"]},
        ],
    })
    print(f"seed={seed} rows={len(T)} summary={s} variants={ {k: v[k]['_total'] for k in v} }")


def write_naive(d: dict, out: str) -> None:
    """Every row in the export, P-codes and exact policy names only (anything else gets the Normal target),
    calendar hours from Created to Resolved, open tickets never breach."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for t in d["tickets"]:
        p = OFFICIAL.get(t["spelling"].lower(), "P3")
        cal = ((t["resolved"] - t["created"]).total_seconds() / 3600) if t["resolved"] else 0
        rows.append([t["id"], t["cat"], p, fmt_dt(t["created"]), fmt_dt(t["resolved"]), t["status"], TARGET[p], round(cal, 2),
                     1 if cal > TARGET[p] else 0, 1])
    write_xlsx(os.path.join(out, "tickets_report.xlsx"), report_workbook(rows), creator="naive")
    b = sum(x[8] for x in rows)
    write_text(os.path.join(out, "memo.md"), f"# Helpdesk, May\n\nWe logged {len(rows)} tickets in May and {b} of them breached the SLA.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
