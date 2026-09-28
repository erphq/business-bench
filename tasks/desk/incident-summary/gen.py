#!/usr/bin/env python3
"""incident-summary: half-year safety incidents by site and type for a metal fabrication shop.

    python gen.py [--seed N] [--naive DIR]
    python gen.py --list-traps
    python gen.py --traps-off site_names,voided --out DIR   # same draw, those pitfalls removed, same answer
    python gen.py --mutant relisted --out DIR               # a deliverable that falls for one trap

Business: a fabricator with four sites. Supervisors type incidents into a shared workbook (one sheet per
quarter) and the floor tablets collect near misses into their own export. EHS wants one summary.

Traps (each caught by a check, see task.yaml):
  * every site is written four or five ways across the sheets        (checks: Plant 2 incidents; Plant 1 lacerations)
  * the Q2 sheet re-lists late-entered Q1 incidents under the same id (checks: Plant 2 incidents; total incidents)
  * the Type column mixes the legend's codes with free text          (check: Plant 1 lacerations)
  * voided rows are still in the log                                 (check: total incidents)
  * near misses are a separate export and are not incidents          (checks: total incidents; warehouse near misses)
  * the warehouse has no incidents at all but is still a site        (check: warehouse near misses)
"""
from __future__ import annotations
import argparse
import calendar
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from bizgen.traps import TrapSet, add_trap_args, parse_trap_args, variant_dirs, active_trap_text  # noqa: E402

# Every trap in task.yaml, keyed. Switchable traps are removed at render time only, so build() and its
# random draws are identical in every variant and the correct answer never moves.
TRAPS = TrapSet(
    switchable={
        "site_names": "each site written four or five ways (off: the canonical site name everywhere)",
        "relisted": "late Q1 incidents repeated at the top of the Q2 sheet (off: listed once, on Q1)",
        "type_codes": "Type column mixes legend codes with free text (off: the legend's type names)",
        "voided": "voided / reported-in-error rows left in the log (off: not in the log)",
        "format_noise": "three date formats, merged titles, instruction rows, CSV preamble and BOM (off: clean files)",
    },
    fixed={
        "near_misses": "near misses are a separate export, reported on their own line, never in the incident count",
        "warehouse": "the Warehouse has no incidents but is still a site on the report",
    },
)
# task.yaml trap sentences, in order, and the trap each one describes
TRAP_KEYS = ["site_names", "relisted", "type_codes", "voided", "near_misses", "warehouse", "format_noise"]


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
                data = _re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                               rb"\g<1>2026-01-15T09:00:00Z\g<2>",
                               data)
            zi = _zip.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = _zip.ZIP_DEFLATED
            out.writestr(zi, data)
    write_bytes(path, buf.getvalue())

SITES = ["Plant 1", "Plant 2", "East Fab", "Warehouse"]
SITE_VARIANTS = {
    "Plant 1": ["Plant 1", "PLANT 1", "Plant #1", "Plant One", "plant 1"],
    "Plant 2": ["Plant 2", "PLANT 2", "Plant #2", "Plant Two"],
    "East Fab": ["East Fab", "EAST FAB", "East Fab Shop", "Fab East"],
    "Warehouse": ["Warehouse", "WAREHOUSE", "Warehouse 7"],
}
TYPES = [("Slip, trip or fall", "STF", ["STF", "slip trip fall", "Slip/trip", "Slip, trip or fall"]),
         ("Struck by object", "SB", ["SB", "Struck-by", "struck by object", "Struck by object"]),
         ("Caught in or between", "CI", ["CI", "caught in", "Caught in/between", "Caught in or between"]),
         ("Laceration", "LAC", ["LAC", "Lac.", "laceration", "Laceration"]),
         ("Chemical exposure", "CHEM", ["CHEM", "chem exposure", "Chemical exposure"]),
         ("Strain or sprain", "ERG", ["ERG", "strain", "Strain/sprain", "Strain or sprain"])]
