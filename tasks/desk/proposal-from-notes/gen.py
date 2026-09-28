#!/usr/bin/env python3
"""proposal-from-notes: an electrical contractor's site-walk and call notes to a lighting retrofit proposal.

    python gen.py [--seed N]
    python gen.py --list-traps
    python gen.py --traps-off poles,old_rates --out DIR   # same draw, those pitfalls removed, same answer
    python gen.py --mutant lift --out DIR                 # a deliverable that falls for one trap

Traps (each caught by a check, see task.yaml):
  * the high-bay count is 22 on the site walk, "maybe 24" on the first call and 26 on the later recount; the call
    notes are newest first, so the last number in the file is the stale one           (checks: high bay line; disposal line; total)
  * the lift is two days on the site walk and three days after the recount           (checks: lift line; total)
  * disposal is charged per fixture removed across all three fixture types, so the recount moves it too
                                                                                      (checks: disposal line; total)
  * the client wants occupancy sensors priced as an option, separately, not in the total (checks: optional sensors priced separately; total)
  * the parking lot pole lights were dropped on the later call                        (checks: pole lights dropped; total)
  * the rate card carries last year's prices in the first price column                (checks: other lines priced from the 2026 rates; total)
  * last job's proposal is in the folder as a format example, with another client's name and figures
                                                                                      (check: no leftovers from the old proposal)
"""
from __future__ import annotations
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from bizgen.traps import TrapSet, add_trap_args, parse_trap_args, variant_dirs, active_trap_text  # noqa: E402

# Every trap in task.yaml, keyed. Switches only change the notes, the rate card and the example file; build() and
# the reference never move.
TRAPS = TrapSet(
    switchable={
        "highbay_count": "the call log is newest first, so the last high-bay count in the file is the stale one; off: "
                         "the log runs oldest first (the 22, 24 and 26 counts all stay)",
        "lift": "the lift is two days on the site walk and three after the recount; off: three days throughout",
        "disposal": "disposal is per fixture across all three fixture types; off: the latest call spells out the 46 "
                    "fixtures to haul away",
        "poles": "the parking lot poles are in the site walk and dropped on the later call; off: never mentioned",
        "old_rates": "the rate card's first price column is last year's; off: only the 2026 column",
        "old_proposal": "last year's proposal for another client sits in the folder; off: not in the folder",
    },
    fixed={
        "sensors": "occupancy sensors priced as a separate option, one per high bay, out of the total",
    },
)
# task.yaml trap sentences, in order, and the trap each one describes
TRAP_KEYS = ["highbay_count", "lift", "disposal", "sensors", "poles", "old_rates", "old_proposal"]

CONTRACTOR = "Hollowell Electric"

def build(seed: int) -> dict:
    r = rng(seed)
    clients = [c for c in COMPANIES if c[2] in ("logistics", "manufacturing", "food", "retail") and "&" not in c[0] and "Ironwood" not in c[0]]
    client = r.choice(clients)[0]
    fm_first, fm_last = person(r)
    while True:
        rate = {
            "highbay": float(r.randrange(265, 321, 5)), "wallpack": float(r.randrange(185, 241, 5)), "troffer": float(r.randrange(120, 161, 5)),
            "pole": float(r.randrange(540, 721, 10)), "sensor": float(r.randrange(68, 96)), "disposal": float(r.randrange(12, 19)),
            "lift": float(r.randrange(385, 461, 5)), "permit": float(r.randrange(240, 321, 5))}
        old = {k: round(v * r.uniform(0.92, 0.95)) * 1.0 for k, v in rate.items()}
        qty = {"highbay": 26, "wallpack": 6, "troffer": 14, "disposal": 46, "lift": 3, "permit": 1}
        amt = {k: qty[k] * rate[k] for k in qty}
        total = sum(amt.values())
        sensors = 26 * rate["sensor"]
        naive = {"highbay": 22 * rate["highbay"], "disposal": 42 * rate["disposal"], "lift": 2 * rate["lift"]}
        figures = list(amt.values()) + [total, sensors, 5 * rate["pole"], rate["pole"]] + list(naive.values())
        if len({round(x, 2) for x in figures}) == len(figures) and all(old[k] != rate[k] for k in rate):
            break
    return dict(client=client, fm=f"{fm_first} {fm_last}", rate=rate, old=old, qty=qty, amt=amt, total=total, sensors=sensors)

