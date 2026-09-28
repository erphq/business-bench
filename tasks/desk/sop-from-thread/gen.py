#!/usr/bin/env python3
"""sop-from-thread: an outdoor store's email thread about counter refunds to a printed step-by-step procedure.

    python gen.py [--seed N]
    python gen.py --list-traps
    python gen.py --traps-off binder,limit --out DIR   # same draw, those pitfalls removed, same answer
    python gen.py --mutant order --out DIR             # a deliverable that falls for one trap

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
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from bizgen.traps import TrapSet, add_trap_args, parse_trap_args, variant_dirs, active_trap_text  # noqa: E402

# Every trap in task.yaml, keyed. Switchable traps are removed at render time only, so build() and its
# random draws are identical in every variant and the correct answer never moves.
TRAPS = TrapSet(
    switchable={
        "binder": "the first message files slips in a blue binder, replaced by the Refunds Log sheet a week later "
                  "(off: the thread uses the Refunds Log sheet throughout)",
        "limit": "the approval limit is lowered two messages after it is given (off: the lower limit given once)",
        "window": "the manager's first message gives a longer return window than the posted policy (off: that "
                  "sentence dropped; the policy's refund and store-credit windows still have to be used)",
    },
    fixed={
        "order": "steps arrive out of order across the messages and must be put in the order they happen",
        "cash": "cash refunds come from the drawer only up to a limit; above it the bookkeeper mails a check",
    },
)
# task.yaml trap sentences, in order, and the trap each one describes
TRAP_KEYS = ["order", "binder", "limit", "window", "cash"]

STORE = "Granite Peak Outfitters"

def build(seed: int) -> dict:
    r = rng(seed)
    old_limit, new_limit = r.choice([(250, 150), (300, 200), (200, 125)])
    cash_limit = r.choice([50, 75, 100])
    window, wrong_window, credit_window = r.choice([(30, 45, 60), (30, 60, 90), (21, 30, 45)])
    mgr, book, owner, hire = (f"{a} {b}" for a, b in people(r, 4))
    return dict(old_limit=old_limit, new_limit=new_limit, cash_limit=cash_limit, window=window, wrong_window=wrong_window,
                credit_window=credit_window, mgr=mgr, book=book, owner=owner, hire=hire)

def thread(d: dict, traps: TrapSet) -> list[dict]:
    """The email thread, with the switched-off pitfalls removed. Every message stays, so 'the fifth message' still
    means the same one."""
    M, B, O, H = (d[k].split()[0] for k in ("mgr", "book", "owner", "hire"))
    dom = "granitepeak.com"
    em = lambda full: f"{full} <{full.split()[0].lower()}@{dom}>"
    binder, limit = traps.on("binder"), traps.on("limit")
    first_limit = d["old_limit"] if limit else d["new_limit"]
    return [
        {"from": em(d["mgr"]), "to": em(d["hire"]), "date": "Tue, 1 Sep 2026 17:20", "subject": "how we do refunds",
         "body": (f"Hi {H}, here's how refunds work at the counter so you're not guessing on Saturday:\n\n"
                  "1. Look up the original sale in Lightspeed, by receipt number or the customer's phone number.\n"
                  "2. Refund it to the original payment method.\n"
                  + ("3. Fill in a refund slip and put it in the blue binder under the register.\n\n" if binder else
                     "3. Log the refund in the Refunds Log sheet on the shared drive.\n\n")
                  + (f"We take returns within {d['wrong_window']} days of purchase.\n\n" if traps.on("window") else "")
                  + M)},
        {"from": em(d["book"]), "to": f"{em(d['hire'])}, {em(d['mgr'])}", "date": "Wed, 2 Sep 2026 08:47", "subject": "RE: how we do refunds",
         "body": (f"Two things {M} left out. Before you refund anything, look the item over: tags on, not worn or used, and put a return tag on it "
                  "with the receipt number so it goes back to stock or into the damaged bin.\n\n"
                  f"And any refund over ${first_limit} needs {O}'s OK before you process it. Text {O} and wait for the yes.\n\n{B}")},
        {"from": em(d["mgr"]), "to": f"{em(d['hire'])}, {em(d['book'])}", "date": "Thu, 3 Sep 2026 12:05", "subject": "RE: how we do refunds",
         "body": ("Also - once the refund has gone through, email the customer the refund receipt from Lightspeed, and do that before you "
                  + ("file the slip. " if binder else "log it. ") +
                  f"We keep getting calls asking whether the money went back.\n\n{M}")},
        {"from": em(d["book"]), "to": f"{em(d['hire'])}, {em(d['mgr'])}", "date": "Tue, 8 Sep 2026 09:30", "subject": "RE: how we do refunds",
         "body": (("Change starting this week: we're done with the blue binder, I'm taking it home to shred. Log every refund in the Refunds Log sheet "
                   "on the shared drive instead - date, receipt number, amount, reason, and who approved it if it needed approval.\n\n" if binder else
                   "For the Refunds Log sheet on the shared drive: log every refund with the date, receipt number, amount, reason, and who "
                   "approved it if it needed approval.\n\n")
                  + B)},
        {"from": em(d["owner"]), "to": f"{em(d['hire'])}, {em(d['mgr'])}, {em(d['book'])}", "date": "Wed, 9 Sep 2026 19:02", "subject": "RE: how we do refunds",
         "body": ((f"I'm lowering the approval limit. Anything over ${d['new_limit']} needs my OK from now on, not ${d['old_limit']} - we've had too many big refunds on worn boots.\n\n"
                   f"And for cash sales: " if limit else "For cash sales: ")
                  + f"refund cash from the drawer up to ${d['cash_limit']}. Above ${d['cash_limit']} on a cash sale, don't open the drawer - take the customer's "
                  f"mailing address and {B} mails them a check within 5 business days.\n\n{O}")},
        {"from": em(d["hire"]), "to": em(d["mgr"]), "date": "Thu, 10 Sep 2026 10:14", "subject": "RE: how we do refunds",
         "body": f"Thanks all. Could someone write this up as one sheet I can keep at the register? I keep mixing up the order.\n\n{H}"}]


def procedure_text(d: dict, trap: str | None = None) -> str:
    """The register procedure; with `trap`, the one an agent that fell for that trap would write."""
    B, O = (d[k].split()[0] for k in ("book", "owner"))
    lim, cash, win, cw = d["new_limit"], d["cash_limit"], d["window"], d["credit_window"]
    if trap == "limit":           # the first limit in the thread kept
        lim = d["old_limit"]
    before = [f"- Refunds to the original payment method are allowed within {win} days of purchase.",
              f"- From day {win + 1} to day {cw} after purchase, give store credit on a gift card instead of a refund.",
              f"- No returns after {cw} days, and no returns on Final Sale items."]
    if trap == "window":          # the manager's window taken over the posted policy, which has no store credit in it
        ww = d["wrong_window"]
        before = [f"- Refunds to the original payment method are allowed within {ww} days of purchase.",
                  f"- No returns after {ww} days, and no returns on Final Sale items."]
    cash_text = (f"For a cash sale, refund cash from the drawer up to ${cash}; above ${cash}, do not open the drawer - take the customer's "
                 f"mailing address and {B} mails a check within 5 business days.")
    if trap == "cash":            # the drawer limit and the mailed check left out
        cash_text = "For a cash sale, refund cash from the drawer."
    steps = {
        "lookup": "**Look up the original sale** in Lightspeed by receipt number or the customer's phone number, and confirm the purchase date.",
        "inspect": "**Inspect the item.** Tags must be on and the item unworn and unused. Put a return tag on it with the receipt number so it goes back to stock or into the damaged bin.",
        "approve": f"**Get approval for refunds over ${lim}.** Text {O} and wait for a yes before you go on.",
        "refund": f"**Process the refund** to the original payment method. {cash_text}",
        "receipt": "**Email the customer the refund receipt** from Lightspeed.",
        "log": "**Log the refund** in the Refunds Log sheet on the shared drive: date, receipt number, amount, reason, and who approved it if approval was needed.",
    }
    order = ["lookup", "inspect", "approve", "refund", "receipt", "log"]
    if trap == "order":           # steps written in the order the messages brought them
        order = ["lookup", "refund", "log", "inspect", "approve", "receipt"]
    if trap == "binder":          # the first message's blue binder kept
        steps["log"] = "**Fill in a refund slip** and put it in the blue binder under the register."
    body = "\n".join(f"{i}. {steps[k]}" for i, k in enumerate(order, 1))
    nl = "\n"
    return f"""# Counter refund procedure

