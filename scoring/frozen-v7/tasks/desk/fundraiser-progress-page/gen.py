#!/usr/bin/env python3
"""fundraiser-progress-page: a junior rowing club's boat campaign as one progress page with totals and top donors.

    python gen.py [--seed N] [--naive DIR]

Business: a volunteer-run junior rowing club raising money for a new eight. Online gifts come from the giving
platform's export (all campaigns in one file, refunds as statuses, an anonymous tick box); the treasurer logs
checks and cash in a workbook with names written surname first.

Traps (each caught by a check, see task.yaml):
  * refunded gifts keep their amount with a Refunded status; one gift is partly refunded   (checks: total raised; page structure: top donors)
  * a check in the treasurer's log bounced                                                (check: total raised)
  * the export mixes the boat fund with the general fund and regatta entry fees           (checks: total raised; page structure: top donors)
  * donors who gave online and by check are one donor ('Okafor, James' in the log)       (check: page structure: top donors)
  * a donor who ticked anonymous online also gave a named check; the name stays off the page entirely
                                                                                           (checks: anonymous donors kept off; page structure: top donors)
  * goal percent and amount still to raise come from the treasurer's goal                 (checks: total raised; page structure: progress figures)
"""
from __future__ import annotations
import argparse
import html
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

GOAL = 48000_00
CAMPAIGN = "New eight for the juniors"
OTHER = ["General fund", "Spring regatta entry fees"]


def build(seed: int) -> dict:
    r = rng(seed)
    names = people(r, 120)
    donors = [{"first": f, "last": l, "email": email_for(r, f, l), "gifts": [], "anon": False} for f, l in names]
    d0 = date(2026, 6, 1)

    def gift(dn, cents, channel, status="Succeeded", campaign=CAMPAIGN, refunded=0, anon=False, note=""):
        g = {"donor": dn, "cents": cents, "channel": channel, "status": status, "campaign": campaign,
             "refunded": refunded, "anon": anon, "note": note, "date": d0 + timedelta(days=r.randint(0, 100))}
        dn["gifts"].append(g)
        return g

    pool = list(donors)
    r.shuffle(pool)
    top = pool[:5]
    rest = pool[5:]
    # the ranked five, built so each trap moves the list
    big = sorted([r.randint(40, 60) * 100_00, r.randint(30, 38) * 100_00, r.randint(24, 28) * 100_00,
                  r.randint(19, 22) * 100_00, r.randint(15, 17) * 100_00], reverse=True)
    t1, t2, t3, t4, t5 = top
    gift(t1, big[0], "online")
    split = r.randint(8, 12) * 100_00
    gift(t2, big[1] - split, "online")                    # combined donor: online plus a check
    gift(t2, split, "check")
    a_online = big[2] - r.randint(4, 6) * 100_00
    gift(t3, a_online, "online", anon=True)               # anonymous online, named check in the log
    gift(t3, big[2] - a_online, "check")
    t3["anon"] = True
    gift(t4, big[3] - 250_00, "online")
    gift(t4, 250_00, "online", status="Partially refunded", refunded=0)  # fixed below
    gift(t5, big[4], "check")
    # partial refund: t4's second gift was 400 with 150 refunded (net 250)
    t4["gifts"][1].update(cents=400_00, refunded=150_00)
    # decoys that would enter the top five under a naive reading
    ref = rest[0]
    gift(ref, big[2] + r.randint(5, 9) * 100_00, "online", status="Refunded")        # refunded in full
    gift(ref, 100_00, "online")
    gen = rest[1]
    gift(gen, big[1] + r.randint(1, 4) * 100_00, "online", campaign=OTHER[0])         # general fund, not the boat
    gift(gen, 50_00, "online")
    bounce = rest[2]
    gift(bounce, big[3] + r.randint(2, 6) * 100_00, "check", note="returned - NSF, do not count")
    anon2 = rest[3]
    gift(anon2, r.randint(3, 9) * 25_00, "online", anon=True)
    anon2["anon"] = True
    # the crowd: small boat-fund gifts, some other-campaign gifts, a couple of small refunds
    for dn in rest[4:80]:
        for _ in range(r.choice([1, 1, 1, 2])):
            ch = "online" if r.random() < 0.8 else r.choice(["check", "cash"])
            amt = r.choice([25_00, 36_00, 50_00, 50_00, 54_00, 75_00, 100_00, 100_00, 118_00, 150_00, 180_00, 200_00,
                            250_00, 500_00, 35_00, 60_00, 72_50, 26_25, 108_00])
            gift(dn, amt, ch, anon=(ch == "online" and r.random() < 0.05))
        if any(g["anon"] for g in dn["gifts"]):
            dn["anon"] = True
    for dn in rest[80:100]:
        gift(dn, r.choice([40_00, 50_00, 120_00, 180_00]), "online", campaign=r.choice(OTHER))
    for dn in r.sample(rest[4:80], 2):
        gift(dn, r.choice([50_00, 100_00]), "online", status="Refunded")
    for dn in donors:
        dn["net"] = sum(g["cents"] - g["refunded"] for g in dn["gifts"] if counts(g))
    givers = [dn for dn in donors if dn["net"] > 0]
    total = sum(dn["net"] for dn in givers)
    ranked = sorted(givers, key=lambda dn: -dn["net"])
    return {"donors": donors, "givers": givers, "ranked": ranked, "total": total, "top": ranked[:5],
            "decoys": {"refunded": ref, "general": gen, "bounced": bounce}, "anon2": anon2}


