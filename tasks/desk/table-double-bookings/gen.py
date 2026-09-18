#!/usr/bin/env python3
"""table-double-bookings: which dinner reservations clash on the same table, from the booking system export.

    python gen.py [--seed N] [--naive DIR]

Business: a neighbourhood restaurant taking reservations online and by phone. The booking system lets two
parties land on one table when a host moves people around or a phone booking is squeezed in, and the online
widget still takes bookings on days the restaurant is closed.

Traps (each caught by a check, see task.yaml):
  * a booking holds its table from its time for its duration; back-to-back is not a clash (check: clashing bookings)
  * blank durations take the turn time for the party size from the GM's note         (checks: clashing bookings; clashes with)
  * hosts move parties in the Notes ("moved to T9"); the Table column is stale, and one note
    names a table the guest asked for but did not get                                 (checks: clashing bookings; table)
  * bookings on closed days (Mondays, the private event) are not clashes             (check: clashing bookings)
  * cancelled bookings do not hold a table                                            (check: clashing bookings)
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

DAYS = [date(2026, 9, 15) + timedelta(days=i) for i in range(13)]      # Tue 15 Sep - Sun 27 Sep
PRIVATE = date(2026, 9, 24)
CLOSED = {d for d in DAYS if d.weekday() == 0} | {PRIVATE}
TABLES = [("T1", 2), ("T2", 4), ("T3", 2), ("T4", 4), ("T5", 4), ("T6", 6), ("T7", 2), ("T8", 4), ("T9", 4),
          ("T10", 6), ("T11", 2), ("T12", 8)]
SEATS = dict(TABLES)


def turn(party: int) -> int:
    return 90 if party <= 2 else 105 if party <= 4 else 120 if party <= 6 else 150


def build(seed: int) -> dict:
    r = rng(seed)
    bk = []

    def add(day, table, start, party, dur, status="Confirmed", note="", export_table=None, tag=""):
        b = {"day": day, "table": table, "export_table": export_table or table, "start": start, "party": party,
             "dur": dur, "status": status, "note": note, "tag": tag}
        bk.append(b)
        return b

    # baseline: open days, each table a sequence of sittings with gaps
    for day in DAYS:
        busy = 0.35 if day in CLOSED else (0.9 if day.weekday() >= 4 else 0.6)
        for t, seats in TABLES:
            cur = 17 * 60 + r.choice([0, 15, 30])
            while cur <= 21 * 60:
                if r.random() > busy:
                    cur += 45
                    continue
                party = r.randint(max(1, seats // 2), seats)
                dur = r.choice([75, 90, 105, 120]) if r.random() < 0.6 else None
                add(day, t, cur, party, dur)
                cur += (dur or turn(party)) + r.choice([0, 15, 15, 30, 30, 45])
    open_days = [d for d in DAYS if d not in CLOSED]

    def seq(day, t):
        return sorted([b for b in bk if b["day"] == day and b["table"] == t and b["status"] == "Confirmed"], key=lambda b: b["start"])

    def end(b):
        return b["start"] + (b["dur"] or turn(b["party"]))

    def pairs_after(b, day, t):
        s = seq(day, t)
        i = s.index(b)
        return s[i + 1] if i + 1 < len(s) else None

    # (b) blank-duration clash: a party of 5-6 with no duration, next sitting starts 105 min later
    for _ in range(2):
        day = r.choice(open_days); t = r.choice(["T6", "T10"])
        s = seq(day, t)
        cands = [(x, y) for x, y in zip(s, s[1:]) if y["start"] - x["start"] >= 105 and not x["tag"] and not y["tag"]]
        if not cands:
            continue
        x, y = r.choice(cands)
        x.update(party=r.choice([5, 6]), dur=None, tag="default_clash")
        y.update(start=x["start"] + 105, tag="default_clash")
    # (c) blank duration for a two-top, next sitting exactly 90 min later: not a clash
    for _ in range(2):
        day = r.choice(open_days); t = r.choice(["T1", "T3", "T7", "T11"])
        s = seq(day, t)
        cands = [(x, y) for x, y in zip(s, s[1:]) if y["start"] - x["start"] >= 90 and not x["tag"] and not y["tag"]]
        if not cands:
            continue
        x, y = r.choice(cands)
        x.update(party=2, dur=None, tag="default_ok")
        y.update(start=x["start"] + 90, tag="default_ok")
    # (d) plain overlaps with explicit durations: a phone booking squeezed in
    for _ in range(3):
        day = r.choice(open_days); t = r.choice(["T2", "T4", "T5", "T8", "T9"])
        s = seq(day, t)
        cands = [(x, y) for x, y in zip(s, s[1:]) if not x["tag"] and not y["tag"] and y["start"] - x["start"] >= 90]
        if not cands:
            continue
        x, y = r.choice(cands)
        x.update(dur=105, tag="plain")
        y.update(start=x["start"] + r.choice([60, 75]), dur=y["dur"] or 90, tag="plain")
    # (e) a move that creates a real clash: exported on table A, moved to B onto an existing sitting
    day = r.choice(open_days)
    z = r.choice([b for b in seq(day, "T9") if not b["tag"]] or seq(day, "T9"))
    a_table = "T4"
    m = add(day, "T9", z["start"] + 30, r.randint(2, 4), 90, note=r.choice(["moved to T9 - window request", "Moved to table 9 (window)"]),
            export_table=a_table, tag="move_clash")
    z["tag"] = "move_clash"
    # (f) a move that removes a clash: exported on T2 over an existing sitting, moved to a free slot on T11
    day2 = r.choice([d for d in open_days if d != day])
    w = r.choice([b for b in seq(day2, "T2") if not b["tag"]] or seq(day2, "T2"))
    f = add(day2, "T11", w["start"] + 15, 2, 75, note=r.choice(["host moved to T11", "moved to T11, quieter"]), export_table="T2",
            tag="move_ok")
    # clear T11 around f so the moved booking lands in a free slot
    for b in list(bk):
        if b is not f and b["day"] == day2 and b["table"] == "T11" and b["status"] == "Confirmed" and \
           b["start"] < end(f) + 15 and end(b) > f["start"] - 15:
            bk.remove(b)
    # (g) a note that names a table without a move
    day3 = r.choice(open_days)
    s = seq(day3, "T8")
    g = r.choice([b for b in s if not b["tag"]])
    g.update(note=r.choice(["asked for T12 (big booth) - not available", "wanted T12, told them it's booked"]), tag="note_decoy")
    # (h) closed days: overlapping bookings made on the online widget
    for day in sorted(CLOSED):
        for t in r.sample(["T2", "T4", "T5", "T9"], 2):
            s = seq(day, t)
            if s:
                x = s[0]
                add(day, t, x["start"] + 45, r.randint(2, 4), 90, note="booked online", tag="closed_clash")
    # (i) cancelled bookings on top of confirmed ones
    for _ in range(3):
        day = r.choice(open_days); t = r.choice(["T1", "T4", "T6", "T10"])
        s = seq(day, t)
        if not s:
            continue
        x = r.choice(s)
        add(day, t, x["start"] + 30, x["party"], x["dur"], status="Cancelled", note=r.choice(["guest cancelled", "cxl by phone", ""]),
            tag="cancelled")
    # ids in booking-creation order (random), exported in date/time order
    order = list(range(len(bk)))
    r.shuffle(order)
    for n, i in enumerate(order):
        bk[i]["id"] = f"R{40100 + n * 3 + r.randint(0, 2)}"
    return {"bookings": bk}


def clashes(bk, *, moves=True, decoy_moves=False, default=turn, closed=False, cancelled=False, touching=False):
    live = []
    for b in bk:
        if b["day"] in CLOSED and not closed:
            continue
        if b["status"] == "Cancelled" and not cancelled:
            continue
        table = b["export_table"]
        if moves:
            m = re.search(r"moved to (?:t|table )?\s*(\d+)", b["note"], re.I)
            if m:
                table = f"T{m.group(1)}"
        if decoy_moves:
            m = re.search(r"\bT(\d+)\b", b["note"])
            if m:
                table = f"T{m.group(1)}"
        s = b["start"]; e = s + (b["dur"] if b["dur"] else default(b["party"]))
        live.append((b, table, s, e))
    out = set()
    for i in range(len(live)):
        for j in range(i + 1, len(live)):
            a, ta, sa, ea = live[i]; c, tc, sc, ec = live[j]
            if a["day"] != c["day"] or ta != tc:
                continue
            if (sa < ec and sc < ea) or (touching and (sa <= ec and sc <= ea)):
                out.add(tuple(sorted((a["id"], c["id"]))) + (ta,))
    return out


def acceptable(d: dict) -> bool:
    bk = d["bookings"]
    ids = [b["id"] for b in bk]
    if len(set(ids)) != len(ids):
        return False
    t = clashes(bk)
    ids_in = [x for p in t for x in p[:2]]
    if len(ids_in) != len(set(ids_in)) or not (6 <= len(t) <= 10):
        return False
    tags = {b["id"]: b["tag"] for b in bk}
    kinds = {tags[p[0]] for p in t} | {tags[p[1]] for p in t}
    if not {"default_clash", "plain", "move_clash"} <= kinds:
        return False
    if sum(1 for p in t if tags[p[0]] == "default_clash") != 2 or sum(1 for b in bk if b["tag"] == "cancelled") != 3:
        return False
    # every naive reading must change the answer
    variants = [clashes(bk, moves=False), clashes(bk, decoy_moves=True), clashes(bk, default=lambda p: 90),
                clashes(bk, default=lambda p: 120), clashes(bk, closed=True), clashes(bk, cancelled=True),
                clashes(bk, touching=True)]
    if any(v == t for v in variants):
        return False
    # the moved-in clash must be on the moved-to table, not the exported one
    mc = next(b for b in bk if b["tag"] == "move_clash" and b["export_table"] != b["table"])
    if not any(mc["id"] in p[:2] and p[2] == mc["table"] for p in t):
        return False
    # the decoy note must create a false clash if read as a move
    return True


def hhmm(m: int) -> str:
    h, mm = divmod(m, 60)
    return f"{(h - 1) % 12 + 1}:{mm:02d} {'PM' if h >= 12 else 'AM'}"


HEADER = ["reservation", "date", "table", "conflicts_with"]


def rows_for(pairs) -> list[list]:
    rows = []
    for a, c, t in pairs:
        rows.append([a, t, c]); rows.append([c, t, a])
    return rows


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    bk = d["bookings"]
    byid = {b["id"]: b for b in bk}
    if naive_dir:
        # Table column as exported, blank durations as two hours, every row in the export
        os.makedirs(naive_dir, exist_ok=True)
        pairs = clashes(bk, moves=False, default=lambda p: 120, closed=True, cancelled=True)
        write_csv(os.path.join(naive_dir, "conflicts.csv"), HEADER,
                  [[a, byid[a]["day"].isoformat(), t, c] for a, t, c in sorted(rows_for(pairs))])
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 5)
    guests = people(r, len(bk))
    exp = []
    for b, (gf, gl) in zip(sorted(bk, key=lambda z: (z["day"], z["start"], z["export_table"])), guests):
        exp.append([b["id"], b["day"].strftime("%a %m/%d/%Y"), hhmm(b["start"]), b["party"], b["export_table"],
                    b["dur"] if b["dur"] else "", b["status"], f"{gl}, {gf}", phone_variant(phone_digits(r), r.randrange(7)),
                    b["note"], "Online" if b["tag"] == "closed_clash" else r.choice(["Online", "Online", "Phone"])])
    write_csv(os.path.join(ws, "reservations_export_2026-09-15_to_09-27.csv"),
              ["Res #", "Date", "Time", "Party", "Table", "Duration (min)", "Status", "Guest", "Phone", "Notes", "Source"],
              exp, bom=True, crlf=True)
    write_csv(os.path.join(ws, "tables.csv"), ["Table", "Seats", "Area"],
              [[t, s, "Patio" if t in ("T11", "T12") else "Window" if t in ("T8", "T9") else "Main room"] for t, s in TABLES])
    write_text(os.path.join(ws, "note_from_gm.txt"), (
        "Double bookings - next two weeks\n\n"
        "We've had two nights this month with two parties standing at the same table. Before it happens again, "
        "go through the reservations export for 15-27 September and find every booking that clashes with another "
        "booking on the same table.\n\n"
        "How to read the export:\n"
        "- A booking holds its table from its time for its duration. If one party's time is up at 7:30 and the "
        "next is booked for 7:30, that's fine - we turn it.\n"
        "- If Duration is blank, use our standard turn times: parties of 1-2 get 90 minutes, 3-4 get 1 hour 45, "
        "5-6 get 2 hours, 7 or more get 2 and a half hours.\n"
        "- When a host moves a party, the system doesn't change the Table column. The host writes it in Notes "
        "(\"moved to T9\"). The note is where they're actually sitting.\n"
        "- Cancelled bookings don't hold a table.\n"
        "- We're closed Mondays, and Thursday the 24th is the Hartley wedding (whole restaurant). The online widget "
        "still lets people book those days - Sam is calling them, so leave those out of this list.\n\n"
        "What I want: conflicts.csv with one line per clashing booking - reservation number, date (2026-09-15 style), "
        "table, and the reservation number it clashes with. Both bookings in a clash get a line.\n\n"
        "- Marisol\n"))

    pairs = clashes(bk)
    rows = sorted([[a, byid[a]["day"].isoformat(), t, c] for a, t, c in rows_for(pairs)])
    write_csv(os.path.join(ref, "conflicts.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "conflicts.csv"), HEADER, rows)
    moved = [b["id"] for b in bk if b["tag"] == "move_clash" and b["export_table"] != b["table"]]
    move_partner = [p[1] if p[0] in moved else p[0] for p in pairs if set(p[:2]) & set(moved)]
    default_ids = [x for p in pairs for x in p[:2] if byid[x]["tag"] == "default_clash"]
    write_json(os.path.join(ref, "notes.json"), {
        "pairs": sorted([list(p) for p in pairs]),
        "tags": {b["id"]: b["tag"] for b in bk if b["tag"]},
        "variants": {name: sorted([list(p) for p in v]) for name, v in [
            ("ignore_moves", clashes(bk, moves=False)), ("decoy_note_as_move", clashes(bk, decoy_moves=True)),
            ("blank_as_90", clashes(bk, default=lambda p: 90)), ("blank_as_120", clashes(bk, default=lambda p: 120)),
            ("closed_days", clashes(bk, closed=True)), ("cancelled", clashes(bk, cancelled=True)),
            ("touching", clashes(bk, touching=True))]}})
    write_task_yaml(HERE, {
        "id": "table-double-bookings", "track": "desk", "category": "spreadsheet",
        "title": "Find double-booked tables in the reservations",
        "ask": ("Marisol wants every double-booked table in the next two weeks of reservations found before service. "
                "Go through the booking export and save conflicts.csv - her note explains how bookings work.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "a booking holds its table for its duration, so clashes are overlapping windows, not equal times; several "
            "sittings are back-to-back (one ends at 7:30, the next starts at 7:30) and are not clashes "
            "(check: clashing bookings)",
            "four in ten bookings have a blank Duration and take the turn time for the party size; two clashes on the "
            "six-tops exist only at the two-hour turn time, while two-top and four-top sittings that follow a blank "
            "booking clash only if every blank is read as two hours "
            "(checks: clashing bookings; clashes with)",
            "a host moved a party to T9 in the Notes while the Table column still says T4, creating a real clash on T9; "
            "another party exported on T2 was moved to T11, so the apparent T2 clash is not one "
            "(checks: clashing bookings; table)",
            "one note names T12 as the table a guest asked for and did not get; reading any table number in Notes as a "
            "move invents a clash on T12 (check: clashing bookings)",
            "the online widget took overlapping bookings on Monday 21 September and on the private-event Thursday; the "
            "note leaves closed days out (check: clashing bookings)",
            "three cancelled bookings sit on top of confirmed ones (check: clashing bookings)",
            "dates are 'Tue 09/15/2026', times are 12-hour, and the export carries a BOM and CRLF endings "
            "(check: clashes with)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "conflicts.csv", "columns": HEADER},
            {"type": "csv_set_equal", "name": "clashing bookings", "path": "conflicts.csv", "column": "reservation",
             "ref": "conflicts.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "conflicts.csv", "equals_ref": "conflicts.csv"},
            {"type": "csv_values_match", "name": "table", "path": "conflicts.csv", "ref": "conflicts.csv", "key": "reservation",
             "columns": ["table"], "min_accuracy": 1.0, "must_match_keys": moved + move_partner},
            {"type": "csv_values_match", "name": "clashes with", "path": "conflicts.csv", "ref": "conflicts.csv",
             "key": "reservation", "columns": ["conflicts_with", "date"], "min_accuracy": 1.0, "must_match_keys": default_ids},
        ],
    })
    print(f"seed={seed} bookings={len(bk)} pairs={sorted(pairs)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(3000):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
