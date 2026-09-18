#!/usr/bin/env python3
"""sop-from-thread: an outdoor store's email thread about counter refunds to a printed step-by-step procedure.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * steps arrive out of order: the item inspection and the approval come in a later message but happen before the
    refund, and the emailed receipt comes after the refund but before logging        (check: steps in the right order)
  * the blue binder step is superseded by the Refunds Log sheet a week later         (checks: refunds logged in the sheet; steps in the right order)
  * the approval limit starts at one amount and the owner lowers it two messages later (check: approval threshold)
  * the store manager's first message gives a longer return window than the posted policy; the policy is what the
    counter follows, and it adds a store-credit window                               (checks: refund window; store credit window)
  * cash sales refund from the drawer only up to a limit; above it the bookkeeper mails a check (check: cash refunds)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

STORE = "Granite Peak Outfitters"

def build(seed: int) -> dict:
    r = rng(seed)
    old_limit, new_limit = r.choice([(250, 150), (300, 200), (200, 125)])
    cash_limit = r.choice([50, 75, 100])
    window, wrong_window, credit_window = r.choice([(30, 45, 60), (30, 60, 90), (21, 30, 45)])
    mgr, book, owner, hire = (f"{a} {b}" for a, b in people(r, 4))
    return dict(old_limit=old_limit, new_limit=new_limit, cash_limit=cash_limit, window=window, wrong_window=wrong_window,
                credit_window=credit_window, mgr=mgr, book=book, owner=owner, hire=hire)

def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    M, B, O, H = (d[k].split()[0] for k in ("mgr", "book", "owner", "hire"))
    dom = "granitepeak.com"
    em = lambda full: f"{full} <{full.split()[0].lower()}@{dom}>"
    write_email_thread(os.path.join(ws, "email_thread_refunds.txt"), [
        {"from": em(d["mgr"]), "to": em(d["hire"]), "date": "Tue, 1 Sep 2026 17:20", "subject": "how we do refunds",
         "body": (f"Hi {H}, here's how refunds work at the counter so you're not guessing on Saturday:\n\n"
                  "1. Look up the original sale in Lightspeed, by receipt number or the customer's phone number.\n"
                  "2. Refund it to the original payment method.\n"
                  "3. Fill in a refund slip and put it in the blue binder under the register.\n\n"
                  f"We take returns within {d['wrong_window']} days of purchase.\n\n{M}")},
        {"from": em(d["book"]), "to": f"{em(d['hire'])}, {em(d['mgr'])}", "date": "Wed, 2 Sep 2026 08:47", "subject": "RE: how we do refunds",
         "body": (f"Two things {M} left out. Before you refund anything, look the item over: tags on, not worn or used, and put a return tag on it "
                  "with the receipt number so it goes back to stock or into the damaged bin.\n\n"
                  f"And any refund over ${d['old_limit']} needs {O}'s OK before you process it. Text {O} and wait for the yes.\n\n{B}")},
        {"from": em(d["mgr"]), "to": f"{em(d['hire'])}, {em(d['book'])}", "date": "Thu, 3 Sep 2026 12:05", "subject": "RE: how we do refunds",
         "body": ("Also - once the refund has gone through, email the customer the refund receipt from Lightspeed, and do that before you file the slip. "
                  f"We keep getting calls asking whether the money went back.\n\n{M}")},
        {"from": em(d["book"]), "to": f"{em(d['hire'])}, {em(d['mgr'])}", "date": "Tue, 8 Sep 2026 09:30", "subject": "RE: how we do refunds",
         "body": ("Change starting this week: we're done with the blue binder, I'm taking it home to shred. Log every refund in the Refunds Log sheet "
                  "on the shared drive instead - date, receipt number, amount, reason, and who approved it if it needed approval.\n\n"
                  f"{B}")},
        {"from": em(d["owner"]), "to": f"{em(d['hire'])}, {em(d['mgr'])}, {em(d['book'])}", "date": "Wed, 9 Sep 2026 19:02", "subject": "RE: how we do refunds",
         "body": (f"I'm lowering the approval limit. Anything over ${d['new_limit']} needs my OK from now on, not ${d['old_limit']} - we've had too many big refunds on worn boots.\n\n"
                  f"And for cash sales: refund cash from the drawer up to ${d['cash_limit']}. Above ${d['cash_limit']} on a cash sale, don't open the drawer - take the customer's "
                  f"mailing address and {B} mails them a check within 5 business days.\n\n{O}")},
        {"from": em(d["hire"]), "to": em(d["mgr"]), "date": "Thu, 10 Sep 2026 10:14", "subject": "RE: how we do refunds",
         "body": f"Thanks all. Could someone write this up as one sheet I can keep at the register? I keep mixing up the order.\n\n{H}"}])
    write_pdf_document(os.path.join(ws, "return_policy_posted.pdf"), [
        ("title", f"{STORE}"), ("h", "Returns and Refunds"), ("hr", None),
        ("p", f"<b>Full refund</b> to your original payment method within <b>{d['window']} days</b> of purchase with proof of purchase (receipt or order lookup)."),
        ("spacer", 4),
        ("p", f"<b>Store credit</b> on a {STORE} gift card from day {d['window'] + 1} to day {d['credit_window']} after purchase."),
        ("spacer", 4),
        ("p", f"No returns after {d['credit_window']} days. Items marked Final Sale cannot be returned. Items must be unworn and unused with tags attached."),
        ("spacer", 12), ("small", "This notice is posted at every register. Updated August 2026.")], font="Helvetica", base_size=13)

    lim, cash, win, cw = d["new_limit"], d["cash_limit"], d["window"], d["credit_window"]
    proc = f"""# Counter refund procedure

