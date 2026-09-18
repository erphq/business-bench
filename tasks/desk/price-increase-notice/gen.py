#!/usr/bin/env python3
"""price-increase-notice: a florist's weekly standing-order price increase, drafted as one notice with a mailing note.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * Grace's first email says the increase takes effect October 1; two messages later it moves to Monday, November 2
                                                                         (check: effective date)
  * percentages are rounded to the nearest whole percent on the current price: truncating, or dividing by the new
    price, gives a different figure for the counter arrangement and the delivery fee  (checks: counter arrangement: new price and rounded percent; delivery fee: new price and rounded percent)
  * Grace's last email says the medium lobby arrangement goes to one price; the approved schedule she called final
    has another                                                          (check: lobby arrangement: new price and rounded percent)
  * the owner names three annual-contract customers from memory: one of them converted to month-to-month in June and
    another annual customer is missing; the customer list decides who is left off the mailing
                                                                         (check: mailing note names the annual-contract customers)
  * last year's notice sits in the folder with its old date and a LOYAL10 discount code; Grace says no code this year
                                                                         (check: no discount code)
  * the bud vase set has no new price because it is being discontinued  (check: bud vase sets discontinued)
"""
from __future__ import annotations
import math, os, sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

SHOP = "Ivy Lane Florist"
OWNER = "Grace Lindqvist"
MAILER = "Kim Tanaka"
EFFECTIVE = date(2026, 11, 2)

def pct(old: float, new: float) -> float:
    return (new - old) / old * 100

def r_half_up(x: float) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def good(old, new, need_trunc, need_base):
    p = pct(old, new); q = (new - old) / new * 100
    if abs(p - math.floor(p) - 0.5) < 0.15 or abs(q - math.floor(q) - 0.5) < 0.15:
        return False
    if need_trunc and r_half_up(p) == math.floor(p):
        return False
    if need_base and r_half_up(p) == r_half_up(q):
        return False
    return True

def choose(r, olds, deltas, need_trunc, need_base):
    combos = [(o, o + dl) for o in olds for dl in deltas if good(o, o + dl, need_trunc, need_base)]
    assert combos, (olds, deltas)
    return r.choice(combos)

def build(seed: int) -> dict:
    r = rng(seed)
    items = {}
    items["counter"] = dict(name="Small counter arrangement", key="counter", price=choose(r, [36.0, 38.0, 42.0, 44.0], [2.5, 3.0, 3.5], True, True))
    items["lobby"] = dict(name="Medium lobby arrangement", key="lobby", price=choose(r, [58.0, 62.0, 65.0], [4.0, 6.0, 7.0], False, True))
    items["statement"] = dict(name="Large statement arrangement", key="statement", price=choose(r, [115.0, 120.0, 135.0], [9.0, 11.0, 14.0], False, False))
    items["delivery"] = dict(name="Delivery fee (per visit)", key="delivery", price=choose(r, [7.5, 8.0, 8.5], [0.75, 0.95, 1.25], True, True))
    for it in items.values():
        o, n = it["price"]; it["old"], it["new"], it["pct"] = o, n, r_half_up(pct(o, n))
    lob = items["lobby"]
    wrong_lobby = lob["new"] - 2.0
    bud_old = float(r.choice([24, 26, 28]))
    comps = [c for c in COMPANIES if c[2] in ("food", "clinic", "legal", "insurance", "services", "fitness", "property", "design", "media", "software")
             and "&" not in c[0] and c[0] != SHOP]
    while True:
        chosen = pick(r, comps, 14)
        firsts = [c[0].split()[0].lower() for c in chosen]
        if len(set(firsts)) == 14 and not any(a != b and a in b for a in firsts for b in firsts):
            break
    custs = []
    plans = ["Small x2 + delivery", "Medium + delivery", "Large + Small + delivery", "Small + bud vases + delivery", "Medium x2 + delivery", "Large + delivery"]
    for i, (nm, dom, _) in enumerate(chosen):
        f, l = person(r)
        custs.append(dict(name=nm, contact=f"{f} {l}", email=email_for(r, f, l, dom), plan=r.choice(plans), contract="Month-to-month",
                          start=date(2025, r.randint(1, 12), 1), renewal=None, status="Active"))
    # annual contracts: 0, 1, 2 truly annual; 3 converted to month-to-month in June (the owner still thinks annual)
    renewals = [date(2027, 1, 31), date(2027, 3, 31), date(2026, 12, 31)]
    for i in range(3):
        custs[i]["contract"] = "Annual"; custs[i]["renewal"] = renewals[i]; custs[i]["start"] = date(renewals[i].year - 1, renewals[i].month, 1) if renewals[i].month != 12 else date(2026, 1, 1)
    custs[3]["contract"] = "Month-to-month (annual ended 06/30/2026)"
    custs[4]["status"] = "Cancelled 08/2026"
    return dict(items=items, wrong_lobby=wrong_lobby, bud_old=bud_old, custs=custs)