LABEL = {"highbay": "LED high bay fixture, 150W, installed (replaces 400W metal halide)", "wallpack": "LED wall pack, 60W, installed",
         "troffer": "LED 2x4 troffer retrofit kit, installed", "pole": "Parking lot pole light LED retrofit, installed",
         "sensor": "Occupancy sensor, high bay mount, installed", "disposal": "Fixture removal, disposal and lamp recycling (per fixture)",
         "lift": "Boom lift rental (per day)", "permit": "City of Tacoma electrical permit (lighting alteration)"}
UNIT = {"highbay": "each", "wallpack": "each", "troffer": "each", "pole": "each", "sensor": "each", "disposal": "per fixture", "lift": "per day", "permit": "flat"}

def m(x: float) -> str: return f"${x:,.2f}"

def site_walk(client: str, fm: str, traps: TrapSet) -> str:
    return (f"SITE WALK - {client} warehouse, 1840 Water St, Tacoma\n3 Sep 2026 - Marcus\nMet {fm} (facilities)\n\n"
        "Main floor: 22 old 400W metal halide high bays, half of them flickering. Ceiling about 28 ft, so we need the boom lift - "
        + ("figure 2 days.\n" if traps.on("lift") else "figure 3 days.\n") +
        "Loading dock: 6 wall packs, all HPS, 2 dead.\n"
        "Office area: 14 2x4 troffers, T8. They want those done at the same time.\n"
        + ("Parking lot: 5 pole lights, asked us to look at them too.\n" if traps.on("poles") else "") +
        "They asked about occupancy sensors on the high bays since half the aisles are empty most of the day.\n"
        "Permit: yes, Tacoma wants a lighting alteration permit for this size job.\n"
        "We haul away and recycle all the old fixtures (per fixture charge on the rate card).\n")


def call_notes(client: str, fm: str, traps: TrapSet) -> str:
    newest = (f"2026-09-10  Dana (call with {fm})\n"
        "- Their maintenance lead recounted: 26 high bays, not 22. There are 4 more over the mezzanine we couldn't see from the floor.\n"
        + ("- Parking lot poles are OFF the job. The city is redoing the lot next spring and the poles go with it.\n" if traps.on("poles") else "") +
        "- Office troffers confirmed, 14.\n"
        + ("- With 26 fixtures Marcus says the lift is 3 days, not 2.\n" if traps.on("lift") else "- Marcus confirms the lift is 3 days.\n")
        + ("" if traps.on("disposal") else
           "- Disposal: 46 fixtures to haul away and recycle (26 high bays, 6 wall packs, 14 troffers).\n") +
        "- Occupancy sensors: they want the price, one per high bay, but as a separate option they can add later. Keep it out of the main total.\n"
        "- Needs the proposal by Sept 18 for their budget meeting.\n")
    older = ("2026-09-05  Marcus (follow-up call)\n"
        "- Asked if the count includes the office. Told him no. He thinks maybe 24 high bays total, will have maintenance recount.\n"
        "- Wall packs: 6 confirmed.\n"
        "- Asked whether removal/disposal is included - told him it's its own line, per fixture.\n")
    if traps.on("highbay_count"):
        return f"{client.upper()} - LIGHTING RETROFIT - CALL LOG (newest at top)\n\n" + newest + "\n" + older
    return f"{client.upper()} - LIGHTING RETROFIT - CALL LOG (oldest at top)\n\n" + older + "\n" + newest


