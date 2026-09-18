#!/usr/bin/env python3
"""Deterministic seed generator for the event-registration build task.

    python gen.py [--seed N]

Writes:
  seed/rooms.csv          venue room inventory across three buildings: exact duplicate rows, rows that
                          repeat a room code written RM14 / rm-014, capacities as "24 pax" / "1,200"
  seed/sessions.csv       60 ticketed workshops over three days: duplicate rows, session codes and room
                          codes written several ways, 12- and 24-hour times, "Free" prices, and one
                          session that ends before it starts
  seed/registrations.csv  one row per attendee per workshop: exact duplicate rows, statuses in eight
                          spellings, amounts as currency strings (waitlisted and cancelled rows carry an
                          amount too), email case variants for repeat attendees, mixed timestamps
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Chair names are fixed across seeds (the ask names Helena Varga); other seeds re-roll rooms, sessions,
attendees, and timestamps, and counts.json is recomputed from the truth.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date, datetime, time, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import COMPANIES, FIRST, LAST, argparse_seed, write_csv, write_json  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

CHAIRS = ["Helena Varga", "Samuel Osei", "Priyanka Rao", "Martin Kessler", "Aisha Bello", "Graham Lott",
          "Yuki Sato", "Rosa Delgado", "Ian McAllister", "Fatima Qureshi", "Lars Nilsson", "Chloe Dumont",
          "Victor Huang", "Nora Fitzpatrick", "Emeka Obi", "Sara Lindgren"]
RESTRICTED = "Helena Varga"
TRACKS = ["Operations", "Finance", "People", "Technology"]
DAYS = [date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15)]
SLOTS = [(time(9, 0), time(10, 30)), (time(11, 0), time(12, 30)), (time(13, 30), time(15, 0)), (time(15, 30), time(17, 0))]
PRICES = [0, 95, 145, 195, 195, 245]
EARLY_BIRD_BEFORE = date(2026, 7, 15)
EARLY_BIRD_FACTOR = 0.8
BUILDINGS = ["Convention Center", "Harbor Hotel", "Lakeside Hotel"]
TITLE_WORDS = {
    "Operations": ["Lean Scheduling", "Inventory Buffers", "Supplier Scorecards", "Shift Handover Design", "Warehouse Slotting",
                   "Demand Sensing", "Maintenance Planning", "Quality Escapes", "Dock Appointment Systems", "Returns Triage",
                   "Capacity Modeling", "Standard Work Audits", "Line Balancing", "Cycle Counting", "Freight Audit"],
    "Finance": ["Rolling Forecasts", "Cash Conversion", "Cost Allocation", "Audit Readiness", "Revenue Recognition",
                "Working Capital", "Budget Ownership", "Close Acceleration", "Pricing Guardrails", "Spend Analytics",
                "Treasury Basics", "Variance Storytelling", "Capex Reviews", "Unit Economics", "Controls Testing"],
    "People": ["Onboarding Journeys", "Frontline Retention", "Skills Matrices", "Scheduling Fairness", "Manager Coaching",
               "Pay Transparency", "Safety Culture", "Succession Maps", "Hiring Scorecards", "Exit Interviews",
               "Learning Paths", "Team Rituals", "Workforce Planning", "Recognition Programs", "Conflict Mediation"],
    "Technology": ["Data Contracts", "Barcode Rollouts", "Integration Patterns", "Dashboard Hygiene", "Access Reviews",
                   "Master Data Cleanup", "Automation Triage", "Label Printing", "Mobile Scanning", "Report Retirement",
                   "Vendor Portals", "Spreadsheet Exit Plans", "Audit Trails", "Alert Fatigue", "System Cutovers"],
}
ROOM_NAMES = ["Boardroom", "Studio", "Salon", "Meeting Room", "Breakout", "Suite", "Hall"]
N_ROOMS, N_SESSIONS = 60, 60
N_ROOM_EXACT, N_ROOM_CODE = 2, 2
N_SESS_EXACT, N_SESS_CODE = 2, 2
N_REG_DUPES = 8
N_FULL = 5
N_ATTENDEES = 175


def usd(c: int) -> str:
    return f"{c / 100:,.2f}"


def t12(t: time) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def ts_str(t: datetime, style: int) -> str:
    h12 = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return [t.strftime("%Y-%m-%d %H:%M"), f"{t.month}/{t.day}/{t.year} {h12}:{t.minute:02d} {ampm}",
            t.strftime("%d-%b-%Y %H:%M"), f"{t.strftime('%b')} {t.day} {t.year} {t.strftime('%H:%M')}"][style]


def room_code(n: int, style: int) -> str:
    return [f"RM-{n:03d}", f"RM{n}", f"rm-{n:03d}", f"RM-{n}"][style]


def sess_code(n: int, style: int) -> str:
    return [f"WS-{n:03d}", f"WS-{n}", f"WS{n:03d}", f"{n}"][style]


def cap_str(c: int, style: int) -> str:
    return [f"{c}", f"{c} pax", f"{c:,}", f"{c} seats"][style]


def main() -> None:
    seed = argparse_seed()
    r = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)

    # ------------------------------------------------------------------ rooms
    codes = r.sample(range(1, 400), N_ROOMS)
    caps = ([1200] + [r.choice([250, 300, 350, 400, 450, 500, 600]) for _ in range(5)]
            + [r.choice([48, 60, 72, 80, 96, 100, 120, 150]) for _ in range(24)]
            + [12, 16, 18, 20] + [r.choice([12, 14, 16, 18, 20, 24, 28, 30, 36, 40]) for _ in range(26)])
    rooms, used_names = [], set()
    for i, (code, cap) in enumerate(zip(codes, caps)):
        b = r.choice(BUILDINGS)
        if cap == 1200:
            name = "Grand Hall"
        else:
            while True:
                kind = "Ballroom" if cap >= 250 else ("Hall" if cap >= 100 else r.choice(ROOM_NAMES[:-1]))
                name = f"{b.split()[0]} {kind} {r.randint(1, 12)}"
                if name not in used_names:
                    break
        used_names.add(name)
        rooms.append({"code": code, "name": name, "building": "Convention Center" if cap == 1200 else b, "floor": r.randint(1, 4),
                      "cap": cap, "setup": r.choice(["Theatre", "Classroom", "U-shape", "Boardroom", "Cabaret"]),
                      "accessible": r.choice(["Y", "Y", "Y", "N"]), "cap_style": 2 if cap >= 1000 else r.randrange(4)})
    assert sum(1 for x in rooms if x["cap"] == 1200) == 1
    second_cap = sorted({x["cap"] for x in rooms})[-2]

    # ------------------------------------------------------------------ sessions
    blocks = [(d, s) for d in DAYS for s in range(len(SLOTS))]
    small_rooms = [x for x in rooms if 16 <= x["cap"] <= 20]
    mid_rooms = [x for x in rooms if 24 <= x["cap"] <= 100]
    titles = {t: r.sample(TITLE_WORDS[t], len(TITLE_WORDS[t])) for t in TRACKS}
    sess_numbers = r.sample(range(1, 180), N_SESSIONS)
    chair_list = [RESTRICTED] * 3 + [c for c in CHAIRS[1:] for _ in range(4)][:N_SESSIONS - 3]
    sessions = []
    full_idx = set(r.sample(range(N_SESSIONS), N_FULL))
    block_rooms = {b: [] for b in blocks}
    for i in range(N_SESSIONS):
        block = blocks[i % len(blocks)]
        pool = small_rooms if i in full_idx else mid_rooms
        room = r.choice([x for x in pool if all(x is not y for y in block_rooms[block])])
        block_rooms[block].append(room)
        track = TRACKS[i % 4]
        sessions.append({"num": sess_numbers[i], "title": titles[track].pop(), "track": track, "day": block[0], "slot": block[1],
                         "start": SLOTS[block[1]][0], "end": SLOTS[block[1]][1], "room": room, "price": r.choice(PRICES) * 100,
                         "full": i in full_idx, "chair": None})
    # chairs: Helena gets one full Operations session and two non-full Operations sessions
    ops_full = [s for s in sessions if s["full"] and s["track"] == "Operations"]
    if not ops_full:
        s0 = next(s for s in sessions if s["full"])
        s0["track"] = "Operations"
        ops_full = [s0]
    test = ops_full[0]
    if test["price"] < 14500:
        test["price"] = 19500
    test["chair"] = RESTRICTED
    helena_other = r.sample([s for s in sessions if not s["full"] and s["track"] == "Operations" and s["day"] != test["day"]], 2)
    for s in helena_other:
        s["chair"] = RESTRICTED
    rest_chairs = [c for c in CHAIRS[1:] for _ in range(4)]
    r.shuffle(rest_chairs)
    for s in sessions:
        if s["chair"] is None:
            s["chair"] = rest_chairs.pop()
    # one impossible session: ends before it starts (non-full, not Helena's)
    bad = r.choice([s for s in sessions if not s["full"] and s["chair"] != RESTRICTED and s["track"] != "Operations"])
    bad["bad_end"] = time(bad["start"].hour - 1 if bad["start"].hour > 9 else 8, 15)
    # a smaller room for the capacity-guard item (free in that block? not needed: the move must be refused anyway)
    smaller = r.choice([x for x in rooms if x["cap"] < test["room"]["cap"] and all(x is not y for y in block_rooms[(test["day"], test["slot"])])])
    larger_free = [x for x in rooms if x["cap"] >= 60 and all(x is not y for y in block_rooms[(test["day"], test["slot"])])]

    # ------------------------------------------------------------------ attendees and registrations
    pairs = [(f, l) for f in FIRST for l in LAST]
    r.shuffle(pairs)
    companies = r.sample(COMPANIES, 30)
    attendees = []
    for k in range(N_ATTENDEES):
        f, l = pairs[k]
        comp = companies[k % len(companies)] if k < 120 else r.choice(companies)
        attendees.append({"first": f, "last": l, "email": f"{f}.{l}@{comp[1]}".lower(), "company": comp[0], "regs": []})
    reg_start, reg_end = datetime(2026, 6, 1, 8, 0), datetime(2026, 9, 10, 12, 0)

    regs = []

    def free(a, s):
        return all((x["session"]["day"], x["session"]["slot"]) != (s["day"], s["slot"]) for x in a["regs"])

    def add_reg(a, s, status, t=None):
        t = t or reg_start + timedelta(minutes=r.randint(0, int((reg_end - reg_start).total_seconds() // 60)))
        amount = s["price"]
        if t.date() < EARLY_BIRD_BEFORE:
            amount = int(round(s["price"] * EARLY_BIRD_FACTOR))
        reg = {"a": a, "session": s, "status": status, "t": t, "amount": amount}
        regs.append(reg)
        a["regs"].append(reg)
        return reg

    for s in sessions:
        if s["full"]:
            cap = s["room"]["cap"]
            n_wait = 3 if s is test else r.randint(1, 3)
            cands = [a for a in attendees if free(a, s)]
            chosen = r.sample(cands, cap + n_wait)
            times = sorted(reg_start + timedelta(minutes=r.randint(0, 130_000)) for _ in range(cap + n_wait))
            for a, t in zip(chosen, times):
                add_reg(a, s, "confirmed" if len(regs_of(s, regs)) < cap else "waitlisted", t)
        else:
            n = r.randint(6, 10) if s["chair"] == RESTRICTED else r.randint(0, 5)
            cands = [a for a in attendees if free(a, s)]
            for a in r.sample(cands, n):
                add_reg(a, s, "cancelled" if r.random() < 0.08 else "confirmed")

    # waitlist timestamps for the test session: earliest waitlisted written US style, the first row in file ISO
    # file rows are grouped by session and attendee surname, so file order is not arrival order: the earliest
    # waitlisted goes to the surname that sorts last
    tw = sorted([x for x in regs if x["session"] is test and x["status"] == "waitlisted"], key=lambda x: (x["a"]["last"], x["a"]["first"]))
    tw = [tw[2], tw[0], tw[1]]
    last_conf = max(x["t"] for x in regs if x["session"] is test and x["status"] == "confirmed")
    base = max(last_conf + timedelta(hours=2), datetime(2026, 7, 20, 9, 0))
    tw[0]["t"] = base + timedelta(days=1, hours=7, minutes=25)   # earliest waitlisted
    tw[1]["t"] = base + timedelta(days=2, minutes=15)
    tw[2]["t"] = base + timedelta(days=3, hours=2)
    for x in tw:
        x["amount"] = test["price"]
    # the confirmed registration the tester cancels: an early-bird one
    test_conf = sorted([x for x in regs if x["session"] is test and x["status"] == "confirmed"], key=lambda x: x["t"])
    cancel_me = test_conf[0]
    if cancel_me["t"].date() >= EARLY_BIRD_BEFORE:
        cancel_me["t"] = datetime(2026, 6, 3, 10, 5)
        cancel_me["amount"] = int(round(test["price"] * EARLY_BIRD_FACTOR))

    # a repeat attendee with three confirmed registrations and email case variants
    multi = next(a for a in attendees if sum(1 for x in a["regs"] if x["status"] == "confirmed") >= 3)
    # an attendee whose only registrations are waitlisted
    wait_only = [a for a in attendees if a["regs"] and all(x["status"] == "waitlisted" for x in a["regs"])]
    if not wait_only:
        a = next(a for a in attendees if not a["regs"])
        s = next(s for s in sessions if s["full"] and s is not test and free(a, s))
        add_reg(a, s, "waitlisted", max(x["t"] for x in regs if x["session"] is s) + timedelta(hours=5))
        wait_only = [a]
    wait_only = wait_only[0]

    # two pre-existing double bookings (same attendee confirmed in two sessions in one block) for change 2
    overlaps = []
    for a in r.sample([a for a in attendees if a is not multi and a is not wait_only and any(x["status"] == "confirmed" for x in a["regs"])], 40):
        x0 = next(x for x in a["regs"] if x["status"] == "confirmed")
        others = [s for s in sessions if not s["full"] and s is not x0["session"] and s is not bad and (s["day"], s["slot"]) == (x0["session"]["day"], x0["session"]["slot"])
                  and s["chair"] != RESTRICTED and x0["session"]["chair"] != RESTRICTED and x0["session"] is not bad]
        if others:
            add_reg(a, r.choice(others), "confirmed")
            overlaps.append(a)
        if len(overlaps) == 2:
            break
    assert len(overlaps) == 2

    # unique latest registration (sort target), written 12-hour US style
    top = r.choice([x for x in regs if not x["session"]["full"] and x["status"] == "confirmed" and x["a"] is not multi])
    top["t"] = datetime(2026, 9, 10, 16, 45)

    regs.sort(key=lambda x: (x["session"]["num"], x["a"]["last"], x["a"]["first"], x["t"]))
    ids = r.sample(range(30001, 39999), len(regs))
    for i, x in enumerate(regs):
        x["id"] = f"R-{ids[i]}"
        x["ts_style"] = r.randrange(4)
        x["code_style"] = r.choices([0, 1, 2, 3], weights=[55, 20, 15, 10])[0]
        x["status_str"] = r.choice({"confirmed": ["Confirmed", "Confirmed", "confirmed", "CONFIRMED"],
                                    "waitlisted": ["Waitlisted", "waitlist", "Wait list"],
                                    "cancelled": ["Cancelled", "canceled"]}[x["status"]])
        x["amount_str"] = ("0.00" if x["amount"] == 0 else r.choice([f"${x['amount'] / 100:,.2f}", f"{x['amount'] / 100:.2f}", f"{x['amount'] // 100}" if x["amount"] % 100 == 0 else f"{x['amount'] / 100:.2f}"]))
        x["email_str"] = x["a"]["email"]
    top["ts_style"] = 1
    tw[0]["ts_style"], tw[1]["ts_style"], tw[2]["ts_style"] = 1, 0, 2
    for k, x in enumerate([x for x in regs if x["a"] is multi]):
        x["email_str"] = [multi["email"], multi["email"].title(), multi["email"].upper()][k % 3]
    assert sum(1 for x in regs if x["t"] == top["t"]) == 1

    # ------------------------------------------------------------------ write files
    room_rows = [{"room": x, "kind": "unique", "cols": [room_code(x["code"], 0), x["name"], x["building"], x["floor"],
                                                        cap_str(x["cap"], x["cap_style"]), x["setup"], x["accessible"]]} for x in rooms]
    rdup = r.sample([x for x in rooms if x is not test["room"] and x["cap"] != 1200], N_ROOM_EXACT + N_ROOM_CODE)
    for x in rdup[:N_ROOM_EXACT]:
        room_rows.append({"room": x, "kind": "exact_duplicate", "cols": list(room_rows[rooms.index(x)]["cols"])})
    for x in rdup[N_ROOM_EXACT:]:
        room_rows.append({"room": x, "kind": "same_code_written_differently", "cols": [room_code(x["code"], 1), x["name"].upper(), x["building"], x["floor"],
                                                                                     cap_str(x["cap"], (x["cap_style"] + 1) % 4), x["setup"], x["accessible"]]})
    r.shuffle(room_rows)
    for i, row in enumerate(room_rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "rooms.csv"), ["Room Code", "Room", "Building", "Floor", "Capacity", "Setup", "Accessible"],
              [row["cols"] for row in room_rows])

    for s in sessions:
        s["room_style"] = r.choices([0, 1, 2, 3], weights=[55, 15, 15, 15])[0]
        s["time_style"] = r.randrange(2)
        s["date_str"] = r.choice([s["day"].isoformat(), f"{s['day'].month}/{s['day'].day}/{s['day'].year}", s["day"].strftime("%d-%b-%Y"), f"{s['day'].strftime('%B')} {s['day'].day}, {s['day'].year}"])
        s["price_str"] = "Free" if s["price"] == 0 else r.choice([f"${s['price'] // 100}.00", f"{s['price'] // 100}", f"{s['price'] // 100}.00"])
    test["room_style"] = 2

    def sess_cols(s, code_style=0, title=None):
        start = s["start"]
        end = s.get("bad_end", s["end"])
        fmt = (lambda t: t.strftime("%H:%M")) if s["time_style"] == 0 else t12
        chair_email = s["chair"].lower().replace(" ", ".") + "@northboundevents.com"
        return [sess_code(s["num"], code_style), title or s["title"], s["track"], s["chair"], chair_email, s["date_str"], fmt(start), fmt(end),
                room_code(s["room"]["code"], s["room_style"]), s["price_str"]]

    sess_rows = [{"s": s, "kind": "unique", "cols": sess_cols(s)} for s in sessions]
    sdup = r.sample([s for s in sessions if s is not test and s is not bad and s["chair"] != RESTRICTED], N_SESS_EXACT + N_SESS_CODE)
    for s in sdup[:N_SESS_EXACT]:
        sess_rows.append({"s": s, "kind": "exact_duplicate", "cols": sess_cols(s)})
    for s in sdup[N_SESS_EXACT:]:
        sess_rows.append({"s": s, "kind": "same_code_written_differently", "cols": sess_cols(s, code_style=3, title=s["title"] + " ")})
    r.shuffle(sess_rows)
    for i, row in enumerate(sess_rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "sessions.csv"),
              ["Session", "Title", "Track", "Chair", "Chair Email", "Date", "Start", "End", "Room", "Price"], [row["cols"] for row in sess_rows])

    reg_rows = [{"x": x, "kind": "unique"} for x in regs]
    rdupes = r.sample([x for x in regs if x["session"] is not test and x is not top and x["a"] is not multi], N_REG_DUPES)
    for x in rdupes:
        reg_rows.insert(r.randint(0, len(reg_rows)), {"x": x, "kind": "exact_duplicate"})
    for i, row in enumerate(reg_rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "registrations.csv"),
              ["Registration ID", "Registered At", "First Name", "Last Name", "Email", "Company", "Session", "Status", "Amount"],
              [[w["x"]["id"], ts_str(w["x"]["t"], w["x"]["ts_style"]), w["x"]["a"]["first"], w["x"]["a"]["last"], w["x"]["email_str"],
                w["x"]["a"]["company"], sess_code(w["x"]["session"]["num"], w["x"]["code_style"]), w["x"]["status_str"], w["x"]["amount_str"]]
               for w in reg_rows])

    # ------------------------------------------------------------------ figures
    conf = [x for x in regs if x["status"] == "confirmed"]
    wait = [x for x in regs if x["status"] == "waitlisted"]
    canc = [x for x in regs if x["status"] == "cancelled"]
    revenue = sum(x["amount"] for x in conf)
    full = [s for s in sessions if sum(1 for x in conf if x["session"] is s) >= s["room"]["cap"]]
    assert all(sum(1 for x in conf if x["session"] is s) <= s["room"]["cap"] for s in sessions)
    assert len(full) == N_FULL
    mine = [x for x in regs if x["session"]["chair"] == RESTRICTED]
    badge_emails = sorted({x["a"]["email"] for x in conf})
    word_count = {}
    for c in companies:
        w = c[0].split()[0]
        word_count[w] = word_count.get(w, 0) + 1
    hay = " ".join([s["title"] for s in sessions] + [x["name"] for x in rooms] + CHAIRS + [f"{a['first']} {a['last']}" for a in attendees]).lower()
    s_cands = sorted([c for c in companies if word_count[c[0].split()[0]] == 1 and c[0].split()[0].lower() not in hay and len(c[0].split()[0]) >= 6
                      and 5 <= sum(1 for x in regs if x["a"]["company"] == c[0]) <= 14], key=lambda c: c[0])
    search_company = r.choice(s_cands)
    search_word = search_company[0].split()[0]
    other_scope = r.choice(sorted([x for x in regs if x["session"]["chair"] == CHAIRS[1] and x["status"] == "confirmed"], key=lambda x: x["id"]))
    setup_session = r.choice(sorted([s for s in sessions if not s["full"] and s is not bad and s["chair"] != RESTRICTED
                                     and sum(1 for x in conf if x["session"] is s) + 5 <= s["room"]["cap"]], key=lambda s: s["num"]))
    helena_cancel = r.choice(sorted([x for x in conf if x["session"] in helena_other], key=lambda x: x["id"]))
    other_cancel = r.choice(sorted([x for x in conf if x["session"]["chair"] == CHAIRS[2]], key=lambda x: x["id"]))

    def lines_of(x):
        return sorted(w["line"] for w in reg_rows if w["x"] is x)

    def reg(x):
        return {"id": x["id"], "attendee": f"{x['a']['first']} {x['a']['last']}", "email": x["a"]["email"], "file_email": x["email_str"],
                "company": x["a"]["company"], "session": sess_code(x["session"]["num"], 0), "file_session": sess_code(x["session"]["num"], x["code_style"]),
                "status": x["status"], "file_status": x["status_str"], "amount": usd(x["amount"]), "file_amount": x["amount_str"],
                "registered_at": x["t"].strftime("%Y-%m-%d %H:%M"), "file_registered_at": ts_str(x["t"], x["ts_style"]), "file_lines": lines_of(x)}

    def sess(s):
        c = [x for x in conf if x["session"] is s]
        return {"code": sess_code(s["num"], 0), "title": s["title"], "track": s["track"], "chair": s["chair"], "date": s["day"].isoformat(),
                "start": s["start"].strftime("%H:%M"), "end": s.get("bad_end", s["end"]).strftime("%H:%M"), "room": room_code(s["room"]["code"], 0),
                "room_name": s["room"]["name"], "file_room": room_code(s["room"]["code"], s["room_style"]), "capacity": s["room"]["cap"],
                "price": usd(s["price"]), "file_price": s["price_str"], "confirmed": len(c), "waitlisted": sum(1 for x in wait if x["session"] is s),
                "cancelled": sum(1 for x in canc if x["session"] is s), "revenue": usd(sum(x["amount"] for x in c)),
                "file_lines": sorted(w["line"] for w in sess_rows if w["s"] is s)}

    def room(x):
        return {"code": room_code(x["code"], 0), "name": x["name"], "capacity": x["cap"],
                "file_rows": [w["cols"] for w in room_rows if w["room"] is x], "file_lines": sorted(w["line"] for w in room_rows if w["room"] is x)}

    promoted = tw[0]
    rev_after = revenue - cancel_me["amount"] + promoted["amount"]
    test_wait_amounts = sum(x["amount"] for x in tw)
    track_rev = {t: usd(sum(x["amount"] for x in conf if x["session"]["track"] == t)) for t in TRACKS}
    fill_session = sorted([s for s in sessions if not s["full"] and s["chair"] != RESTRICTED and s is not bad and s["track"] in ("Finance", "People")],
                          key=lambda s: (-sum(1 for x in conf if x["session"] is s), s["room"]["cap"], s["num"]))[0]
    fc = sum(1 for x in conf if x["session"] is fill_session)
    # change 2 overlap test: multi attendee's first confirmed session; a non-full session in the same block and one in the next block
    m_conf = sorted([x for x in conf if x["a"] is multi], key=lambda x: (x["session"]["day"], x["session"]["slot"]))
    anchor = m_conf[0]["session"]
    same_block = sorted([s for s in sessions if (s["day"], s["slot"]) == (anchor["day"], anchor["slot"]) and s is not anchor and not s["full"] and s is not bad
                         and s is not setup_session], key=lambda s: s["num"])
    next_block = sorted([s for s in sessions if s["day"] == anchor["day"] and s["slot"] != anchor["slot"] and not s["full"] and s is not bad
                         and all((s["day"], s["slot"]) != (x["session"]["day"], x["session"]["slot"]) for x in multi["regs"])
                         and sum(1 for x in conf if x["session"] is s) < s["room"]["cap"]], key=lambda s: (s["slot"], s["num"]))
    # change 3 check-in: a confirmed registration in Helena's other session and a waitlisted one in the test session
    counts = {
        "seed": seed,
        "date_dependence": "No figure depends on the test date.",
        "rules": {
            "capacity": "confirmed registrations for a session never exceed its room's capacity",
            "waitlist_promotion": "when a confirmed registration in a full session is cancelled, the earliest-registered waitlisted registration becomes confirmed",
            "revenue": "sum of Amount over confirmed registrations only",
            "badge_export": "one badge per attendee (email, case-insensitive) with at least one confirmed registration",
        },
        "rooms": {"file_rows_excluding_header": len(room_rows), "exact_duplicate_rows": N_ROOM_EXACT, "same_code_rows": N_ROOM_CODE, "unique_rooms": N_ROOMS,
                  "largest": room(next(x for x in rooms if x["cap"] == 1200)),
                  "second_largest_capacity": second_cap,
                  "same_code_example": room(rdup[N_ROOM_EXACT]), "exact_duplicate_example": room(rdup[0]),
                  "smaller_room_for_move": room(smaller)},
        "sessions": {"file_rows_excluding_header": len(sess_rows), "exact_duplicate_rows": N_SESS_EXACT, "same_code_rows": N_SESS_CODE,
                     "unique_sessions": N_SESSIONS, "full_sessions": [sess_code(s["num"], 0) for s in sorted(full, key=lambda s: s["num"])],
                     "free_sessions": sum(1 for s in sessions if s["price"] == 0),
                     "impossible_times": sess(bad), "same_code_example": sess(sdup[N_SESS_EXACT]),
                     "test_session": sess(test), "wrong_confirmed_if_capacity_ignored": test["room"]["cap"] + 1, "restricted_chair_sessions": [sess(s) for s in [test] + helena_other],
                     "setup_session": sess(setup_session)},
        "registrations": {
            "file_rows_excluding_header": len(reg_rows), "exact_duplicate_rows": N_REG_DUPES, "unique_registrations": len(regs),
            "confirmed": len(conf), "waitlisted": len(wait), "cancelled": len(canc),
            "status_spellings": sorted({x["status_str"] for x in regs}),
            "revenue_confirmed": usd(revenue),
            "wrong_revenue_all_rows": usd(sum(x["amount"] for x in regs)),
            "wrong_revenue_confirmed_and_waitlisted": usd(revenue + sum(x["amount"] for x in wait)),
            "duplicate_example": reg(rdupes[0]),
            "latest": reg(top),
            "test_session_waitlist_in_file_order": [reg(x) for x in sorted(tw, key=lambda x: lines_of(x)[0])],
            "test_session_waitlist_amounts": usd(test_wait_amounts),
            "cancel_in_test_session": reg(cancel_me),
            "promoted": reg(promoted),
            "revenue_after_promotion": usd(rev_after),
            "revenue_change_on_promotion": usd(promoted["amount"] - cancel_me["amount"]),
            "restricted_chair_cancel": reg(helena_cancel),
            "other_chair_cancel": reg(other_cancel),
        },
        "badges": {"rows": len(badge_emails), "multi_attendee": {"name": f"{multi['first']} {multi['last']}", "company": multi["company"],
                                                                "confirmed_registrations": sum(1 for x in conf if x["a"] is multi),
                                                                "emails_as_written": sorted({x["email_str"] for x in regs if x["a"] is multi})},
                   "waitlist_only_attendee": {"name": f"{wait_only['first']} {wait_only['last']}", "email": wait_only["email"],
                                              "registrations": [reg(x) for x in wait_only["regs"]]},
                   "wrong_rows_one_per_registration": len(conf), "wrong_rows_case_sensitive_email": len({x["email_str"] for x in conf})},
        "baseline": {
            "STAFF_ROLE": "Session chair", "VIEWER_ROLE": "Read-only", "MAIN_ENTITY": "registration", "MAIN_ENTITY_PLURAL": "registrations",
            "SCOPE_RULE": f"registrations for the sessions {RESTRICTED} chairs", "SCOPE_COUNT": len(mine),
            "OUT_OF_SCOPE_EXAMPLE": reg(other_scope),
            "KPI_1": "Confirmed registrations", "KPI_1_VALUE": len(conf),
            "KPI_2": "Waitlisted registrations", "KPI_2_VALUE": len(wait),
            "KPI_3": "Revenue (confirmed registrations)", "KPI_3_VALUE": usd(revenue),
            "KPI_4": "Full sessions", "KPI_4_VALUE": len(full),
            "SCOPED_KPI_1_VALUE": sum(1 for x in conf if x["session"]["chair"] == RESTRICTED),
            "SEARCH_TERM": search_word, "SEARCH_COUNT": sum(1 for x in regs if x["a"]["company"] == search_company[0]),
            "FILTER_FIELD": "Status", "FILTER_VALUE": "Waitlisted", "FILTER_COUNT": len(wait),
            "SORT_FIELD": "Registered At", "SORT_TOP": reg(top),
            "EXPORT_ROWS": len(regs), "EXPORT_COLUMNS": ["Registration ID", "Attendee", "Email", "Session", "Status", "Amount"],
            "REQUIRED_FIELD": "Email",
        },
        "change_1_report": {"revenue_by_track": track_rev, "fill_rate_session": sess(fill_session) | {"fill_rate_pct": round(fc / fill_session["room"]["cap"] * 100, 1),
                                                                                  "fill_rate_pct_2dp": round(fc / fill_session["room"]["cap"] * 100, 2)},
                            "restricted_chair_session_count": 3},
        "change_2_overlap": {"attendee": {"name": f"{multi['first']} {multi['last']}", "email": multi["email"]}, "confirmed_in": sess(anchor),
                             "same_block_session": sess(same_block[0]), "other_block_session": sess(next_block[0]),
                             "existing_double_bookings": [{"attendee": f"{a['first']} {a['last']}", "email": a["email"],
                                                           "sessions": sorted(sess_code(x["session"]["num"], 0) for x in a["regs"] if x["status"] == "confirmed"
                                                                              and sum(1 for y in a["regs"] if y["status"] == "confirmed" and (y["session"]["day"], y["session"]["slot"]) == (x["session"]["day"], x["session"]["slot"])) > 1)}
                                                          for a in sorted(overlaps, key=lambda a: a["last"])]},
        "change_3_checkin": {"confirmed_in_restricted_session": reg(helena_cancel if False else sorted([x for x in conf if x["session"] in helena_other and x is not helena_cancel], key=lambda x: x["id"])[0]),
                             "waitlisted_in_test_session": reg(tw[2]), "other_chair_confirmed": reg(other_cancel)},
    }
    # every attendee other than the two planted ones has no double booking
    for a in attendees:
        blocks_c = [(x["session"]["day"], x["session"]["slot"]) for x in a["regs"] if x["status"] == "confirmed"]
        assert len(blocks_c) == len(set(blocks_c)) or a in overlaps
    write_json(os.path.join(REF_DIR, "counts.json"), counts)
    b = counts["baseline"]
    print(f"rooms {len(room_rows)} -> {N_ROOMS}; sessions {len(sess_rows)} -> {N_SESSIONS}; registrations {len(reg_rows)} -> {len(regs)} "
          f"(confirmed {len(conf)}, waitlisted {len(wait)}, cancelled {len(canc)}); revenue {usd(revenue)}; badges {len(badge_emails)}; Helena {b['SCOPE_COUNT']}")


def regs_of(s, regs):
    return [x for x in regs if x["session"] is s]


if __name__ == "__main__":
    main()