TYPE_NAMES = [t[0] for t in TYPES]
SEVERITY = ["First aid only", "Recordable", "Recordable", "Lost time", "First aid only"]
VOID_WORDS = ["Voided - duplicate entry", "Reported in error", "Voided - not an injury"]
TOP = "Plant 1"          # the site the memo has to name
N_DUP = 3
N_VOID = 5
BODY = ["hand", "forearm", "shin", "shoulder", "ankle", "eye", "back", "finger"]
WHAT = ["stacking plate on the rack", "changing the plasma consumables", "moving a pallet with the walkie",
        "grinding a weld seam", "loading the press brake", "decanting solvent in the paint room",
        "pulling stock out of the rack", "clearing offcut from the saw"]


def build(seed: int) -> dict:
    r = rng(seed)
    # site weights: Plant 1 busiest, Warehouse has no injuries at all this half
    weights = {"Plant 1": 0.40, "Plant 2": 0.33, "East Fab": 0.27, "Warehouse": 0.0}
    incidents, seq = [], 400
    for m in range(1, 7):
        for _ in range(r.randint(16, 22)):
            seq += 1
            u, acc, site = r.random(), 0.0, "Plant 1"
            for s in SITES:
                acc += weights[s]
                if u <= acc:
                    site = s
                    break
            tname, code, variants = r.choice(TYPES) if site != "Plant 1" or r.random() > 0.34 else TYPES[3]
            incidents.append({"id": f"IR-2026-{seq}", "date": date(2026, m, r.randint(1, calendar.monthrange(2026, m)[1])),
                              "site": site, "type": tname, "variants": variants,
                              "sev": r.choice(SEVERITY), "who": " ".join(person(r)),
                              "desc": f"{r.choice(SEVERITY[:1] + ['Minor', 'Reported'])} injury to {r.choice(BODY)} while {r.choice(WHAT)}",
                              "void": False, "k": r.random()})
    incidents.sort(key=lambda x: (x["date"], x["k"]))
    for x in incidents:
        x["shown_site"] = r.choice(SITE_VARIANTS[x["site"]])
        x["shown_type"] = r.choice(x["variants"])
    # voided rows stay in the log
    for x in r.sample(incidents, N_VOID):
        x["void"] = True
        x["status"] = r.choice(VOID_WORDS)
    for x in incidents:
        x.setdefault("status", "Closed" if r.random() < 0.8 else "Open")
    # three Q1 incidents were entered late and are re-listed on the Q2 sheet
    q1 = [x for x in incidents if x["date"].month <= 3 and not x["void"]]
    dups = r.sample([x for x in q1 if x["site"] in ("Plant 2", "Plant 1")], N_DUP)
    for x in dups:
        x["relisted"] = True

    # near misses from the floor tablets, every site including the warehouse
    nm_weights = {"Plant 1": 0.31, "Plant 2": 0.24, "East Fab": 0.21, "Warehouse": 0.24}
    near = []
    for i in range(r.randint(62, 78)):
        u, acc, site = r.random(), 0.0, "Plant 1"
        for s in SITES:
            acc += nm_weights[s]
            if u <= acc:
                site = s
                break
        m = r.randint(1, 6)
        near.append({"id": f"NM-{5200 + i}", "date": date(2026, m, r.randint(1, calendar.monthrange(2026, m)[1])),
                     "site": site, "shown_site": r.choice(SITE_VARIANTS[site]),
                     "what": f"Near miss - {r.choice(WHAT)}", "who": " ".join(person(r)), "k": r.random()})
    near.sort(key=lambda x: (x["date"], x["k"]))

    live = [x for x in incidents if not x["void"]]
    grid = {(s, t): sum(1 for x in live if x["site"] == s and x["type"] == t) for s in SITES for t in TYPE_NAMES}
    site_tot = {s: sum(grid[(s, t)] for t in TYPE_NAMES) for s in SITES}
    type_tot = {t: sum(grid[(s, t)] for s in SITES) for t in TYPE_NAMES}
    nm_tot = {s: sum(1 for x in near if x["site"] == s) for s in SITES}
    return {"incidents": incidents, "live": live, "near": near, "dups": dups, "grid": grid,
            "site_tot": site_tot, "type_tot": type_tot, "nm_tot": nm_tot,
            "total": sum(site_tot.values()), "nm_total": len(near)}