def counts(g: dict) -> bool:
    return g["campaign"] == CAMPAIGN and g["status"] != "Refunded" and "NSF" not in g["note"]


def acceptable(d: dict) -> bool:
    ranked = d["ranked"]
    nets = [dn["net"] for dn in ranked[:6]]
    if len(set(nets)) < 6 or nets[4] - nets[5] < 200_00:
        return False
    if sum(1 for dn in ranked[:5] if dn["anon"]) != 1:
        return False
    if d["total"] >= GOAL:
        return False
    pct10 = d["total"] / GOAL * 1000
    frac = pct10 - int(pct10)
    if abs(frac - 0.5) < 0.1 or round(pct10) % 10 == 0:
        return False
    # names unique, and no donor's full name inside another's
    full = [f"{dn['first']} {dn['last']}".lower() for dn in d["donors"]]
    if len(set(full)) != len(full):
        return False
    lasts = [dn["last"] for dn in d["donors"] if dn["anon"]]
    # an anonymous donor's surname must not be shared with anyone named on the page's top list
    shown = [dn for dn in ranked[:5] if not dn["anon"]]
    if any(dn["last"] in lasts or dn["first"] in [a["first"] for a in d["donors"] if a["anon"]] for dn in shown):
        return False
    return True


def usd(c: int) -> str:
    return f"${c / 100:,.2f}"


