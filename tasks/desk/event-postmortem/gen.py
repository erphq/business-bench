#!/usr/bin/env python3
"""event-postmortem: conference wrap-up numbers from registrations, door scans and post-event refunds.

    python gen.py [--seed N] [--naive DIR]

Business: a regional data conference run by a small association. Three exports come out of three
systems (Eventbrite-style registrations, the badge scanner, the payment processor's refund report)
and the board wants one summary workbook plus a memo.

Traps (each caught by a check, see task.yaml):
  * comp / speaker passes pay nothing but are registrations and do attend  (checks: comp no-shows; attendance rate)
  * the scanner logs every entry, so most attendees have two or three rows  (check: full conference attended)
  * six attendees have one scan row with a lower-cased badge id            (check: full conference attended)
  * staff badges (STF-) are in the scan log and are not attendees          (check: full conference attended)
  * cancellations were refunded before the event and are out entirely      (check: student gross revenue)
  * eleven refunds were processed after the event and come off revenue     (checks: refunds total; net revenue; memo anomaly)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

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

EVENT_NAME = "Cascade Data Summit 2026"
DAY1 = date(2026, 9, 17)
DAY2 = date(2026, 9, 18)
# ticket type, price, share of registrants who actually show up
TYPES = [("Full conference", 895.00, 0.88), ("Early bird", 645.00, 0.86), ("One-day", 395.00, 0.82),
         ("Student", 195.00, 0.71), ("Comp", 0.00, 0.55)]
COUNTS = {"Full conference": 62, "Early bird": 78, "One-day": 45, "Student": 34, "Comp": 27}
N_CANCEL = 9
N_REFUND = 11
N_CASE_NOISE = 6
N_STAFF_SCANS = 18
DOORS = ["Main entrance", "Main entrance", "Hall B", "Registration desk", "Main entrance"]
REFUND_REASONS = ["Sponsor comped after the fact", "Duplicate charge", "Did not attend - travel cancelled",
                  "Session cancelled, partial", "Membership discount applied late", "Goodwill - AV problems"]


def build(seed: int) -> dict:
    r = rng(seed)
    regs, seq = [], 1000
    for tname, price, att in TYPES:
        for _ in range(COUNTS[tname]):
            seq += 1
            f, l = person(r)
            regs.append({"reg_id": f"REG-{seq}", "first": f, "last": l, "email": email_for(r, f, l),
                         "type": tname, "price": price, "reg_date": day_in(r, date(2026, 5, 4), date(2026, 9, 12)),
                         "status": "Registered", "attended": r.random() < att, "scans": 0,
                         "case_noise": False, "refund": 0.0})

    def of(tname, pool=None):
        return [g for g in (pool if pool is not None else regs) if g["type"] == tname]

    # cancellations: forced into the two ticket types whose gross revenue a check pins
    cancelled = r.sample(of("Full conference"), 2) + r.sample(of("Student"), 2)
    rest = [g for g in regs if g["price"] > 0 and g not in cancelled]
    cancelled += r.sample(rest, N_CANCEL - len(cancelled))
    for g in cancelled:
        g["status"] = "Cancelled"
        g["attended"] = False

    valid = [g for g in regs if g["status"] == "Registered"]
    attendees = [g for g in valid if g["attended"]]
    for g in attendees:
        g["scans"] = r.choice([1, 2, 2, 3])

    # badge ids that show up in two cases in the scan log
    multi = [g for g in attendees if g["scans"] >= 2]
    noisy = r.sample([g for g in multi if g["type"] == "Full conference"], 2)
    noisy += r.sample([g for g in multi if g not in noisy], N_CASE_NOISE - len(noisy))
    for g in noisy:
        g["case_noise"] = True

    # refunds processed after the event closed
    paid_valid = [g for g in valid if g["price"] > 0]
    for g in r.sample(paid_valid, N_REFUND):
        g["refund"] = round(g["price"] * r.choice([1.0, 1.0, 0.5, 0.25]), 2)

    # ---- scan log rows ----
    scans = []
    for g in attendees:
        slots = r.sample([(DAY1, 8), (DAY1, 13), (DAY2, 8), (DAY2, 14)], g["scans"])
        for i, (d, hour) in enumerate(sorted(slots)):
            bid = g["reg_id"].lower() if (g["case_noise"] and i == 1) else g["reg_id"]
            scans.append({"badge": bid, "at": f"{d.isoformat()} {hour + r.randint(0, 2):02d}:{r.randint(0, 59):02d}:{r.randint(0, 59):02d}",
                          "door": r.choice(DOORS), "k": r.random()})
    for _ in range(N_STAFF_SCANS):
        d = r.choice([DAY1, DAY2])
        scans.append({"badge": f"STF-{r.randint(101, 140)}", "at": f"{d.isoformat()} {r.randint(6, 19):02d}:{r.randint(0, 59):02d}:{r.randint(0, 59):02d}",
                      "door": r.choice(DOORS), "k": r.random()})
    scans.sort(key=lambda s: (s["at"], s["k"]))
    for i, s in enumerate(scans):
        s["scan_id"] = f"S{50001 + i}"

    # ---- truth ----
    summary = {}
    for tname, _, _ in TYPES:
        v = [g for g in valid if g["type"] == tname]
        a = [g for g in v if g["attended"]]
        gross = round(sum(g["price"] for g in v), 2)
        refunds = round(sum(g["refund"] for g in v), 2)
        summary[tname] = {"registered": len(v), "attended": len(a), "noshows": len(v) - len(a),
                          "gross": gross, "refunds": refunds, "net": round(gross - refunds, 2)}
    tot = {k: round(sum(summary[t][k] for t, _, _ in TYPES), 2) for k in ("registered", "attended", "noshows", "gross", "refunds", "net")}
    tot["rate"] = round(tot["attended"] / tot["registered"], 4)
    return {"regs": regs, "valid": valid, "attendees": attendees, "cancelled": cancelled,
            "scans": scans, "summary": summary, "tot": tot}


def acceptable(d: dict) -> bool:
    """The pinned cells must move when the obvious shortcut is taken."""
    s, tot = d["summary"], d["tot"]
    # attended for Full conference vs (a) scan rows, (b) case-sensitive unique badges
    fc = [g for g in d["attendees"] if g["type"] == "Full conference"]
    naive_rows = sum(g["scans"] for g in fc)
    naive_case = len(fc) + sum(1 for g in fc if g["case_noise"])
    if naive_rows <= s["Full conference"]["attended"] * 1.05 or naive_case <= s["Full conference"]["attended"] * 1.01:
        return False
    # student gross vs including the cancelled students
    cancel_student = sum(g["price"] for g in d["cancelled"] if g["type"] == "Student")
    if cancel_student <= s["Student"]["gross"] * 0.02:
        return False
    # net revenue vs gross, and vs gross including cancellations
    if tot["refunds"] <= tot["gross"] * 0.02:
        return False
    # comp no-shows must not collide with another figure on the comp row
    comp = s["Comp"]
    if comp["noshows"] in (comp["registered"], comp["attended"]) or comp["noshows"] < 8:
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_sheets(data_rows: list[list], type_names: list[str]) -> dict:
    """Data sheet of one row per registration + a Report sheet of live formulas over it."""
    n = len(data_rows) + 1
    rows = []
    for i, tname in enumerate(type_names, start=2):
        rows.append([tname,
                     f"=COUNTIF(Data!$C$2:$C${n},$A{i})",
                     f"=SUMIFS(Data!$F$2:$F${n},Data!$C$2:$C${n},$A{i})",
                     f"=B{i}-C{i}",
                     f"=SUMIFS(Data!$D$2:$D${n},Data!$C$2:$C${n},$A{i})",
                     f"=SUMIFS(Data!$E$2:$E${n},Data!$C$2:$C${n},$A{i})",
                     f"=E{i}-F{i}"])
    last = 1 + len(type_names)
    rows.append(["Total"] + [f"=SUM({c}2:{c}{last})" for c in "BCDEFG"])
    rows.append([])
    rows.append(["Attendance rate (scanned / registered)", f"=ROUND(C{last + 1}/B{last + 1},4)"])
    return {
        "Data": {"header": ["reg_id", "attendee", "ticket_type", "amount_paid", "refunded_after_event", "attended"],
                 "rows": data_rows, "widths": {"B": 24, "C": 18}},
        "Report": {"header": ["Ticket type", "Registered", "Attended", "No-shows", "Gross revenue", "Refunds", "Net revenue"],
                   "rows": rows, "widths": {"A": 34, "E": 15, "F": 12, "G": 14}},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    s, tot = d["summary"], d["tot"]

    # ---- workspace ----
    reg_rows = []
    for g in d["regs"]:
        amt = "-" if g["price"] == 0 else money_str(g["price"], r_style(g["reg_id"]))
        reg_rows.append([g["reg_id"], f"{g['last']}, {g['first']}", g["email"], g["type"], amt,
                         date_variant(g["reg_date"], sum(ord(c) for c in g["reg_id"]) % 4), g["status"]])
    reg_rows.sort(key=lambda x: x[0])
    write_csv(os.path.join(ws, "registrations_export.csv"),
              ["Reg ID", "Attendee", "Email", "Ticket Type", "Amount Paid", "Registered On", "Status"], reg_rows,
              preamble=[f"{EVENT_NAME} - registration export", "Generated 09/22/2026 07:15 by registration@summit"],
              bom=True, crlf=True)
    write_csv(os.path.join(ws, "badge_scans_sept17-18.csv"), ["scan_id", "badge_id", "scanned_at", "door"],
              [[s_["scan_id"], s_["badge"], s_["at"], s_["door"]] for s_ in d["scans"]])
    refunds = [g for g in d["valid"] if g["refund"] > 0]
    refunds.sort(key=lambda g: g["reg_id"])
    write_csv(os.path.join(ws, "refunds_after_event.csv"), ["Reg ID", "Processed", "Amount", "Reason"],
              [[g["reg_id"], date_variant(DAY2 + timedelta(days=3 + (sum(ord(c) for c in g["reg_id"]) % 21)), 1),
                money_str(g["refund"], 1), REFUND_REASONS[sum(ord(c) for c in g["reg_id"]) % len(REFUND_REASONS)]]
               for g in refunds])
    write_email_thread(os.path.join(ws, "email_from_dana.txt"), [
        {"from": "Dana Whitfield <dana@cascadedatasummit.org>", "to": "you", "date": "Mon, 21 Sep 2026 16:40",
         "subject": "summit wrap-up numbers",
         "body": ("The board meets Thursday and wants the summit numbers by ticket type. Everything is in the folder: "
                  "the registration export, the badge scanner log for both days, and the refund report from the "
                  "payment processor.\n\nAttendance means the person scanned in at least once - it does not matter "
                  "which day or how many times they came through the doors.")},
        {"from": "Dana Whitfield <dana@cascadedatasummit.org>", "to": "you", "date": "Mon, 21 Sep 2026 17:05",
         "subject": "RE: summit wrap-up numbers",
         "body": ("Two things I forgot. Comp passes (speakers, sponsors, the volunteer crew) pay nothing, but they are "
                  "real registrations and they count as attendance when they scan in - the board always asks how many "
                  "comps we gave out. And our own staff badges start with STF, they are working the event, not "
                  "attending it.\n\nThe cancellations in the export were refunded in full before the doors opened. "
                  "Leave them out of the counts and out of the revenue completely.")},
        {"from": "Dana Whitfield <dana@cascadedatasummit.org>", "to": "you", "date": "Tue, 22 Sep 2026 08:12",
         "subject": "RE: summit wrap-up numbers",
         "body": ("Last thing - the processor sent through a batch of refunds in the week after the event and they are "
                  "in refunds_after_event.csv. Those have to come off the revenue or we will report a number we do not "
                  "have.\n\nIn the memo give me the attendance rate and what the revenue came to net of the refunds.")}])

    # ---- reference ----
    write_csv(os.path.join(ref, "event_summary.csv"), ["ticket_type", "registered", "attended", "noshows", "gross", "refunds", "net"],
              [[t, s[t]["registered"], s[t]["attended"], s[t]["noshows"], f"{s[t]['gross']:.2f}", f"{s[t]['refunds']:.2f}", f"{s[t]['net']:.2f}"]
               for t, _, _ in TYPES] +
              [["TOTAL", tot["registered"], tot["attended"], tot["noshows"], f"{tot['gross']:.2f}", f"{tot['refunds']:.2f}", f"{tot['net']:.2f}"]])
    write_json(os.path.join(ref, "notes.json"), {
        "attendance_rate": tot["rate"], "cancelled_registrations": len(d["cancelled"]),
        "refund_count": N_REFUND, "staff_scan_rows": N_STAFF_SCANS, "scan_rows": len(d["scans"])})

    # ---- reference solution ----
    data_rows = [[g["reg_id"], f"{g['first']} {g['last']}", g["type"], g["price"], g["refund"], 1 if g["attended"] else 0]
                 for g in sorted(d["valid"], key=lambda g: g["reg_id"])]
    stable_xlsx(os.path.join(sol, "event_summary.xlsx"), report_sheets(data_rows, [t for t, _, _ in TYPES]), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    # ---- task.yaml ----
    rate_pct = round(tot["rate"] * 100, 1)
    write_task_yaml(HERE, {
        "id": "event-postmortem", "track": "desk", "category": "reports",
        "title": "Wrap-up numbers for the summit",
        "ask": ("We just wrapped the Cascade Data Summit and the board wants the wrap-up numbers by ticket type. "
                "Build me event_summary.xlsx with live formulas and a short memo.md with the headline numbers. "
                "Dana's email thread has the rules.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"comp passes ({COUNTS['Comp']} of them) pay nothing but are registrations and do attend; dropping them or "
            "treating them as zero-revenue non-registrations moves both the comp row and the attendance rate "
            "(checks: comp no-shows; memo headline figures)",
            "the scanner writes one row per entry, so most attendees appear two or three times; attendance is people "
            "who scanned at least once (check: full conference attended)",
            f"{N_CASE_NOISE} attendees have one scan row with a lower-cased badge id, so a case-sensitive unique count "
            "over-counts them (check: full conference attended)",
            f"{N_STAFF_SCANS} staff scan rows (badges starting STF-) are in the log and are not attendees "
            "(check: full conference attended)",
            f"{N_CANCEL} cancelled registrations still carry an amount in the export; Dana's email says they were "
            "refunded before the event and are out of the counts and the revenue entirely (check: student gross revenue)",
            f"{N_REFUND} refunds were processed after the event in a separate file and must come off revenue; "
            "the naive gross total ignores them (checks: net revenue after post-event refunds; memo names the "
            "post-event refunds)",
            "amounts are '$895.00' text with '-' for comps, dates come in four formats, and the registration export "
            "carries a two-line preamble, a BOM and CRLF endings (check: student gross revenue)",
        ],
        "checks": [
            {"type": "file_exists", "name": "event_summary.xlsx exists", "path": "event_summary.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "event_summary.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "event_summary.xlsx"},
            {"type": "xlsx_value_present", "name": "full conference attended (unique scanners)", "path": "event_summary.xlsx",
             "expected": s["Full conference"]["attended"], "rel_tol": cent_tol(s["Full conference"]["attended"], 0.001), "near_text": "full conference"},
            {"type": "xlsx_value_present", "name": "comp no-shows", "path": "event_summary.xlsx",
             "expected": s["Comp"]["noshows"], "rel_tol": cent_tol(s["Comp"]["noshows"], 0.001), "near_text": "comp"},
            {"type": "xlsx_value_present", "name": "student gross revenue (cancellations excluded)", "path": "event_summary.xlsx",
             "expected": s["Student"]["gross"], "rel_tol": cent_tol(s["Student"]["gross"], 0.005), "near_text": "student"},
            {"type": "xlsx_value_present", "name": "net revenue after post-event refunds", "path": "event_summary.xlsx",
             "expected": tot["net"], "rel_tol": cent_tol(tot["net"], 0.005), "near_text": "net"},
            {"type": "text_numbers_present", "name": "memo headline figures", "path": "memo.md",
             "numbers": [tot["registered"], tot["attended"], tot["net"]], "rel_tol": 0.005},
            {"type": "text_numbers_present", "name": "memo states the attendance rate", "path": "memo.md",
             "numbers": [rate_pct], "rel_tol": 0.01},
            {"type": "text_sentence_matches", "name": "memo names the post-event refunds", "path": "memo.md",
             "all": [r"\brefund", r"(\bafter\b|\bpost[- ]event\b|\bfollowing the (event|summit)\b|\bonce the (event|summit)\b)"],
             "none": [r"\bno refunds?\b", r"\bwere not refunded\b"]},
        ],
    })
    print(f"seed={seed} regs={len(d['regs'])} valid={len(d['valid'])} attendees={len(d['attendees'])} "
          f"scan_rows={len(d['scans'])} cancelled={len(d['cancelled'])} refunds={N_REFUND}")
    print("summary:", {t: s[t] for t, _, _ in TYPES})
    print("totals:", tot, "rate_pct:", rate_pct)


def r_style(reg_id: str) -> int:
    return [1, 2, 6][sum(ord(c) for c in reg_id) % 3]


def memo_text(d: dict) -> str:
    s, tot = d["summary"], d["tot"]
    rate_pct = round(tot["rate"] * 100, 1)
    comp = s["Comp"]
    return f"""# {EVENT_NAME} - wrap-up

