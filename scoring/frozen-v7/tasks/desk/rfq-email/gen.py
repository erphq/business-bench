#!/usr/bin/env python3
"""rfq-email: a bench manufacturer's parts spec sheet, the job ticket, an engineering note and the purchasing lead's
email become the request for quotation sent to metal and parts suppliers.

    python gen.py [--seed N]

Business: a fabricator of rolling benches for commercial greenhouses. A grower ordered a batch of 4 x 8 ft rolling
benches; purchasing needs quotes on the bought-in parts before the build.

Traps (each caught by a check, see task.yaml):
  * the spec sheet's per-bench quantities must be multiplied by the job ticket's bench count; the sheet also carries a
    pre-filled build-quantity column left over from an earlier 30-bench job       (check: line quantities, stock kit, dates)
  * the workbook keeps a superseded Rev A tab with fewer corner brackets and shorter cross members  (check: line quantities, stock kit, dates)
  * Rev B lists the roller pipe as 16 ga; engineering's note says 16 ga bent in the load test and it must be quoted
    at 14 ga                                                                        (check: roller pipe wall)
  * the fastener kits come from stock and are left off the request                   (check: line quantities, stock kit, dates)
  * the job ticket's ship date is December 1; the purchasing email needs the parts on the dock by November 13 and
    quotes back by October 2                                                         (check: line quantities, stock kit, dates)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

COMPANY = "Tern Point Greenhouse Systems"
DOMAIN = "ternpointgreenhouse.com"
QUOTE_DUE = date(2026, 10, 2)
DOCK_BY = date(2026, 11, 13)
SHIP = date(2026, 12, 1)
OLD_JOB = 30

# part no, description, material/spec (Rev B as printed), finish, qty per bench, buy/stock, rev A qty
PARTS = [
    ("TP-EXT-1530-96", "Aluminum T-slot extrusion 1.5 x 3.0 in, cut to 96 in", "6063-T5 aluminum", "Clear anodized", 4, "Buy", 4),
    ("TP-EXT-1515-45", "Aluminum T-slot extrusion 1.5 x 1.5 in, cut to 45 in", "6063-T5 aluminum", "Clear anodized", 6, "Buy", 6),
    ("TP-BRK-90G", "Corner gusset bracket, 4-hole", "11 ga steel", "Hot-dip galvanized", 12, "Buy", 10),
    ("TP-RLR-1315", "Roller pipe 1.315 in OD x 102 in", "16 ga steel tube", "Galvanized", 2, "Buy", 2),
    ("TP-EXM-4896", "Expanded metal bench top 48 x 96 in", "3/4 in #9 flattened, carbon steel", "Galvanized", 1, "Buy", 1),
    ("TP-FST-516K", "Fastener kit: 5/16-18 T-bolts and flange nuts", "Zinc-plated steel", "-", 1, "Stock", 1),
    ("TP-CAP-1515", "End cap for 1.5 x 1.5 in extrusion", "Black polypropylene", "-", 8, "Buy", 8),
    ("TP-HND-CRK", "Crank handle assembly", "Cast aluminum", "Black powder coat", 1, "Buy", 1),
]


def build(seed: int) -> dict:
    r = rng(seed * 17 + 3)
    benches = r.choice([36, 42, 44])
    ppl, firsts = [], set()
    while len(ppl) < 4:
        f, l = person(r)
        if f not in firsts:
            firsts.add(f); ppl.append((f, l))
    P = {k: {"first": f, "last": l, "full": f"{f} {l}"} for k, (f, l) in zip(["purchasing", "engineer", "sales", "planner"], ppl)}
    lines = []
    for no, desc, spec, fin, per, src, rev_a in PARTS:
        q = per * benches
        lines.append(dict(no=no, desc=desc, spec=spec, finish=fin, per=per, src=src, rev_a=rev_a, qty=q, old=per * OLD_JOB))
    # every quoted quantity must differ from the stale column, the per-bench figure and Rev A's figure
    for l in lines:
        assert l["qty"] not in (l["old"], l["per"])
        assert l["rev_a"] == l["per"] or l["rev_a"] * benches != l["qty"]
    dock_no = r.randint(1200, 4800)
    return dict(P=P, benches=benches, lines=lines, dock=f"{dock_no} Industrial Parkway", dock_no=dock_no, city="Salem", st="OR", zip="97301",
                job=f"HG-{r.randint(2600, 2699)}", customer="Hollis Growers")


def emit(seed: int) -> None:
    d = build(seed)
    P = d["P"]
    ws, ref, sol = task_dirs(HERE)
    # ---- spec workbook
    rev_b = [[i + 1, l["no"], l["desc"], l["spec"], l["finish"], l["per"], l["src"], l["old"] if l["src"] == "Buy" else "",
              "Rev A: 94 in" if l["no"] == "TP-EXT-1515-45" else ""] for i, l in enumerate(d["lines"])]
    rev_a = [[i + 1, (l["no"].replace("-45", "-94") if l["no"] == "TP-EXT-1515-45" else l["no"]),
              (l["desc"].replace("45 in", "44 in") if l["no"] == "TP-EXT-1515-45" else l["desc"]), l["spec"], l["finish"], l["rev_a"], l["src"]]
             for i, l in enumerate(d["lines"])]
    write_xlsx(os.path.join(ws, "RB-48_rolling_bench_spec_sheet.xlsx"), {
        "Rev B": {"merged_title": "RB-48 Rolling Bench (4 x 8 ft) - Bill of parts", "preamble": [["Rev B, released 2026-06-18", "", "", "", "", "", "", "", "Drawn: " + P['engineer']['first']], []],
                  "header": ["Line", "Part No.", "Description", "Material / Spec", "Finish", "Qty / bench", "Source", f"Build qty ({OLD_JOB} benches - Riverside Farms)", "Notes"],
                  "rows": rev_b, "widths": {"B": 18, "C": 48, "D": 32, "E": 18, "H": 22}},
        "Rev A (superseded)": {"merged_title": "RB-48 Rolling Bench - Bill of parts - REV A - SUPERSEDED", "preamble": [["Rev A, 2025-11-02"]],
                               "header": ["Line", "Part No.", "Description", "Material / Spec", "Finish", "Qty / bench", "Source"], "rows": rev_a,
                               "widths": {"B": 18, "C": 48, "D": 32}},
    }, creator="Engineering")

    # ---- job ticket PDF
    write_pdf_document(os.path.join(ws, f"job_ticket_{d['job']}.pdf"), [
        ("title", f"Job Ticket {d['job']}"),
        ("kv", [("Customer", f"{d['customer']}, Woodburn OR"), ("Sales rep", P["sales"]["full"]), ("Opened", "September 8, 2026"),
                ("Model", "RB-48 Rolling Bench, 4 x 8 ft, standard height"), ("Quantity", f"{d['benches']} benches"),
                ("Ship date to customer", SHIP.strftime("%B %-d, %Y")), ("Freight", "Our truck, two loads")]),
        ("spacer", 8),
        ("h", "Production notes"),
        ("p", "Standard RB-48 build per current revision. Customer-supplied bench labels to be fitted before shipping. "
              f"Production planner: {P['planner']['full']}."),
    ], font="Helvetica")

    # ---- engineering note
    write_text(os.path.join(ws, "note_from_engineering.txt"),
        f"From {P['engineer']['full']} (engineering), Sept 11\n\n"
        "Heads up for the Hollis RFQ. Rev B of the RB-48 sheet has the roller pipe wrong: it says 16 ga, but 16 ga bent in the "
        "load test with wet flats on the bench. The roller pipe has to be 14 ga wall (0.083 in), same 1.315 in OD and 102 in length, galvanized. "
        "Rev C will fix the sheet but don't hold the RFQ for it. Everything else on Rev B is correct. Ignore the Rev A tab, that's "
        "the old design.\n\n" + P["engineer"]["first"] + "\n")

    # ---- purchasing email
    write_email_thread(os.path.join(ws, "email_from_purchasing.txt"), [
        {"from": f"{P['purchasing']['full']} <{P['purchasing']['first'].lower()}@{DOMAIN}>", "to": f"purchasing-assist@{DOMAIN}",
         "date": "Mon, 14 Sep 2026 08:31", "subject": f"RFQ for the {d['customer']} benches",
         "body": (f"Can you put together the RFQ email for the {d['customer']} job ({d['job']})? I'll send it to our usual three suppliers.\n\n"
                  "- Quote everything we buy for the RB-48 at the job quantity. The fastener kits come out of our own stock, so leave them off.\n"
                  "- Ask for unit price, extended price, lead time and freight to our dock.\n"
                  f"- Quotes back to me by Friday, October 2.\n"
                  f"- The truck leaves for {d['customer']} on the ship date on the ticket, and we need a few weeks to build, so parts have to be on our dock "
                  f"at {d['dock']}, {d['city']}, {d['st']} {d['zip']} no later than Friday, November 13.\n\n"
                  f"Thanks,\n{P['purchasing']['full']}\nPurchasing Lead, {COMPANY}")},
    ])

    buy = [l for l in d["lines"] if l["src"] == "Buy"]
    facts = {"benches": d["benches"], "quote_due": QUOTE_DUE.isoformat(), "dock_by": DOCK_BY.isoformat(), "ship": SHIP.isoformat(),
             "stock_part": "TP-FST-516K", "lines": [{"no": l["no"], "qty": l["qty"], "old": l["old"], "per": l["per"]} for l in buy]}
    write_json(os.path.join(ref, "facts.json"), facts)
    spec_fix = lambda l: "14 ga steel tube (0.083 in wall)" if l["no"] == "TP-RLR-1315" else l["spec"]
    rows = "\n".join(f"| {i + 1} | {l['no']} | {l['desc']} | {spec_fix(l)} | {l['finish']} | {l['qty']} |" for i, l in enumerate(buy))
    rfq = (f"Subject: Request for quotation - RB-48 bench parts, {d['job']}\n\n"
           "Hello,\n\n"
           f"{COMPANY} requests your quotation for the parts below for a build of {d['benches']} RB-48 rolling benches.\n\n"
           "| Line | Part No. | Description | Material / Spec | Finish | Quantity |\n|---|---|---|---|---|---|\n"
           f"{rows}\n\n"
           "Please note the roller pipe (TP-RLR-1315) is 14 ga wall, 0.083 in, 1.315 in OD x 102 in, galvanized.\n\n"
           "For each line please quote the unit price, the extended price, your lead time, and freight to our dock.\n\n"
           f"- Quotes due: Friday, October 2, 2026, to {P['purchasing']['full']} ({P['purchasing']['first'].lower()}@{DOMAIN}).\n"
           f"- Delivery: all parts delivered to our dock at {d['dock']}, {d['city']}, {d['st']} {d['zip']} no later than Friday, November 13, 2026.\n\n"
           "Thank you, and please let us know if you have any questions about the specifications.\n\n"
           f"{P['purchasing']['full']}\nPurchasing Lead, {COMPANY}\n")
    write_text(os.path.join(sol, "rfq.md"), rfq)

    write_task_yaml(HERE, {
        "id": "rfq-email", "track": "desk", "category": "drafting",
        "title": "Request for quotation for the rolling bench parts",
        "ask": (f"{P['purchasing']['first']} needs the RFQ email for the {d['customer']} bench parts so it can go out to our suppliers. "
                "Everything you need is in the folder. Save the email as rfq.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the sheet gives quantities per bench and the job ticket orders {d['benches']} benches; the sheet also carries a pre-filled build-quantity column from an earlier {OLD_JOB}-bench job (check: line quantities, stock kit, dates)",
            "the workbook keeps a superseded Rev A tab with 10 corner brackets per bench instead of 12 and a 44 in cross member (check: line quantities, stock kit, dates)",
            "Rev B lists the roller pipe as 16 ga steel tube; engineering's note says it must be quoted at 14 ga (0.083 in wall) (check: roller pipe wall)",
            "the fastener kits come from stock and must be left off the request (check: line quantities, stock kit, dates)",
            f"the job ticket's ship date is {SHIP.strftime('%B %-d')}; the email wants quotes back by {QUOTE_DUE.strftime('%B %-d')} and parts on the dock by {DOCK_BY.strftime('%B %-d')} (check: line quantities, stock kit, dates)",
        ],
        "checks": [
            {"type": "file_exists", "name": "rfq.md exists", "path": "rfq.md"},
            {"type": "custom", "name": "line quantities, stock kit, dates", "module": "check.py"},
            {"type": "text_sentence_matches", "name": "roller pipe wall", "path": "rfq.md",
             "all": [r"(roller|1\.315|RLR)", r"(\b14\s*-?\s*(ga|gauge|gage)\b|0?\.083)"], "none": [r"\b16\s*-?\s*(ga|gauge|gage)\b"]},
            {"type": "text_matches_all", "name": "delivery address", "path": "rfq.md", "patterns": [rf"\b{d['dock_no']}\s+Industrial\s+(Parkway|Pkwy\b)"]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