def acceptable(d: dict) -> bool:
    grid, site_tot, nm_tot = d["grid"], d["site_tot"], d["nm_tot"]
    if site_tot["Warehouse"] != 0 or nm_tot["Warehouse"] < 8:
        return False
    ranked = sorted(SITES, key=lambda s: -site_tot[s])
    if ranked[0] != TOP or site_tot[ranked[0]] - site_tot[ranked[1]] < 4:
        return False
    # a naive group-by on the raw site strings must not name the true top site
    naive_groups = {}
    for x in d["incidents"]:
        naive_groups[x["shown_site"]] = naive_groups.get(x["shown_site"], 0) + 1
    if max(naive_groups, key=lambda k: naive_groups[k]) == TOP:
        return False

    def unique_in_row(site, value):
        row = [grid[(site, t)] for t in TYPE_NAMES] + [site_tot[site], nm_tot[site]]
        return row.count(value) == 1

    if not unique_in_row("Plant 2", site_tot["Plant 2"]) or not unique_in_row("Plant 1", grid[("Plant 1", "Laceration")]):
        return False
    if not unique_in_row("Warehouse", nm_tot["Warehouse"]):
        return False
    total_row = [d["type_tot"][t] for t in TYPE_NAMES] + [d["total"], d["nm_total"]]
    if total_row.count(d["total"]) != 1:
        return False
    if grid[("Plant 1", "Laceration")] < 8:
        return False
    # the shortcuts have to move the pinned figures
    dup_p2 = sum(1 for x in d["dups"] if x["site"] == "Plant 2")
    if dup_p2 < 1 or sum(1 for x in d["incidents"] if x["void"]) < 3:
        return False
    if all(x["site"] != "Plant 1" or x["type"] != "Laceration" for x in d["incidents"] if x["void"]):
        pass  # not required, the type-code trap already moves this cell
    return True


# --------------------------------------------------------------------------- deliverables