def money_s(x: float) -> str: return f"${x:,.2f}"

def emit(seed: int) -> None:
    d = build(seed); I = d["items"]; C = d["custs"]
    ws, ref, sol = task_dirs(HERE)
    order = ["counter", "lobby", "statement", "delivery"]
    rows = [[I[k]["name"], I[k]["old"], I[k]["new"], ""] for k in order[:3]]
    rows.append(["Bud vase set (5 vases)", d["bud_old"], "-", "Discontinued - last deliveries week of Oct 26"])
    rows.append([I["delivery"]["name"], I["delivery"]["old"], I["delivery"]["new"], "Applies to every standing order"])
    write_xlsx(os.path.join(ws, "new_price_schedule_2026.xlsx"), {"Schedule": {
        "merged_title": f"{SHOP} - weekly standing order prices (approved by finance 9/4/2026)",
        "header": ["Item", "Current weekly price", "New weekly price", "Notes"], "rows": rows,
        "number_formats": {"B": "$#,##0.00", "C": "$#,##0.00"}, "widths": {"A": 32, "B": 20, "C": 20, "D": 44}}}, creator="Finance")
    crow = []
    r = rng(seed + 8)
    for c in C:
        crow.append([c["name"], c["contact"], c["email"], c["plan"], c["contract"], c["start"].strftime("%m/%d/%Y"),
                     c["renewal"].strftime("%m/%d/%Y") if c["renewal"] else "", c["status"]])
    r.shuffle(crow)
    write_csv(os.path.join(ws, "standing_order_customers.csv"),
              ["Business", "Contact", "Email", "Standing order", "Contract", "Contract start", "Renewal date", "Status"], crow)
    a0, a1, a2, conv = C[0], C[1], C[2], C[3]
    write_email_thread(os.path.join(ws, "email_price_increase.txt"), [
        {"from": f"{OWNER} <grace@ivylaneflorist.com>", "to": "office@ivylaneflorist.com", "cc": MAILER, "date": "Tue, 8 Sep 2026 09:05",
         "subject": "price notice for standing orders",
         "body": ("Can you draft the price increase notice for our standing order customers? Finance approved the new schedule "
                  "(new_price_schedule_2026.xlsx in the folder) and that sheet is final, so use it for every number. The new prices take effect October 1.\n\n"
                  "For each item give the current weekly price, the new weekly price and the percent change, rounded to the nearest whole percent. "
                  "Say that we're discontinuing the bud vase sets. No discount code this year, we did that last time.\n\n"
                  f"Customers on an annual contract keep their current prices until their renewal date - that's {a0['name']}, {conv['name']} and {a2['name']}. "
                  f"They shouldn't get this letter, so add a short note at the bottom for {MAILER.split()[0]} saying who to leave off the mailing and when each of them renews.")},
        {"from": f"{MAILER} <kim@ivylaneflorist.com>", "to": f"{OWNER} <grace@ivylaneflorist.com>", "date": "Thu, 10 Sep 2026 14:31", "subject": "RE: price notice for standing orders",
         "body": "Our customer terms say 30 days' written notice for a price change, and I can't get the letters printed and out before October 2. Can we push the date?"},
        {"from": f"{OWNER} <grace@ivylaneflorist.com>", "to": f"{MAILER} <kim@ivylaneflorist.com>", "date": "Fri, 11 Sep 2026 08:12", "subject": "RE: price notice for standing orders",
         "body": (f"Good catch. Make it Monday, November 2 instead. Everything else stays the same - and remember the medium lobby goes to ${d['wrong_lobby']:.0f} a week.")}])
    write_text(os.path.join(ws, "price_notice_2025.md"),
        f"# A note about our prices\n\nDear valued customer,\n\nThank you for letting {SHOP} bring flowers to your business every week. "
        "After two years without a change, our weekly standing order prices will rise by about 5% effective September 1, 2025, because of higher "
        "wholesale flower and fuel costs.\n\nAs a thank-you for your loyalty, use code LOYAL10 for 10% off your first month at the new prices.\n\n"
        f"Warmly,\n{OWNER}\n{SHOP}\n")

    lines = [f"# Standing order price update from {SHOP}", "", "Dear customer,", "",
             f"Thank you for letting {SHOP} bring fresh flowers to your business every week. Rising wholesale flower costs mean we need to update "
             "our standing order prices.", "",
             f"The new prices take effect on Monday, November 2, 2026. Deliveries before then stay at your current prices.", "",
             "| Item | Current weekly price | New weekly price | Change |", "|---|---|---|---|"]
    for k in order:
        it = I[k]
        lines.append(f"| {it['name']} | {money_s(it['old'])} | {money_s(it['new'])} | {it['pct']}% |")
    lines += ["", "We are discontinuing the bud vase sets; the last bud vase deliveries will be the week of October 26.", "",
              "If you have questions about your standing order, just reply to this letter or call the shop.", "", "Warmly,", "", OWNER, SHOP, "", "---", "",
              f"Note for {MAILER.split()[0]} (not part of the letter): leave these annual-contract customers off the mailing; they keep current prices until renewal.", ""]
    for c in sorted(C[:3], key=lambda x: x["renewal"]):
        lines.append(f"- {c['name']} - renews {c['renewal'].strftime('%B %-d, %Y')}")
    lines.append("")
    write_text(os.path.join(sol, "notice.md"), "\n".join(lines))
    write_json(os.path.join(ref, "notes.json"), {
        "annual": [{"name": c["name"], "renewal": c["renewal"].isoformat()} for c in C[:3]], "converted": conv["name"], "effective": EFFECTIVE.isoformat(),
        "items": {k: {"old": I[k]["old"], "new": I[k]["new"], "pct": I[k]["pct"]} for k in order}, "wrong_lobby": d["wrong_lobby"]})

    def price_rx(x: float) -> str:
        whole = int(x); cents = round((x - whole) * 100)
        body = f"{whole}\\.{cents:02d}" if cents else f"{whole}(\\.00)?"
        return rf"(?<![\d.,]){body}(?!\d|,\d|\.\d)"
    def pct_rx(p: int) -> str:
        return rf"(?<![\d.]){p}(\.0+)?\s?(%|percent)"
    item_checks = []
    for k, label, word in [("counter", "counter arrangement", "counter"), ("lobby", "lobby arrangement", "lobby"),
                           ("statement", "statement arrangement", "statement"), ("delivery", "delivery fee", "delivery")]:
        it = I[k]
        spec = {"type": "text_sentence_matches", "name": f"{label}: new price and rounded percent", "path": "notice.md",
                "all": [rf"\b{word}\b", price_rx(it["new"]), pct_rx(it["pct"])]}
        if k == "lobby":
            spec["none"] = [price_rx(d["wrong_lobby"])]
        item_checks.append(spec)
    write_task_yaml(HERE, {
        "id": "price-increase-notice", "track": "desk", "category": "drafting",
        "title": "Draft the standing order price increase notice",
        "ask": "Please draft the price increase notice for our standing order customers and save it as notice.md. Grace's emails and the new price schedule are in the folder.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the first email says the new prices take effect October 1; the last one moves the date to Monday, November 2 (check: effective date)",
            f"percent changes round to the nearest whole percent on the current price; for the counter arrangement ({money_s(I['counter']['old'])} to {money_s(I['counter']['new'])}) and the delivery fee ({money_s(I['delivery']['old'])} to {money_s(I['delivery']['new'])}) truncating or dividing by the new price gives a different whole percent (checks: counter arrangement: new price and rounded percent; delivery fee: new price and rounded percent)",
            f"Grace's last email says the medium lobby arrangement goes to ${d['wrong_lobby']:.0f}; the approved schedule she called final says {money_s(I['lobby']['new'])} (check: lobby arrangement: new price and rounded percent)",
            f"Grace lists {conv['name']} among the annual-contract customers, but the customer list shows it went month-to-month in June, and she leaves out {a1['name']}, which is annual; the mailing note must name the three annual customers with renewal dates and not exclude {conv['name']} (check: mailing note names the annual-contract customers)",
            "last year's notice is in the folder with a September 2025 date and a LOYAL10 discount code; Grace says no code this year (check: no discount code)",
            "the bud vase set has no new price because it is being discontinued, so the notice must say so rather than price it (check: bud vase sets discontinued)",
        ],
        "checks": [
            {"type": "text_sentence_matches", "name": "effective date", "path": "notice.md",
             "all": [r"(effective|take effect|takes effect|start|starting|begin|beginning|from|as of|on and after)",
                     r"(november\s+2(nd)?\b|nov\.?\s+2(nd)?\b|\b11/0?2/(20)?26\b|\b2026-11-02\b|\b2(nd)?\s+(of\s+)?nov(ember)?\b|\bnov\.$)"],
             "none": [r"(october\s+1(st)?\b|oct\.?\s+1(st)?\b|\b10/0?1/(20)?26\b|\b2026-10-01\b)"]},
            *item_checks,
            {"type": "text_numbers_present", "name": "current prices stated", "path": "notice.md",
             "numbers": [I[k]["old"] for k in order], "rel_tol": 0.0005},
            {"type": "text_sentence_matches", "name": "bud vase sets discontinued", "path": "notice.md",
             "all": [r"bud\s*vase", r"(discontinu|no longer (be )?(offer|available|carry|provid|sell)|retir|phas(e|ing) out|last (deliver|week))"]},
            {"type": "text_not_contains", "name": "no discount code", "path": "notice.md", "phrases": ["LOYAL10"]},
            {"type": "custom", "name": "mailing note names the annual-contract customers", "module": "check.py"},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