def page_html(d: dict) -> str:
    total, top = d["total"], d["top"]
    pct = total / GOAL * 100
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           "<title>New eight for the juniors - campaign progress</title>", "<style>",
           "body{font-family:'Helvetica Neue',Arial,sans-serif;margin:28px auto;max-width:680px;color:#14243b;padding:0 16px}",
           ".bar{background:#dfe6ef;height:22px;border-radius:11px;overflow:hidden}",
           f".fill{{background:#1f5aa6;height:100%;width:{pct:.1f}%}}",
           "table{border-collapse:collapse;width:100%}", "td{padding:6px 8px;border-bottom:1px solid #e3e8ee}",
           "td.n{text-align:right}", "</style>", "</head>", "<body>",
           "<h1>New eight for the juniors</h1>",
           f"<p><strong>{usd(total)} raised</strong> of our {usd(GOAL)} goal - <strong>{pct:.1f}%</strong> of the way there.</p>",
           '<div class="bar"><div class="fill"></div></div>',
           f"<p>{usd(GOAL - total)} still to raise. {len(d['givers'])} donors so far.</p>",
           "<h2>Top donors</h2>", "<table><tbody>"]
    for i, dn in enumerate(top, 1):
        nm = "Anonymous" if dn["anon"] else f"{dn['first']} {dn['last']}"
        out.append(f"<tr><td>{i}</td><td>{html.escape(nm)}</td><td class=\"n\">{usd(dn['net'])}</td></tr>")
    out += ["</tbody></table>", "<p>Thank you to everyone who has given. Gifts are counted once they clear; refunded "
            "gifts are not included.</p>", "</body>", "</html>", ""]
    return "\n".join(out)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    donors = d["donors"]
    r = rng(seed + 19)
    online, offline = [], []
    for dn in donors:
        for g in dn["gifts"]:
            if g["channel"] == "online":
                online.append(g)
            else:
                offline.append(g)
    online.sort(key=lambda g: (g["date"], g["donor"]["last"]))
    offline.sort(key=lambda g: (g["date"], g["donor"]["last"]))
    for i, g in enumerate(online):
        g["id"] = f"DN-{58000 + i * 3}"
    if naive_dir:
        write_naive(d, online, offline, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    write_csv(os.path.join(ws, "givewell_platform_export_2026-09-12.csv"),
              ["Donation ID", "Date", "Donor first name", "Donor last name", "Email", "Campaign", "Amount", "Status",
               "Refunded amount", "Hide my name"],
              [[g["id"], g["date"].strftime("%m/%d/%Y"), g["donor"]["first"], g["donor"]["last"], g["donor"]["email"],
                g["campaign"], f"${g['cents'] / 100:,.2f}", g["status"], f"${g['refunded'] / 100:,.2f}" if g["refunded"] else "",
                "Yes" if g["anon"] else ""] for g in online], bom=True, crlf=True)
    write_xlsx(os.path.join(ws, "treasurer_checks_and_cash_log.xlsx"), {"Boat fund deposits": {
        "merged_title": "Boat fund - checks and cash (deposited by treasurer)",
        "header": ["Date received", "Donor", "Method", "Amount", "Note"],
        "rows": [[g["date"], f"{g['donor']['last']}, {g['donor']['first']}", "Check #" + str(1000 + i * 7) if g["channel"] == "check" else "Cash",
                  g["cents"] / 100, g["note"]] for i, g in enumerate(offline)],
        "widths": {"A": 14, "B": 24, "C": 14, "E": 30}}}, creator="Treasurer")
    write_text(os.path.join(ws, "note_from_treasurer.txt"),
               "From: Dana Whitlock (treasurer)\nTo: you\nDate: Sat, 12 Sep 2026 10:30\nSubject: progress page for the boat campaign\n\n"
               "The board wants a progress page for the new eight we can put on the club website and the screen in the "
               "boathouse. One HTML file please, it gets uploaded as is, and no scripts - the site builder strips them.\n\n"
               "Our goal is $48,000. The page should show how much we have raised, what percent of the goal that is "
               "(one decimal is fine), how much is still to raise, how many donors have given, and a Top donors list "
               "with the five biggest donors and what each has given in total.\n\n"
               "What counts:\n"
               f"- Only gifts to the \"{CAMPAIGN}\" campaign. The platform export has everything - general fund, regatta "
               "entry fees - in the same file.\n"
               "- Refunded gifts do not count. If only part of a gift was refunded, count what we kept.\n"
               "- My log has the checks and cash. One check bounced; it is marked in the note column.\n"
               "- A donor is a person, not a gift. Plenty of people gave online and also handed me a check, so add "
               "those together. My log writes names surname first.\n\n"
               "Privacy: if someone ticked Hide my name on any gift, their name never goes on the page, even if they "
               "also gave by check. In the top donors list they show as Anonymous.\n\n"
               "Dana\n")
    top = d["top"]
    anon_all = [dn for dn in donors if dn["anon"]]
    write_json(os.path.join(ref, "expected.json"), {
        "top": [{"name": None if dn["anon"] else f"{dn['first']} {dn['last']}", "total": dn["net"] / 100,
                 "variants": [] if dn["anon"] else [f"{dn['first']} {dn['last']}", f"{dn['last']}, {dn['first']}"]}
                for dn in top],
        "total": d["total"] / 100, "goal": GOAL / 100, "percent": round(d["total"] / GOAL * 100, 1),
        "remaining": (GOAL - d["total"]) / 100, "donors": len(d["givers"]),
        "decoys": [f"{dn['first']} {dn['last']}" for dn in d["decoys"].values()],
        "anonymous_names": [f"{dn['first']} {dn['last']}" for dn in anon_all],
    })
    write_text(os.path.join(sol, "index.html"), page_html(d))
    t_anon = next(dn for dn in top if dn["anon"])
    comb = next(dn for dn in top if len([g for g in dn["gifts"] if counts(g)]) > 1 and not dn["anon"]
                and len({g["channel"] for g in dn["gifts"]}) > 1)
    dec = d["decoys"]
    traps = [
        f"refunded gifts keep their amount and only say Refunded - including a large one from "
        f"{dec['refunded']['first']} {dec['refunded']['last']} that would rank in the top five - and one gift is "
        "Partially refunded with the refunded amount in its own column (checks: total raised and progress; page "
        "structure: top donors)",
        f"a check in the treasurer's log from {dec['bounced']['last']}, {dec['bounced']['first']} bounced (note: "
        "returned - NSF) and is big enough to reach the top five (checks: total raised and progress; page structure: top donors)",
        f"the export carries general fund and regatta entry gifts, among them a gift from {dec['general']['first']} "
        f"{dec['general']['last']} that would be the second-largest (checks: total raised and progress; page structure: top donors)",
        f"{comb['first']} {comb['last']} gave online and by check ('{comb['last']}, {comb['first']}' in the log); only "
        "the two together make the top five in the right place (check: page structure: top donors)",
        f"{t_anon['first']} {t_anon['last']} ticked Hide my name online and also gave a check under their name; the "
        "combined total ranks in the top five as Anonymous and the name appears nowhere (checks: anonymous donors kept "
        "off; page structure: top donors)",
        "percent of goal, amount still to raise and the donor count (people, not gifts) all follow from the treasurer's "
        "goal and rules (checks: total raised and progress; page structure: progress figures)",
    ]
    write_task_yaml(HERE, {
        "id": "fundraiser-progress-page", "track": "desk", "category": "tooling",
        "title": "Boat campaign progress page with top donors",
        "ask": "Could you build the progress page for our boat campaign from the donation export and the treasurer's "
               "check log? Dana's note has the rules. Save it as index.html.\n",
        "followup": None, "timeout_s": 1200,
        "traps": traps,
        "checks": [
            {"type": "file_exists", "name": "index.html exists", "path": "index.html"},
            {"type": "text_contains_all", "name": "named top donors and the anonymous slot", "path": "index.html",
             "phrases": [f"{dn['first']} {dn['last']}" for dn in top if not dn["anon"]] + ["anonymous"]},
            {"type": "text_not_contains", "name": "anonymous donors kept off", "path": "index.html",
             "phrases": [f"{dn['first']} {dn['last']}" for dn in anon_all] + [f"{dn['last']}, {dn['first']}" for dn in anon_all]
                        + [dn["email"] for dn in anon_all]},
            {"type": "text_numbers_present", "name": "total raised and progress", "path": "index.html",
             "numbers": [d["total"] / 100, (GOAL - d["total"]) / 100, round(d["total"] / GOAL * 100, 1)], "rel_tol": 0.0000001},
            {"type": "custom", "name": "page structure", "module": "check.py"},
        ],
    })
    print(f"seed={seed} total={d['total'] / 100:.2f} pct={d['total'] / GOAL * 100:.1f} donors={len(d['givers'])} "
          f"top={[(dn['first'] + ' ' + dn['last'], dn['net'] / 100, dn['anon']) for dn in top]}")


def write_naive(d: dict, online: list, offline: list, out: str) -> None:
    """The obvious reading: every online row's Amount plus every log row, names as written, top five by single gift,
    the Hide my name flag applied to that online gift only, goal percent from that total."""
    os.makedirs(out, exist_ok=True)
    gifts = []
    for g in online:
        gifts.append(("Anonymous" if g["anon"] else f"{g['donor']['first']} {g['donor']['last']}", g["cents"]))
    for g in offline:
        gifts.append((f"{g['donor']['last']}, {g['donor']['first']}", g["cents"]))
    total = sum(c for _, c in gifts)
    top = sorted(gifts, key=lambda x: -x[1])[:5]
    parts = ["<html><body><h1>Boat campaign</h1>",
             f"<p>Raised {usd(total)} of {usd(GOAL)} ({total / GOAL * 100:.1f}%). {usd(GOAL - total)} to go. {len(gifts)} donors.</p>",
             "<h2>Top donors</h2><ol>"]
    parts += [f"<li>{html.escape(n)} {usd(c)}</li>" for n, c in top]
    parts.append("</ol></body></html>\n")
    write_text(os.path.join(out, "index.html"), "\n".join(parts))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(2000):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
