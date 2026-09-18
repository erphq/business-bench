#!/usr/bin/env python3
"""incident-report: a shift supervisor's rushed notes, two witness emails, the safety manager's thread, the
conveyor e-stop export and the first aid log become a formal incident report on the company template.

    python gen.py [--seed N]

Business: a regional distribution center. An order picker's hand was caught at a conveyor merge while
clearing a jammed tote. The safety manager needs the formal report for the insurer and the file.

Traps (each caught by a check, see task.yaml):
  * three people give three times (notes "about 2:15", one witness "around 2:30", the other "a little after
    two"); the safety manager says the Line 3 e-stop in the controller export is the clock of record, and the
    export also holds a Line 1 jam stop at about 2:15 that day and a Line 3 stop at the same hour the day before
                                                                          (check: incident time from the e-stop log)
  * the supervisor's notes swap the injured picker and the co-worker who hit the e-stop; the first aid log and
    both witness emails name the picker                                   (check: injured person)
  * the notes say first aid only, no doctor; the first aid log records a referral to urgent care
                                                                          (check: urgent care referral)
  * corrective actions change inside the thread: the guard's due date moves when facilities cannot get the part,
    and the safety manager takes the jam-clearing refresher off the loader named in the notes
                                                                          (check: corrective actions with owners)
  * the notes blame the picker for not paying attention; the safety manager forbids fault language and says the
    cause is under investigation                                          (checks: no fault language; cause under investigation)
"""
from __future__ import annotations
import os, sys
from datetime import date, datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

COMPANY = "Silverline Logistics"
SITE = "Tacoma distribution center"
INCIDENT_DAY = date(2026, 9, 3)  # Thursday
MONTH_ABBR = {9: "sep(?:t(?:ember)?)?"}


def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def build(seed: int) -> dict:
    r = rng(seed * 1000 + 101)
    firsts, lasts, ppl = set(), set(), []
    while len(ppl) < 7:
        f, l = person(r)
        if f in firsts or l in lasts:
            continue
        firsts.add(f); lasts.add(l); ppl.append((f, l))
    names = ["injured", "coworker", "loader", "supervisor", "safety", "facilities", "first_aider"]
    P = {k: {"first": f, "last": l, "full": f"{f} {l}"} for k, (f, l) in zip(names, ppl)}
    minute = r.randint(2, 8)
    second = r.randint(10, 58)
    t_estop = datetime.combine(INCIDENT_DAY, datetime.min.time()).replace(hour=14, minute=minute, second=second)
    t_reset = t_estop + timedelta(minutes=r.randint(26, 34), seconds=r.randint(0, 50))
    t_aid = t_estop + timedelta(minutes=r.randint(6, 10))
    t_depart = t_aid + timedelta(minutes=r.randint(24, 32))
    decoy_l1 = datetime.combine(INCIDENT_DAY, datetime.min.time()).replace(hour=14, minute=r.randint(13, 17), second=r.randint(0, 59))
    decoy_prev = datetime.combine(INCIDENT_DAY - timedelta(days=1), datetime.min.time()).replace(hour=14, minute=r.randint(10, 20), second=r.randint(0, 59))
    guard_first_due = date(2026, 9, 11)
    guard_due = date(2026, 9, r.choice([15, 16, 17]))
    training_due = date(2026, 9, r.choice([18, 22, 24]))
    signage_due = date(2026, 9, r.choice([8, 9, 10]))
    return {"P": P, "t_estop": t_estop, "t_reset": t_reset, "t_aid": t_aid, "t_depart": t_depart, "decoy_l1": decoy_l1,
            "decoy_prev": decoy_prev, "guard_first_due": guard_first_due, "guard_due": guard_due,
            "training_due": training_due, "signage_due": signage_due, "hand": r.choice(["left", "right"]),
            "urgent_care": r.choice(["Northside Urgent Care", "MultiCare Urgent Care Fife", "Pacific Avenue Urgent Care"]),
            "seed": seed, "r": r}