def emit(seed: int, traps: TrapSet = TRAPS, out: str | None = None, mutant: str | None = None) -> None:
    d = build(seed); R = d["rate"]; Q = d["qty"]; A = d["amt"]; client = d["client"]; fm = d["fm"]
    if mutant:
        return write_mutant(d, mutant, out)
    here = out or HERE
    ws, ref, sol = task_dirs(HERE) if out is None else variant_dirs(out)
    if out is not None:  # the custom check travels with the copy so it can be graded on its own
        import shutil
        shutil.copyfile(os.path.join(HERE, "check.py"), os.path.join(out, "check.py"))
    write_text(os.path.join(ws, "site_walk_notes_2026-09-03.txt"), site_walk(client, fm, traps))
    write_text(os.path.join(ws, "call_notes.txt"), call_notes(client, fm, traps))
    items = ["highbay", "wallpack", "troffer", "pole", "sensor", "disposal", "lift", "permit"]
    if traps.on("old_rates"):
        rows = [[k.upper()[:3] + "-" + str(100 + i), LABEL[k], UNIT[k], d["old"][k], R[k]] for i, k in enumerate(items)]
        header, fmts, widths = ["Code", "Item", "Unit", "2025 price", "2026 price"], {"D": "$#,##0.00", "E": "$#,##0.00"}, {"A": 10, "B": 58, "C": 12, "D": 12, "E": 12}
    else:
        rows = [[k.upper()[:3] + "-" + str(100 + i), LABEL[k], UNIT[k], R[k]] for i, k in enumerate(items)]
        header, fmts, widths = ["Code", "Item", "Unit", "2026 price"], {"D": "$#,##0.00"}, {"A": 10, "B": 58, "C": 12, "D": 12}
    write_xlsx(os.path.join(ws, "rate_card.xlsx"), {"Rates": {
        "merged_title": f"{CONTRACTOR} - commercial lighting rate card", "preamble": [["2026 rates apply to proposals issued after July 1, 2026"]],
        "header": header, "rows": rows,
        "number_formats": fmts, "widths": widths}}, creator="Hollowell Electric")
    if traps.on("old_proposal"):
        write_text(os.path.join(ws, "proposal_ironwood_2025.md"),
          f"# Proposal: Shop Lighting Upgrade\n\n**{CONTRACTOR}**  \nPrepared for: Ironwood Fabrication, 77 Mill Rd, Tacoma  \nDate: November 4, 2025\n\n"
          "## Scope\n\nReplace existing fluorescent strip lights in the fabrication shop with LED fixtures.\n\n"
          "## Pricing\n\n| Item | Qty | Unit price | Amount |\n|---|---|---|---|\n"
          "| LED strip fixture, 8 ft, installed | 40 | $142.00 | $5,680.00 |\n| Fixture disposal (per fixture) | 40 | $13.00 | $520.00 |\n"
          "| Scissor lift rental (per day) | 1 | $310.00 | $310.00 |\n\n**Total: $6,510.00**\n\n"
          "## Terms\n\nPrice valid for 30 days. 40% deposit to schedule, balance on completion.\n\nThank you for considering Hollowell Electric.\n")

    write_text(os.path.join(sol, "proposal.md"), proposal_text(d))
    write_json(os.path.join(ref, "notes.json"), {"rates_2026": R, "rates_2025": d["old"], "qty": Q, "amounts": A, "total": d["total"],
                                                  "sensors_option": d["sensors"], "pole_unit": R["pole"], "pole_amount": 5 * R["pole"]})

    def amt_rx(x: float) -> str:
        whole = int(round(x)); s = f"{whole:,}"
        return rf"(?<![\d.,])({s.replace(',', ',?')})(\.00)?(?![\d]|\.\d|,\d)"
    spec = {
        "id": "proposal-from-notes", "track": "desk", "category": "drafting",
        "title": "Write up the warehouse lighting proposal",
        "ask": f"Please write up the lighting retrofit proposal for {client} from Marcus's site walk and the call notes, priced from our rate card. Save it as proposal.md.\n",
        "followup": None, "timeout_s": 1200,
        "traps": active_trap_text([
            "the high-bay count is 22 on the site walk, 'maybe 24' on the 5 September call and 26 after the 10 September recount; the call log is newest first, so the last count in the file is the stale one (checks: high bay line; disposal line; total)",
            "the lift is two days on the site walk and three days after the recount (checks: lift line; total)",
            "disposal is charged per fixture removed across high bays, wall packs and troffers (46), so the recount moves it too (checks: disposal line; total)",
            "the client wants the occupancy sensors priced as a separate option, one per high bay, and kept out of the total (checks: optional sensors priced separately; total)",
            "the parking lot pole lights were dropped on the later call; pricing them fails (checks: pole lights dropped; total)",
            "the rate card's first price column is last year's; every line must use the 2026 column (checks: other lines priced from the 2026 rates; total)",
            "last year's Ironwood Fabrication proposal sits in the folder as a format example with another client's name and figures (check: no leftovers from the old proposal)",
        ], TRAP_KEYS, traps),
        "checks": [
            {"type": "text_sentence_matches", "name": "high bay line", "path": "proposal.md",
             "all": [r"high[\s-]?bay", r"(?<![\d.,$])26(?!\d|,\d|\.\d)", amt_rx(A["highbay"])]},
            {"type": "text_sentence_matches", "name": "disposal line", "path": "proposal.md",
             "all": [r"(dispos|recycl|haul)", r"(?<![\d.,$])46(?!\d|,\d|\.\d)", amt_rx(A["disposal"])]},
            {"type": "text_sentence_matches", "name": "lift line", "path": "proposal.md",
             "all": [r"\blift\b", amt_rx(A["lift"])]},
            {"type": "text_numbers_present", "name": "other lines priced from the 2026 rates", "path": "proposal.md",
             "numbers": [A["wallpack"], A["troffer"], A["permit"]], "rel_tol": 0.0001},
            {"type": "text_sentence_matches", "name": "total", "path": "proposal.md",
             "all": [r"\btotal\b", amt_rx(d["total"])]},
            {"type": "text_sentence_matches", "name": "optional sensors priced separately", "path": "proposal.md",
             "all": [r"sensor", amt_rx(d["sensors"])]},
            {"type": "custom", "name": "pole lights dropped", "module": "check.py"},
            {"type": "text_not_contains", "name": "no leftovers from the old proposal", "path": "proposal.md", "phrases": ["Ironwood", "6,510", "5,680"]},
        ],
    }
    if not traps.canonical:
        spec["variant"] = {"of": "proposal-from-notes", "draw": seed, "traps_off": sorted(traps.off)}
    write_task_yaml(here, spec)