{STORE} - keep at the register. Follows the posted return policy and the September 2026 changes.

## Before you start

{nl.join(before)}

## Steps

{body}
"""


def emit(seed: int, traps: TrapSet = TRAPS, out: str | None = None, mutant: str | None = None) -> None:
    d = build(seed)
    if mutant:
        write_mutant(d, mutant, out)
        return
    here = out or HERE
    ws, ref, sol = task_dirs(HERE) if out is None else variant_dirs(out)
    if out is not None:  # the custom grader module travels with the task
        import shutil
        shutil.copyfile(os.path.join(HERE, "check.py"), os.path.join(out, "check.py"))
    M, B, O, H = (d[k].split()[0] for k in ("mgr", "book", "owner", "hire"))
    write_email_thread(os.path.join(ws, "email_thread_refunds.txt"), thread(d, traps))
    write_pdf_document(os.path.join(ws, "return_policy_posted.pdf"), [
        ("title", f"{STORE}"), ("h", "Returns and Refunds"), ("hr", None),
        ("p", f"<b>Full refund</b> to your original payment method within <b>{d['window']} days</b> of purchase with proof of purchase (receipt or order lookup)."),
        ("spacer", 4),
        ("p", f"<b>Store credit</b> on a {STORE} gift card from day {d['window'] + 1} to day {d['credit_window']} after purchase."),
        ("spacer", 4),
        ("p", f"No returns after {d['credit_window']} days. Items marked Final Sale cannot be returned. Items must be unworn and unused with tags attached."),
        ("spacer", 12), ("small", "This notice is posted at every register. Updated August 2026.")], font="Helvetica", base_size=13)

    lim, cash, win, cw = d["new_limit"], d["cash_limit"], d["window"], d["credit_window"]
    write_text(os.path.join(sol, "procedure.md"), procedure_text(d))
    write_json(os.path.join(ref, "notes.json"), d)
    spec = {
        "id": "sop-from-thread", "track": "desk", "category": "drafting",
        "title": "Turn the refunds email thread into a counter procedure",
        "ask": f"{H} keeps mixing up how refunds work. Please turn the email thread into one written procedure we can print for the register and save it as procedure.md.\n",
        "followup": None, "timeout_s": 1200,
        "traps": active_trap_text([
            f"steps arrive out of order: {B}'s inspection and approval steps come in the second message but happen before the refund, and {M}'s emailed receipt comes in the third but goes after the refund and before logging (check: steps in the right order)",
            f"the blue binder from the first message is replaced by the Refunds Log sheet on 8 September (checks: refunds logged in the sheet; steps in the right order)",
            f"the approval limit is ${d['old_limit']} in the second message and {O} lowers it to ${lim} in the fifth (check: approval threshold)",
            f"{M}'s first message says returns within {d['wrong_window']} days; the posted policy says a refund within {win} days and store credit to day {cw}, and the counter follows the posted policy (checks: refund window; store credit window)",
            f"cash sales refund from the drawer only up to ${cash}; above that {B} mails a check (check: cash refunds)",
        ], TRAP_KEYS, traps),
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
    }
    if not traps.canonical:
        # A variant: same draw, same checks and reference, fewer pitfalls.
        spec["variant"] = {"of": "sop-from-thread", "draw": seed, "traps_off": sorted(traps.off)}
    write_task_yaml(here, spec)


# --------------------------------------------------------------------------- per-trap mutants

def write_mutant(d: dict, trap: str, out: str) -> None:
    """procedure.md from an agent that is right except that it falls for `trap`."""
    if trap not in TRAP_KEYS:
        raise KeyError(trap)
    os.makedirs(out, exist_ok=True)
    write_text(os.path.join(out, "procedure.md"), procedure_text(d, trap))


MUTANTS = {k: write_mutant for k in TRAP_KEYS}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    add_trap_args(ap)
    a = ap.parse_args()
    traps = parse_trap_args(a, TRAPS, MUTANTS, TRAP_KEYS)
    emit(a.seed, traps, a.out, a.mutant)