def estop_rows(d: dict) -> list[list]:
    r = d["r"]
    rows = []
    start = datetime(2026, 8, 31, 6, 0, 0)
    for day in range(6):
        base = start + timedelta(days=day)
        for _ in range(r.randint(3, 6)):
            t = base + timedelta(minutes=r.randint(0, 15 * 60))
            line = r.choice([1, 2, 4])
            kind = r.choice(["JAM_DETECTED", "MOTOR_OVERLOAD", "PHOTOEYE_BLOCKED", "JAM_DETECTED"])
            rows.append([t, f"L{line}", f"L{line}-{r.choice(['INDUCT', 'MERGE', 'SORT', 'SPUR07'])}", kind, "AUTO", ""])
            rows.append([t + timedelta(minutes=r.randint(1, 6), seconds=r.randint(0, 59)), f"L{line}", rows[-1][2], "CLEARED", "AUTO", ""])
    t = d["decoy_prev"]
    rows.append([t, "L3", "L3-MERGE", "ESTOP_PRESSED", "PB-ESTOP", "maint test"])
    rows.append([t + timedelta(minutes=3, seconds=12), "L3", "L3-MERGE", "ESTOP_RESET", "KEY", "maint test"])
    t = d["decoy_l1"]
    rows.append([t, "L1", "L1-INDUCT", "ESTOP_PRESSED", "PB-ESTOP", "jam clear"])
    rows.append([t + timedelta(minutes=4, seconds=40), "L1", "L1-INDUCT", "ESTOP_RESET", "KEY", ""])
    rows.append([d["t_estop"] - timedelta(seconds=41), "L3", "L3-MERGE", "JAM_DETECTED", "AUTO", ""])
    rows.append([d["t_estop"], "L3", "L3-MERGE", "ESTOP_PRESSED", "PB-ESTOP", ""])
    rows.append([d["t_reset"], "L3", "L3-MERGE", "ESTOP_RESET", "KEY", "reset by supv"])
    rows.sort(key=lambda x: x[0])
    return [[x[0].strftime("%Y-%m-%d %H:%M:%S")] + x[1:] for x in rows]


def time_regex(t: datetime) -> str:
    h12 = t.hour - 12 if t.hour > 12 else t.hour
    mm = f"{t.minute:02d}"
    return (rf"(?<![\d:])({t.hour}[:.]{mm}|0?{h12}[:.]{mm}(?:[:.]\d\d)?\s*(?:p\.?\s?m\.?)|{t.hour}{mm}\s*(?:hrs|hours|h\b))")


def date_regex(dd: date) -> str:
    n = dd.day
    mon = MONTH_ABBR[dd.month]
    return (rf"(2026-09-{n:02d}|(?<!\d)0?9/{n:02d}(?!\d)|(?<!\d)0?9/{n}(?!\d)|(?<!\d){n:02d}/0?9(?!\d)|(?<!\d){n}/0?9(?!\d)|"
            rf"\b{mon}\.?\s+{n}(?:st|nd|rd|th)?\b|\b{n}(?:st|nd|rd|th)?\s+(?:of\s+)?{mon}\b)")


def hm(t: datetime) -> str:
    return t.strftime("%H:%M")