def _col(j: int) -> str:
    """Column letter for 0-based index j counted from A (chr for A..Z, as the reference always was)."""
    return chr(ord("A") + j) if j < 26 else _col(j // 26 - 1) + chr(ord("A") + j % 26)


def report_sheets(inc_rows: list[list], nm_rows: list[list], sites: list[str] = SITES,
                  types: list[str] = TYPE_NAMES) -> dict:
    n, nn = len(inc_rows) + 1, len(nm_rows) + 1
    rows = []
    for i, s in enumerate(sites, start=2):
        line = [s]
        for j in range(len(types)):
            c = _col(1 + j)
            line.append(f"=COUNTIFS(Incidents!$C$2:$C${n},$A{i},Incidents!$D$2:$D${n},{c}$1)")
        line.append(f"=SUM(B{i}:{_col(len(types))}{i})")
        line.append(f"=COUNTIF(NearMisses!$C$2:$C${nn},$A{i})")
        rows.append(line)
    last = 1 + len(sites)
    cols = [_col(1 + j) for j in range(len(types) + 2)]
    rows.append(["All sites"] + [f"=SUM({c}2:{c}{last})" for c in cols])
    rows.append([])
    rows.append(["Incidents exclude voided rows and near misses. Near misses come from the tablet export and are "
                 "counted separately."])
    return {
        "Incidents": {"header": ["incident_id", "date", "site", "type", "severity"], "rows": inc_rows,
                      "widths": {"C": 14, "D": 22}},
        "NearMisses": {"header": ["report_id", "date", "site"], "rows": nm_rows, "widths": {"C": 14}},
        "Report": {"header": ["Site"] + list(types) + ["Total incidents", "Near misses"], "rows": rows,
                   "widths": {"A": 14, "H": 16, "I": 14}},
    }


def ehs_email(traps: TrapSet) -> str:
    names = traps.on("site_names"); codes = traps.on("type_codes")
    first = ("I need the half-year safety numbers for the board and for the insurer: how many incidents at each "
             "of our four sites, broken out by type. Our sites are Plant 1, Plant 2, East Fab and the Warehouse")
    if names and codes:
        first += (" - the crews write them down however they feel like it (PLANT 2, Plant #2, Plant Two, it "
                  "is all the same place), and the type column is half legend codes and half whatever they typed. "
                  "The legend sheet in the workbook says what the codes mean.")
    elif names:
        first += (" - the crews write them down however they feel like it (PLANT 2, Plant #2, Plant Two, it "
                  "is all the same place).")
    elif codes:
        first += (". The type column is half legend codes and half whatever they typed. "
                  "The legend sheet in the workbook says what the codes mean.")
    else:
        first += "."
    last = ("Anything marked voided or reported in error is not an incident either. And every site goes on the "
            "report, even a site that had a clean half.\n\n" if traps.on("voided") else
            "Every site goes on the report, even a site that had a clean half.\n\n")
    return (first + "\n\n"
            "Near misses are not incidents. They matter, so give them their own line, but they never go into "
            "the incident count - the insurer reads that number literally.\n\n"
            + last +
            "In the memo tell me which site had the most incidents this half.")


def emit(seed: int, naive_dir: str | None, traps: TrapSet = TRAPS, out: str | None = None,
         mutant: str | None = None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    if mutant:
        write_mutant(d, mutant, out)
        return
    here = out or HERE
    ws, ref, sol = task_dirs(HERE) if out is None else variant_dirs(out)
    grid, site_tot, nm_tot = d["grid"], d["site_tot"], d["nm_tot"]
    noisy = traps.on("format_noise")
    names, codes, voids = traps.on("site_names"), traps.on("type_codes"), traps.on("voided")

    # ---- workspace ----
    def sheet_rows(month_lo, month_hi, extra=()):
        rows = []
        for x in list(extra) + [y for y in d["incidents"] if month_lo <= y["date"].month <= month_hi]:
            if x["void"] and not voids:
                continue
            rows.append([x["id"], date_variant(x["date"], sum(ord(c) for c in x["id"]) % 3) if noisy else x["date"],
                         x["shown_site"] if names else x["site"], x["shown_type"] if codes else x["type"],
                         x["desc"], x["sev"], x["who"], x["status"]])
        return rows

    hdr = ["Incident ID", "Date", "Site", "Type", "Description", "Severity", "Reported by", "Status"]
    if traps.on("relisted"):
        q1_rows, q2_rows = sheet_rows(1, 3), sheet_rows(4, 6, extra=sorted(d["dups"], key=lambda x: x["id"]))
        q2_pre = [["Late entries from Q1 are repeated at the top of this sheet"]]
    else:
        q1_rows, q2_rows = sheet_rows(1, 3), sheet_rows(4, 6)
        q2_pre = [["Site supervisors: enter every injury here"]]
    sheets = {
        "Q1": {"merged_title": "Incident log - Q1 2026", "preamble": [["Site supervisors: enter every injury here"]],
               "header": hdr, "rows": q1_rows, "widths": {"A": 14, "C": 14, "D": 20, "E": 46, "G": 20}},
        "Q2": {"merged_title": "Incident log - Q2 2026",
               "preamble": q2_pre,
               "header": hdr, "rows": q2_rows,
               "widths": {"A": 14, "C": 14, "D": 20, "E": 46, "G": 20}},
        "Legend": {"merged_title": "Type codes", "header": ["Code", "Type"],
                   "rows": [[code, name] for name, code, _ in TYPES], "widths": {"B": 24}},
    }
    if not noisy:
        for sheet in sheets.values():
            sheet.pop("merged_title", None); sheet.pop("preamble", None)
    stable_xlsx(os.path.join(ws, "incident_log_2026_h1.xlsx"), sheets, creator="EHS")
    write_csv(os.path.join(ws, "near_miss_tablet_export.csv"), ["Report ID", "Date", "Site", "What happened", "Logged by"],
              [[x["id"], date_variant(x["date"], 1) if noisy else x["date"].isoformat(),
                x["shown_site"] if names else x["site"], x["what"], x["who"]] for x in d["near"]],
              preamble=["Floor tablet export - near miss reports", "01/01/2026 - 06/30/2026"] if noisy else None, bom=noisy)
    write_email_thread(os.path.join(ws, "email_from_ehs.txt"), [
        {"from": "Aisha Okafor <aisha@ironwoodfab.com>", "to": "you", "date": "Wed, 8 Jul 2026 07:55",
         "subject": "half-year safety summary",
         "body": ehs_email(traps)}])

    # ---- reference ----
    write_csv(os.path.join(ref, "incidents_by_site_type.csv"), ["site", "type", "incidents"],
              [[s, t, grid[(s, t)]] for s in SITES for t in TYPE_NAMES])
    write_csv(os.path.join(ref, "site_totals.csv"), ["site", "incidents", "near_misses"],
              [[s, site_tot[s], nm_tot[s]] for s in SITES] + [["ALL", d["total"], d["nm_total"]]])
    write_json(os.path.join(ref, "notes.json"), {
        "top_site": TOP, "top_site_incidents": site_tot[TOP], "total_incidents": d["total"],
        "near_misses": d["nm_total"], "voided_rows": sum(1 for x in d["incidents"] if x["void"]),
        "relisted_ids": sorted(x["id"] for x in d["dups"]), "zero_incident_site": "Warehouse"})

    # ---- reference solution ----
    inc_rows = [[x["id"], x["date"].isoformat(), x["site"], x["type"], x["sev"]]
                for x in sorted(d["live"], key=lambda y: y["id"])]
    nm_rows = [[x["id"], x["date"].isoformat(), x["site"]] for x in sorted(d["near"], key=lambda y: y["id"])]
    stable_xlsx(os.path.join(sol, "incidents.xlsx"), report_sheets(inc_rows, nm_rows), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    spec = {
        "id": "incident-summary", "track": "desk", "category": "reports",
        "title": "Half-year safety incidents by site and type",
        "ask": ("Aisha needs the first-half safety numbers for the board and the insurer, by site and by type. "
                "Save it as incidents.xlsx with live formulas and put the headline in memo.md. Her email says how "
                "she counts them.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": active_trap_text([
            "each site is written four or five ways across the two sheets and the tablet export (PLANT 2, Plant #2, "
            "Plant Two, Fab East); a group-by on the raw site column splits every site and names the wrong worst site "
            "(checks: Plant 2 incidents; Plant 1 lacerations; memo names the worst site)",
            f"{N_DUP} late-entered Q1 incidents are repeated at the top of the Q2 sheet under their original ids; "
            "reading both sheets without deduplicating counts them twice (checks: Plant 2 incidents; total incidents)",
            "the Type column mixes the legend sheet's codes (STF, LAC, CHEM) with free text ('Lac.', 'strain', "
            "'struck by object'), so a raw pivot scatters one type across four columns (check: Plant 1 lacerations)",
            f"{N_VOID} rows are marked voided or reported in error and are not incidents (check: total incidents)",
            "near misses are a separate tablet export with no type column; they are reported on their own line and "
            "never inside the incident count (checks: total incidents; warehouse near misses)",
            "the Warehouse had no injuries at all this half but is still one of the four sites and still has near "
            "misses, so a group-by over the incident log drops it from the report (check: warehouse near misses)",
            "dates come in three formats, the workbook sheets carry a merged title and an instruction row, and the "
            "tablet export has a two-line preamble and a BOM (check: total incidents, all sites)",
        ], TRAP_KEYS, traps),
        "checks": [
            {"type": "file_exists", "name": "incidents.xlsx exists", "path": "incidents.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "incidents.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "incidents.xlsx"},
            {"type": "xlsx_value_present", "name": "Plant 2 incidents", "path": "incidents.xlsx",
             "expected": site_tot["Plant 2"], "rel_tol": 0.001, "near_text": "plant 2"},
            {"type": "xlsx_value_present", "name": "Plant 1 lacerations", "path": "incidents.xlsx",
             "expected": grid[("Plant 1", "Laceration")], "rel_tol": 0.001, "near_text": "plant 1"},
            {"type": "xlsx_value_present", "name": "total incidents, all sites", "path": "incidents.xlsx",
             "expected": d["total"], "rel_tol": 0.001, "near_text": "total"},
            {"type": "xlsx_value_present", "name": "warehouse near misses (site with no incidents still reported)",
             "path": "incidents.xlsx", "expected": nm_tot["Warehouse"], "rel_tol": 0.001, "near_text": "warehouse"},
            {"type": "text_numbers_present", "name": "memo carries the incident and near-miss totals", "path": "memo.md",
             "numbers": [d["total"], site_tot[TOP], d["nm_total"]], "rel_tol": 0.001},
            {"type": "text_sentence_matches", "name": "memo names the site with the most incidents", "path": "memo.md",
             "all": [r"\bplant\s*#?\s*1\b|\bplant one\b",
                     r"(\bmost\b|\bhighest\b|\bworst\b|\bmore incidents\b|\bled\b|\bleads\b|\btop\b)"],
             "none": [r"\bfewest\b", r"\bleast\b", r"\bcleanest\b"]},
        ],
    }
    if not traps.canonical:
        spec["variant"] = {"of": "incident-summary", "draw": seed, "traps_off": sorted(traps.off)}
    write_task_yaml(here, spec)
    print(f"seed={seed} incidents={len(d['incidents'])} live={len(d['live'])} near={len(d['near'])} "
          f"voided={sum(1 for x in d['incidents'] if x['void'])} relisted={[x['id'] for x in d['dups']]}")
    print("site totals:", site_tot, "near misses:", nm_tot)
    print("plant1 lacerations:", grid[("Plant 1", "Laceration")], "total:", d["total"], "nm total:", d["nm_total"])


def memo_text(d: dict) -> str:
    site_tot, nm_tot = d["site_tot"], d["nm_tot"]
    ranked = sorted(SITES, key=lambda s: -site_tot[s])
    lac = d["grid"][(TOP, "Laceration")]
    return f"""# Safety summary, January to June 2026

{d['total']} incidents were recorded across the four sites, alongside {d['nm_total']} near misses reported on the
floor tablets. Near misses are counted separately and are not in the incident figure.

**{TOP} had the most incidents this half, {site_tot[TOP]} of them**, ahead of {ranked[1]} on
{site_tot[ranked[1]]}. Lacerations are the single biggest category at {TOP} with {lac} of them, which is where the
next toolbox talk should go.

The Warehouse recorded no injuries at all this half, but it did log {nm_tot['Warehouse']} near misses, so it stays
on the report rather than dropping off it.

Two notes on the data: {sum(1 for x in d['incidents'] if x['void'])} rows in the log are marked voided or reported
in error and are excluded, and the {len(d['dups'])} late Q1 entries repeated at the top of the Q2 sheet are counted
once.
"""


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcut: read both sheets, group by the site and type columns as typed,
    keep voided rows, and pile the near misses in with the incidents."""
    os.makedirs(out, exist_ok=True)
    inc = []
    for x in sorted(d["incidents"], key=lambda y: y["id"]):
        inc.append([x["id"], x["date"].isoformat(), x["shown_site"], x["shown_type"], x["sev"]])
        if x in d["dups"]:
            inc.append([x["id"], x["date"].isoformat(), x["shown_site"], x["shown_type"], x["sev"]])
    for x in sorted(d["near"], key=lambda y: y["id"]):
        inc.append([x["id"], x["date"].isoformat(), x["shown_site"], "Near miss", ""])
    stable_xlsx(os.path.join(out, "incidents.xlsx"), report_sheets(inc, []), creator="naive")
    write_text(os.path.join(out, "memo.md"),
               f"# Safety summary\n\nThe log holds {len(d['incidents']) + len(d['near'])} entries for the half "
               "across the sites. Incidents are spread fairly evenly and no single site stands out.\n")


# --------------------------------------------------------------------------- per-trap mutants

def write_mutant(d: dict, trap: str, out: str) -> None:
    """incidents.xlsx and memo.md, right except that they fall for `trap`."""
    if trap not in TRAPS.names:
        raise KeyError(trap)
    inc = [x for x in d["incidents"] if not x["void"] or trap == "voided"]            # voided rows counted
    if trap == "relisted":                                                            # Q2 re-listings counted again
        inc = inc + list(d["dups"])
    if trap == "format_noise":                   # instruction row taken as the header: first data row of Q1 lost
        first_q1 = min((x for x in d["incidents"] if x["date"].month <= 3), key=lambda x: (x["date"], x["k"]))
        inc = [x for x in inc if x is not first_q1]
    near = list(d["near"])
    if trap == "format_noise":                   # the export's preamble line read as the header: first report lost
        near = near[1:]
    site = (lambda x: x["shown_site"]) if trap == "site_names" else (lambda x: x["site"])
    typ = (lambda x: x["shown_type"]) if trap == "type_codes" else (lambda x: x["type"])
    inc_rows = [[x["id"], x["date"].isoformat(), site(x), typ(x), x["sev"]] for x in sorted(inc, key=lambda y: y["id"])]
    nm_rows = [[x["id"], x["date"].isoformat(), site(x)] for x in sorted(near, key=lambda y: y["id"])]
    types = list(TYPE_NAMES)
    if trap == "type_codes":                     # a raw pivot: one column per spelling
        types = list(dict.fromkeys(r[3] for r in sorted(inc_rows, key=lambda r: r[3].lower())))
    if trap == "near_misses":                    # near misses folded into the incident log as one more type
        inc_rows += [[r[0], r[1], r[2], "Near miss", ""] for r in nm_rows]
        types.append("Near miss")
        nm_rows = []
    if trap == "site_names":                     # a group-by on the raw site column
        sites = list(dict.fromkeys(r[2] for r in sorted(inc_rows + nm_rows, key=lambda r: r[2].lower())))
    elif trap == "warehouse":                    # sites taken from the incident log only
        sites = [s for s in SITES if any(r[2] == s for r in inc_rows)]
    else:
        sites = list(SITES)
    os.makedirs(out, exist_ok=True)
    stable_xlsx(os.path.join(out, "incidents.xlsx"), report_sheets(inc_rows, nm_rows, sites, types), creator="mutant")
    tot = {s: sum(1 for r in inc_rows if r[2] == s) for s in sites}
    nm = {s: sum(1 for r in nm_rows if r[2] == s) for s in sites}
    ranked = sorted(sites, key=lambda s: -tot[s])
    text = (f"# Safety summary, January to June 2026\n\n{len(inc_rows)} incidents were recorded across the sites, "
            f"alongside {len(nm_rows)} near misses reported on the floor tablets.\n\n"
            f"**{ranked[0]} had the most incidents this half, {tot[ranked[0]]} of them**, ahead of {ranked[1]} on "
            f"{tot[ranked[1]]}.\n")
    if "Warehouse" in sites and tot["Warehouse"] == 0:
        text += f"\nThe Warehouse recorded no injuries this half and logged {nm['Warehouse']} near misses.\n"
    write_text(os.path.join(out, "memo.md"), text)


# near_misses is left out: folding the near misses into the incident count still shows the Warehouse's near-miss
# count on the Warehouse row (as its only incidents), so "warehouse near misses" cannot see that mistake; "total
# incidents, all sites" does. Recorded as a grader finding.
MUTANTS = {k: write_mutant for k in TRAP_KEYS if k != "near_misses"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    add_trap_args(ap)
    a = ap.parse_args()
    traps = parse_trap_args(a, TRAPS, MUTANTS, TRAP_KEYS)
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 400 attempts")
    # The acceptance loop always runs on the full task, so a variant or mutant shares the canonical draw.
    emit(a.seed * 1000 + attempt, a.naive, traps, a.out, a.mutant)