def proposal_text(d: dict, qty: dict | None = None, rate: dict | None = None, extra: list | None = None,
                  sensors_in_total: bool = False, prepared_for: str | None = None) -> str:
    """The proposal; the reference solution with no arguments, a mutant with one of them changed."""
    R = rate or d["rate"]; Q = dict(d["qty"], **(qty or {})); client = d["client"]; fm = d["fm"]
    order = ["highbay", "wallpack", "troffer", "disposal", "lift", "permit"] + list(extra or [])
    A = {k: Q[k] * R[k] for k in order}
    total = d["total"] if not (qty or rate or extra or sensors_in_total) else sum(A.values())
    lines = [f"# Proposal: Warehouse LED Lighting Retrofit", "", f"**{CONTRACTOR}**  ", prepared_for or f"Prepared for: {client}, attention {fm}  ", "Date: September 17, 2026", "",
             "## Scope", "", "Replace the warehouse high bays, loading dock wall packs and office troffers with LED fixtures, including removal and recycling of the old fixtures, "
             "lift rental and the city permit.", "", "## Pricing", "", "| Item | Qty | Unit price | Amount |", "|---|---|---|---|"]
    for k in order:
        lines.append(f"| {LABEL[k]} | {Q[k]} | {m(R[k])} | {m(A[k])} |")
    if sensors_in_total:
        lines += ["", f"**Total: {m(total)}**", "", "## Terms", "", "Price valid for 30 days. 40% deposit to schedule, balance on completion.",
                  "", f"Thank you for considering {CONTRACTOR}.", ""]
        return "\n".join(lines)
    lines += ["", f"**Total: {m(total)}**", "", "## Optional add-on (not included in the total)", "",
              f"Occupancy sensors, one per high bay: 26 x {m(R['sensor'])} = {m(26 * R['sensor'] if rate else d['sensors'])}.", "",
              "## Terms", "", "Price valid for 30 days. 40% deposit to schedule, balance on completion.", "", f"Thank you for considering {CONTRACTOR}.", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- per-trap mutants

def write_mutant(d: dict, trap: str, out: str) -> None:
    kw = {
        "highbay_count": {"qty": {"highbay": 22, "disposal": 42}},  # the last count in the file (22) taken; disposal follows it
        "lift": {"qty": {"lift": 2}},                              # the site walk's two lift days
        "disposal": {"qty": {"disposal": 26}},                     # disposal charged on the high bays only
        "sensors": {"qty": {"sensor": 26}, "extra": ["sensor"], "sensors_in_total": True},  # sensors a line in the total
        "poles": {"qty": {"pole": 5}, "extra": ["pole"]},          # the dropped pole lights priced
        "old_rates": {"rate": d["old"]},                           # every line from the 2025 column
        "old_proposal": {"prepared_for": "Prepared for: Ironwood Fabrication, 77 Mill Rd, Tacoma  "},  # template header kept
    }[trap]
    os.makedirs(out, exist_ok=True)
    write_text(os.path.join(out, "proposal.md"), proposal_text(d, **kw))


# Grader-blind mutant, kept out of MUTANTS: "sensors" (the 26 sensors priced as a line inside the total) still
# passes "optional sensors priced separately", which only looks for a sentence with "sensor" and the sensor amount,
# so it cannot tell an option from a line in the total; only "total" catches it. write_mutant(d, "sensors", out)
# still writes it.
MUTANTS = {k: write_mutant for k in TRAP_KEYS if k != "sensors"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    add_trap_args(ap)
    a = ap.parse_args()
    traps = parse_trap_args(a, TRAPS, MUTANTS, TRAP_KEYS)
    emit(a.seed, traps, a.out, a.mutant)