def emit(seed: int) -> None:
    d = build(seed)
    P = d["P"]
    ws, ref, sol = task_dirs(HERE)
    inj, cow, loa, sup, saf, fac, fa = (P[k] for k in ["injured", "coworker", "loader", "supervisor", "safety", "facilities", "first_aider"])
    hand = d["hand"]
    day_long = "Thursday 3 September 2026"

    # ---- supervisor's rushed notes (wrong on who, when, treatment and blame) ----
    write_text(os.path.join(ws, "shift_notes_thu_Bshift.txt"), f"""B shift notes - Thu 9/3 - {sup['first']}

- staffing short 2 on pick module, borrowed {loa['first']} from dock for 2hrs
- L1 induct jammed again after lunch, maint cleared it

INCIDENT L3 merge, about 2:15
{cow['full']} got their hand caught at the L3 merge clearing a stuck tote. {inj['first']} ({inj['last']}) saw it and hit the e-stop.
honestly wasn't paying attention, reached in without stopping the line. careless.
first aid only, no doctor needed. bandaged in the break room.
line down ~30 min, I reset it.

follow ups
- {loa['first']} to run a jam clearing refresher for pick module since they know the merge
- need a guard on that merge, ask facilities
- signs at the merges "STOP LINE BEFORE CLEARING"
- write it up for {saf['first']}
""")

    # ---- witness statements ----
    write_email_thread(os.path.join(ws, "witness_statements.txt"), [
        {"from": f"{cow['full']} <{cow['first'].lower()}.{cow['last'].lower()}@silverlinelogistics.com>",
         "to": f"{sup['full']}; {saf['full']}", "date": "Thu, 3 Sep 2026 16:48", "subject": "what I saw on line 3",
         "body": (f"{sup['first']} asked me to write down what happened.\n\n"
                  f"I was picking at the station next to the Line 3 merge, around 2:30 I think, right before my break. "
                  f"A tote got stuck at the merge and {inj['first']} reached in to free it. The tote moved and {inj['first']}'s "
                  f"{hand} hand got pinched between the tote and the side rail. {inj['first']} yelled and I hit the e-stop "
                  f"on the post by the merge. The line stopped right away.\n\n"
                  f"I walked {inj['first']} to the break room and {fa['first']} did first aid. There was a lot of blood from "
                  f"two fingers. I was not hurt.\n\n{cow['first']}")},
        {"from": f"{loa['full']} <{loa['first'][0].lower()}{loa['last'].lower()}@silverlinelogistics.com>",
         "to": f"{saf['full']}", "date": "Fri, 4 Sep 2026 07:12", "subject": "RE: statement - L3",
         "body": (f"I was bringing empties to the L3 merge a little after two when the line stopped. {cow['first']} had hit "
                  f"the e-stop and {inj['full']} was holding their {hand} hand. That merge jams a few times a week and "
                  f"people clear it by hand, there is nothing stopping you reaching in. I did not see the moment it "
                  f"happened.\n\n{loa['first']}")},
    ])

    # ---- safety manager thread (authoritative on rules, time source, owners) ----
    g1, gd, td, sd = d["guard_first_due"], d["guard_due"], d["training_due"], d["signage_due"]
    write_email_thread(os.path.join(ws, "email_thread_safety.txt"), [
        {"from": f"{saf['full']} <{saf['first'].lower()}.{saf['last'].lower()}@silverlinelogistics.com>",
         "to": f"{sup['full']}; {fac['full']}", "date": "Fri, 4 Sep 2026 09:05", "subject": "Line 3 incident - formal report",
         "body": (f"Thanks for the notes and statements. The insurer wants the formal report on our template "
                  f"(incident_report_template.md) and it goes in the file, so a few rules:\n\n"
                  f"1. Time of the incident: use the Line 3 e-stop in the conveyor controller export. That is the only "
                  f"clock we have. Everybody's memory is a guess.\n"
                  f"2. Who was injured and how they were treated comes from the first aid log. {fa['first']} filled it in "
                  f"at the time.\n"
                  f"3. No blame and no fault in the report. Do not write that anyone was careless or not paying attention. "
                  f"We have not done the root cause yet; say the cause is under investigation (RCA review is Tuesday).\n"
                  f"4. Every corrective action needs one owner and a due date.\n\n"
                  f"Proposed actions:\n"
                  f"- fixed guard at the Line 3 merge pinch point - {fac['full']} - due {g1.strftime('%-d %b')}\n"
                  f"- jam-clearing (stop the line first) refresher for all pick module staff - {loa['full']} - due {td.strftime('%-d %b')}\n"
                  f"- STOP LINE BEFORE CLEARING signs at every merge - {sup['full']} - due {sd.strftime('%-d %b')}\n\n"
                  f"{saf['first']}")},
        {"from": f"{fac['full']} <{fac['first'].lower()}.{fac['last'].lower()}@silverlinelogistics.com>",
         "to": f"{saf['full']}", "date": "Fri, 4 Sep 2026 11:40", "subject": "RE: Line 3 incident - formal report",
         "body": (f"The guard panel has to come from the conveyor vendor. Earliest install is {gd.strftime('%A %-d %B')}, "
                  f"so please put that as the due date for the guard. Until then I have taped off the merge.\n\n{fac['first']}")},
        {"from": f"{saf['full']} <{saf['first'].lower()}.{saf['last'].lower()}@silverlinelogistics.com>",
         "to": f"{sup['full']}; {fac['full']}", "date": "Fri, 4 Sep 2026 13:22", "subject": "RE: Line 3 incident - formal report",
         "body": (f"OK, guard due {gd.strftime('%-d %B')} then. One more change: I will run the jam-clearing refresher myself, "
                  f"not {loa['first']}. {loa['first']} is on the dock and it needs to come from safety. Same due date. "
                  f"Signs stay with {sup['first']}.\n\n{saf['first']}")},
    ])

    # ---- first aid log (authoritative for who and treatment) ----
    cast_first = {v["first"] for v in P.values()}; cast_last = {v["last"] for v in P.values()}
    other = []
    while len(other) < 4:
        f, l = person(d["r"])
        if f not in cast_first and l not in cast_last and (f, l) not in other:
            other.append((f, l))
    aid_rows = [
        ["2026-08-27", "10:15", f"{other[0][0]} {other[0][1]}", "Returns", "Paper cut, right index finger", "Cleaned, plaster", "No", fa["full"]],
        ["2026-09-01", "07:40", f"{other[1][0]} {other[1][1]}", "Dock", "Dust in eye", "Eyewash station", "No", fa["full"]],
        ["2026-09-03", "09:52", f"{other[2][0]} {other[2][1]}", "Pick module", "Small cut, box cutter, left thumb", "Cleaned, plaster", "No", fa["full"]],
        ["2026-09-03", hm(d["t_aid"]), inj["full"], "Pick module",
         f"Laceration and bruising, {hand} hand (ring and little finger), caught at L3 merge",
         f"Cleaned, pressure dressing, ice. Possible fracture. Referred to urgent care ({d['urgent_care']}), driven by {sup['first']} {sup['last']} at {hm(d['t_depart'])}",
         "Yes - urgent care", fa["full"]],
        ["2026-09-04", "12:30", f"{other[3][0]} {other[3][1]}", "Dock", "Pulled muscle, lower back, lifting", "Ice pack, rest", "No", fa["full"]],
    ]
    write_csv(os.path.join(ws, "first_aid_log_2026.csv"), ["Date", "Time", "Name", "Department", "Injury", "Treatment given", "Referred for medical treatment", "First aider"], aid_rows)

    write_csv(os.path.join(ws, "conveyor_estop_events_wk36.csv"), ["Timestamp (local)", "Line", "Device", "Event", "Source", "Note"],
              estop_rows(d), preamble=["ConveyorLogix event export", "Site: TAC-DC1  Range: 2026-08-31 to 2026-09-05"], bom=True, crlf=True)

    write_text(os.path.join(ws, "incident_report_template.md"), f"""# {COMPANY} - Incident Report

## 1. Summary

## 2. Date, time and location

## 3. People involved
- Injured person (name, role):
- Witnesses:
- Supervisor on shift:

## 4. Injury and treatment

## 5. Sequence of events

## 6. Immediate actions taken

## 7. Cause

## 8. Corrective actions
| Action | Owner | Due date |
|---|---|---|

## 9. Prepared by / date
""")

    # ---- reference solution: a plain, careful report ----
    t = d["t_estop"]
    t12 = t.strftime("%-I:%M %p")
    report = f"""# {COMPANY} - Incident Report

## 1. Summary
On {day_long} an order picker, {inj['full']}, sustained a laceration and bruising to the {hand} hand at the Line 3 merge of the {SITE} while freeing a jammed tote. {cow['full']} stopped the line with the e-stop. {inj['full']} received first aid on site and was referred to urgent care.

## 2. Date, time and location
- Date: {day_long}
- Time: {hm(t)} ({t12}), the time the Line 3 e-stop was pressed according to the conveyor controller export. Witness estimates ranged from a little after 2:00 to 2:30 PM; the controller log is the record.
- Location: Line 3 merge (device L3-MERGE), pick module, {SITE}.

## 3. People involved
- Injured person (name, role): {inj['full']}, order picker, pick module.
- Witnesses: {cow['full']} (picker at the adjacent station, pressed the e-stop); {loa['full']} (arrived at the merge after the line had stopped, did not see the moment of injury).
- Supervisor on shift: {sup['full']}.

## 4. Injury and treatment
{inj['full']} sustained a laceration and bruising to the ring and little finger of the {hand} hand, with a possible fracture. First aid was given by {fa['full']} at {hm(d['t_aid'])}: the wound was cleaned and dressed and ice applied. {inj['full']} was referred to urgent care ({d['urgent_care']}) and was driven there by {sup['full']} at {hm(d['t_depart'])}.

## 5. Sequence of events
1. At {hm(d['t_estop'] - timedelta(seconds=41))} the controller recorded a jam at the Line 3 merge.
2. {inj['full']} reached in to free the stuck tote; the tote moved and the {hand} hand was pinched between the tote and the side rail.
3. At {hm(t)} {cow['full']} pressed the e-stop at the merge and the line stopped.
4. {cow['full']} walked {inj['full']} to the break room, where first aid was given at {hm(d['t_aid'])}.
5. The line was reset at {hm(d['t_reset'])}.

## 6. Immediate actions taken
- Line 3 stopped by e-stop and later reset by the supervisor.
- First aid given and referral to urgent care.
- Facilities taped off the Line 3 merge pending installation of a guard.

## 7. Cause
The cause is under investigation. A root cause review is scheduled for Tuesday 8 September 2026. The witness statement from {loa['full']} notes that the merge jams several times a week and is cleared by hand with nothing preventing access to the pinch point.

## 8. Corrective actions
| Action | Owner | Due date |
|---|---|---|
| Install a fixed guard at the Line 3 merge pinch point | {fac['full']} | {gd.isoformat()} |
| Jam-clearing refresher (stop the line first) for all pick module staff | {saf['full']} | {td.isoformat()} |
| STOP LINE BEFORE CLEARING signs at every merge | {sup['full']} | {sd.isoformat()} |

## 9. Prepared by / date
Prepared for {saf['full']}, Safety Manager, 4 September 2026.
"""
    write_text(os.path.join(sol, "incident_report.md"), report)

    actions = [
        {"action": "guard at the Line 3 merge", "keyword": r"\bguard", "owner": fac["last"], "due": gd.isoformat(), "due_regex": date_regex(gd),
         "wrong_due": g1.isoformat()},
        {"action": "jam-clearing refresher training", "keyword": r"\b(train|refresher)", "owner": saf["last"], "due": td.isoformat(), "due_regex": date_regex(td),
         "wrong_owner": loa["last"]},
        {"action": "stop-line signs at the merges", "keyword": r"\b(sign|signs|signage)\b", "owner": sup["last"], "due": sd.isoformat(), "due_regex": date_regex(sd)},
    ]
    write_json(os.path.join(ref, "facts.json"), {
        "incident_time": hm(t), "injured": inj["full"], "coworker_who_pressed_estop": cow["full"], "urgent_care": d["urgent_care"],
        "actions": actions})

    write_task_yaml(HERE, {
        "id": "incident-report", "track": "desk", "category": "drafting",
        "title": "Formal incident report for the Line 3 injury",
        "ask": (f"Turn last Thursday's Line 3 injury into a formal incident report on our template for the insurer and the file. "
                f"The notes, statements and logs are all in the folder, and {saf['first']}'s emails say how the report has to be done. "
                f"Save it as incident_report.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"three accounts give three times (notes 'about 2:15', one witness 'around 2:30', the other 'a little after two'); the safety manager makes the Line 3 e-stop in the controller export the clock of record ({hm(t)}), and that export also holds a Line 1 jam stop at {hm(d['decoy_l1'])} the same afternoon and a Line 3 test stop at {hm(d['decoy_prev'])} the day before (check: incident time from the e-stop log)",
            f"the supervisor's notes swap the injured picker ({inj['full']}) with the co-worker who pressed the e-stop ({cow['full']}); the first aid log and both witness emails name the picker (check: injured person named)",
            "the notes say first aid only and no doctor; the first aid log records a referral to urgent care (check: urgent care referral)",
            f"the corrective actions change inside the thread: facilities moves the guard from {g1.isoformat()} to {gd.isoformat()}, and the safety manager takes the refresher training off {loa['full']}, the loader named in the notes and in the safety manager's first email (check: corrective actions with owners and due dates)",
            "the notes call the picker careless and not paying attention; the safety manager forbids fault language and wants the cause reported as under investigation (checks: no fault language; cause under investigation)",
            "the e-stop export carries a week of unrelated jam and overload events with a two-line preamble, a BOM and CRLF endings; the first aid log has another pick module entry the same morning (check: incident time from the e-stop log)",
        ],
        "checks": [
            {"type": "file_exists", "name": "incident_report.md exists", "path": "incident_report.md"},
            {"type": "text_sentence_matches", "name": "incident time from the e-stop log", "path": "incident_report.md",
             "all": [time_regex(t)]},
            {"type": "text_sentence_matches", "name": "injured person named", "path": "incident_report.md",
             "all": [rf"\b{inj['last']}\b", r"(\binjur|\bhurt\b|\bcaught\b|\bpinched\b|\blaceration|\bcasualty\b|\baffected (employee|person|worker)\b)"],
             "none": [rf"\b{cow['last']}\b[^.;]{{0,40}}\b(?<!not )(?<!n't )(injur|hurt\b|caught\b|pinched\b|lacerat)", rf"\b(injured|hurt)\b[^.;]{{0,25}}\b{cow['last']}\b"]},
            {"type": "text_sentence_matches", "name": "urgent care referral", "path": "incident_report.md",
             "all": [r"(urgent care|\bclinic\b|\bdoctor\b|\bphysician\b|medical (treatment|evaluation|attention|care))",
                     r"(\brefer|\bsent\b|\btaken\b|\btransport|\bdrove\b|\bdriven\b|\bescorted\b)"],
             "none": [r"\bno\b[^.;]{0,25}\b(doctor|medical|urgent|referral)", r"\bnot\b[^.;]{0,20}\b(referred|sent|taken|needed|required)\b", r"first aid only"]},
            {"type": "text_sentence_matches", "name": "cause under investigation", "path": "incident_report.md",
             "all": [r"\b(cause|causes|why)\b",
                     r"(under investigation|being investigated|investigation (is )?(ongoing|underway|in progress|pending)|not yet (been )?(determined|known|established|identified)|to be determined|pending (the |a )?(investigation|root cause|review|rca))"],
             "none": [r"\bno investigation\b", r"\bnot (under|being) investigat"]},
            {"type": "text_not_contains", "name": "no fault language", "path": "incident_report.md",
             "phrases": ["paying attention", "careless", "inattenti", "at fault", "was to blame", "her fault", "his fault"]},
            {"type": "custom", "name": "corrective actions with owners and due dates", "module": "check.py"},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