**Registrations:** {tot['registered']} registrations stood at the door ({len(d['cancelled'])} cancellations were
refunded in full before the event and are excluded from every figure below).

**Attendance:** {tot['attended']} people scanned in at least once, an attendance rate of {rate_pct}%.
{tot['noshows']} registrants never scanned. The scanner logged {len(d['scans'])} entries in total, so the raw
scan count is not the headcount.

**Revenue:** gross registration revenue was {tot['gross']:,.2f}. {N_REFUND} refunds were processed in the week
after the event and take {tot['refunds']:,.2f} off that, leaving {tot['net']:,.2f} net.

Three things worth knowing:

1. {N_REFUND} refunds came through after the event closed, so the registration export overstates revenue by
   {tot['refunds']:,.2f} until they are netted off.
2. Comp passes are {comp['registered']} of the registrations and bring in no revenue; only {comp['attended']} of
   them scanned in, which is the weakest show rate of any ticket type.
3. Student tickets show the second-weakest turnout ({s['Student']['attended']} of {s['Student']['registered']}),
   worth a look before we price that tier again.
"""


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcut: every registration row counted, scan rows counted as attendance,
    refunds file never opened. Same formula structure, naive Data sheet."""
    os.makedirs(out, exist_ok=True)
    scan_count = {}
    for s_ in d["scans"]:
        scan_count[s_["badge"].upper()] = scan_count.get(s_["badge"].upper(), 0) + 1
    rows = [[g["reg_id"], f"{g['first']} {g['last']}", g["type"], g["price"], 0.0, scan_count.get(g["reg_id"], 0)]
            for g in sorted(d["regs"], key=lambda g: g["reg_id"])]
    stable_xlsx(os.path.join(out, "event_summary.xlsx"), report_sheets(rows, [t for t, _, _ in TYPES]), creator="naive")
    tot = d["tot"]
    write_text(os.path.join(out, "memo.md"), f"""# Summit wrap-up

Registrations: {tot['registered'] + len(d['cancelled'])}. Scans at the door: {len(d['scans'])}.
Gross registration revenue: {tot['gross'] + sum(g['price'] for g in d['cancelled']):,.2f}.
Attendance looked strong across every ticket type.
""")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(200):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 200 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