{STORE} - keep at the register. Follows the posted return policy and the September 2026 changes.

## Before you start

- Refunds to the original payment method are allowed within {win} days of purchase.
- From day {win + 1} to day {cw} after purchase, give store credit on a gift card instead of a refund.
- No returns after {cw} days, and no returns on Final Sale items.

## Steps

1. **Look up the original sale** in Lightspeed by receipt number or the customer's phone number, and confirm the purchase date.
2. **Inspect the item.** Tags must be on and the item unworn and unused. Put a return tag on it with the receipt number so it goes back to stock or into the damaged bin.
3. **Get approval for refunds over ${lim}.** Text {O} and wait for a yes before you go on.
4. **Process the refund** to the original payment method. For a cash sale, refund cash from the drawer up to ${cash}; above ${cash}, do not open the drawer - take the customer's mailing address and {B} mails a check within 5 business days.
5. **Email the customer the refund receipt** from Lightspeed.
6. **Log the refund** in the Refunds Log sheet on the shared drive: date, receipt number, amount, reason, and who approved it if approval was needed.
"""
    write_text(os.path.join(sol, "procedure.md"), proc)
    write_json(os.path.join(ref, "notes.json"), d)
    write_task_yaml(HERE, {
        "id": "sop-from-thread", "track": "desk", "category": "drafting",
        "title": "Turn the refunds email thread into a counter procedure",
        "ask": f"{H} keeps mixing up how refunds work. Please turn the email thread into one written procedure we can print for the register and save it as procedure.md.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"steps arrive out of order: {B}'s inspection and approval steps come in the second message but happen before the refund, and {M}'s emailed receipt comes in the third but goes after the refund and before logging (check: steps in the right order)",
            f"the blue binder from the first message is replaced by the Refunds Log sheet on 8 September (checks: refunds logged in the sheet; steps in the right order)",
            f"the approval limit is ${d['old_limit']} in the second message and {O} lowers it to ${lim} in the fifth (check: approval threshold)",
            f"{M}'s first message says returns within {d['wrong_window']} days; the posted policy says a refund within {win} days and store credit to day {cw}, and the counter follows the posted policy (checks: refund window; store credit window)",
            f"cash sales refund from the drawer only up to ${cash}; above that {B} mails a check (check: cash refunds)",
        ],
        "checks": [
            {"type": "text_sentence_matches", "name": "approval threshold", "path": "procedure.md",
             "all": [rf"(?<![\d.,]){lim}(\.00)?(?!\d|,\d|\.\d)", r"(approv|\bok\b|okay|sign[- ]?off|permission|\byes\b)", rf"(\b{O}\b|owner)"],
             "none": [rf"(?<![\d.,]){d['old_limit']}(\.00)?(?!\d|,\d|\.\d)"]},
            {"type": "text_sentence_matches", "name": "refund window", "path": "procedure.md",
             "all": [rf"(?<![\d.,]){win}(?!\d|,\d|\.\d)", r"\bdays?\b", r"refund"], "none": [rf"(?<![\d.,]){d['wrong_window']}(?!\d|,\d|\.\d)"]},
            {"type": "text_sentence_matches", "name": "store credit window", "path": "procedure.md",
             "all": [r"(store credit|gift card)", rf"(?<![\d.,]){cw}(?!\d|,\d|\.\d)"]},
            {"type": "text_sentence_matches", "name": "cash refunds", "path": "procedure.md",
             "all": [r"\bcash\b", rf"(?<![\d.,]){cash}(\.00)?(?!\d|,\d|\.\d)", r"\b(check|cheque)\b"]},
            {"type": "text_sentence_matches", "name": "refunds logged in the sheet", "path": "procedure.md",
             "all": [r"(refunds? log|log sheet|shared drive|spreadsheet)"]},
            {"type": "custom", "name": "steps in the right order", "module": "check.py"},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
