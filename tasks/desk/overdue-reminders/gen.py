#!/usr/bin/env python3
"""overdue-reminders: an HVAC contractor's open-invoice export and the bookkeeper's rules to one reminder per overdue customer.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * the export's Days column is the invoice's age from its invoice date, not days past due; the guide counts from
    the due date as of September 30                                  (checks: <58-day customer> reminder figures; per-customer reminder facts)
  * two invoices have a blank due date; it is the invoice date plus the terms   (checks: <96-day customer> reminder figures; per-customer reminder facts)
  * Dale's email says three customers are over 60 days and get the credit hold paragraph, but one of them is 58 days
    past due by the ledger; only the other two get it  (checks: <75-day customer> credit hold paragraph; per-customer reminder facts)
  * one partially paid invoice: the balance is owed, not the original amount  (check: per-customer reminder facts)
  * two active payment-plan customers get the plan reminder (next installment amount and date, no invoice list, no
    credit hold) even though one has a 90-day invoice; a third customer's plan is completed and gets the standard reminder
                                                                    (check: per-customer reminder facts)
  * disputed invoices are left out entirely: one customer whose only past-due invoice is disputed gets no reminder,
    another gets one without the disputed invoice; not-yet-due and zero-balance invoices are left out too
                                                                    (checks: per-customer reminder facts; reminder files)
  * the export carries a three-line preamble, a BOM, CRLF endings and balances as "$1,234.50" text
                                                                    (check: per-customer reminder facts)
"""
from __future__ import annotations
import os, re, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

AS_OF = date(2026, 9, 30)
COMPANY = "Pemberton HVAC"
BOOKKEEPER = "Nadia Haddad"
OWNER = "Dale Pemberton"
TERMS = {"Net 15": 15, "Net 30": 30, "Net 45": 45}

def ci_glob(word: str) -> str:
    return "reminders/*" + "".join(f"[{c.upper()}{c.lower()}]" if c.isalpha() else c for c in word) + "*"

def build(seed: int) -> dict:
    r = rng(seed)
    pool = [c for c in COMPANIES if "&" not in c[0] and c[0] != COMPANY]
    while True:
        comps = pick(r, pool, 12)
        keys = [re.sub(r"[^a-z0-9]", "", c[0].split()[0].lower()) for c in comps]
        full = [re.sub(r"[^a-z0-9]", "", c[0].lower()) for c in comps]
        if len(set(keys)) == 12 and not any(k in f for i, k in enumerate(keys) for j, f in enumerate(full) if i != j):
            break
    inv_no = iter(r.sample(range(20310, 21990), 30))
    def inv(due=None, terms="Net 30", amount=None, balance=None, memo="", inv_date=None, show_due=True):
        t = TERMS[terms]
        if inv_date is None: inv_date = due - timedelta(days=t)
        if due is None: due = inv_date + timedelta(days=t)
        amt = amount if amount is not None else money(r, 380, 4200)
        bal = amt if balance is None else balance
        return dict(no=f"INV-{next(inv_no)}", date=inv_date, terms=terms, due=due, show_due=show_due, amount=amt, balance=bal, memo=memo,
                    days=(AS_OF - due).days)
    D = lambda m, d: date(2026, m, d)
    C = {}
    a1 = money(r, 1200, 2600)
    C["A"] = dict(kind="standard", invoices=[inv(D(9, 12), amount=a1, balance=round(a1 - money(r, 300, 900, cents=False), 2), memo="Partial pmt 9/2"),
                                             inv(D(9, 25), terms="Net 15")])
    C["B"] = dict(kind="standard", invoices=[inv(D(8, 20)), inv(D(10, 10), memo="")])
    C["C"] = dict(kind="standard", invoices=[inv(D(7, 17), terms="Net 45"), inv(D(8, 21))])
    C["D"] = dict(kind="standard", invoices=[inv(D(8, 3))])
    C["E"] = dict(kind="plan", invoices=[inv(D(7, 2)), inv(D(8, 15))], installment=float(r.choice([350, 400, 450, 500])), next_due=D(10, 15))
    C["F"] = dict(kind="plan", invoices=[inv(D(9, 10), terms="Net 15")], installment=float(r.choice([225, 250, 275])), next_due=D(10, 5))
    C["G"] = dict(kind="none", invoices=[inv(D(8, 25), memo="DISPUTED - billed for wrong unit, Dale reviewing")])
    C["H"] = dict(kind="standard", invoices=[inv(D(9, 15), terms="Net 15"), inv(D(8, 1), memo="Disputed (warranty part)")])
    C["I"] = dict(kind="none", invoices=[inv(D(10, 14))])
    C["J"] = dict(kind="standard", invoices=[inv(None, terms="Net 15", inv_date=D(6, 11), show_due=False)])
    C["K"] = dict(kind="standard", invoices=[inv(None, terms="Net 15", inv_date=D(8, 24), show_due=False)])
    C["L"] = dict(kind="none", invoices=[inv(D(8, 29), balance=0.0, memo="Paid 9/26 ck 4471")])
    for i, k in enumerate("ABCDEFGHIJKL"):
        C[k]["name"] = comps[i][0]; C[k]["key"] = keys[i]
    for k, c in C.items():
        c["past_due"] = [v for v in c["invoices"] if v["days"] > 0 and v["balance"] > 0 and "disput" not in v["memo"].lower()]
        c["excluded"] = [v for v in c["invoices"] if v not in c["past_due"]]
        c["total"] = round(sum(v["balance"] for v in c["past_due"]), 2)
        c["hold"] = c["kind"] == "standard" and any(v["days"] > 60 for v in c["past_due"])
        c["gets_file"] = bool(c["past_due"])
    assert C["D"]["past_due"][0]["days"] == 58 and C["J"]["past_due"][0]["days"] == 96 and not C["G"]["gets_file"]
    assert [k for k in C if C[k]["hold"]] == ["C", "J"]
    return dict(C=C)

def long(d: date) -> str: return d.strftime("%B %-d, %Y")

def letter(c: dict) -> str:
    out = [f"# Payment reminder - {c['name']}", "", f"{COMPANY}", f"Statement date: {long(AS_OF)}", "", f"Hello {c['name']} accounts payable team,", ""]
    if c["kind"] == "plan":
        out += [f"Thank you for keeping to the payment plan you arranged with us.",
                f"Your next installment of ${c['installment']:,.2f} is due on {long(c['next_due'])}.",
                "If anything changes on your side, please call our office before that date so we can help.", ""]
    else:
        out += [f"Our records show the following invoices past due as of {long(AS_OF)}:", "",
                "| Invoice | Balance due | Days past due |", "|---|---|---|"]
        for v in c["past_due"]:
            out.append(f"| {v['no']} | ${v['balance']:,.2f} | {v['days']} |")
        out += ["", f"Total past due: ${c['total']:,.2f}.", ""]
        if c["hold"]:
            late = [v["no"] for v in c["past_due"] if v["days"] > 60]
            out += [f"Because invoice {', '.join(late)} is more than 60 days past due, new service calls for your account are on credit hold (COD only) "
                    "until the past-due balance is paid.", ""]
        out += ["Please send payment or call our office to arrange it.", ""]
    out += ["Thank you,", "", f"{BOOKKEEPER}", f"Accounts Receivable, {COMPANY}", ""]
    return "\n".join(out)

def emit(seed: int) -> None:
    d = build(seed); C = d["C"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 3)
    rows = []
    for k, c in C.items():
        for v in c["invoices"]:
            rows.append([c["name"], v["no"], v["date"].strftime("%m/%d/%Y"), v["terms"], v["due"].strftime("%m/%d/%Y") if v["show_due"] else "",
                         money_str(v["amount"], 1), money_str(v["balance"], 1), (AS_OF - v["date"]).days, v["memo"]])
    r.shuffle(rows)
    rows.sort(key=lambda x: x[0])
    write_csv(os.path.join(ws, "open_invoices_2026-09-30.csv"),
              ["Customer", "Invoice #", "Invoice Date", "Terms", "Due Date", "Original Amount", "Balance", "Days", "Memo"], rows,
              preamble=[f"{COMPANY} - A/R Open Invoice Detail", "As of 09/30/2026", ""], bom=True, crlf=True)
    plans = [[C["A"]["name"], "02/01/2026", "$300.00", "Monthly", "", "$0.00", "Completed 06/01/2026"],
             [C["E"]["name"], "07/15/2026", f"${C['E']['installment']:,.2f}", "Monthly", C["E"]["next_due"].strftime("%m/%d/%Y"),
              f"${C['E']['total'] - C['E']['installment']:,.2f}", "Active"],
             [C["F"]["name"], "09/05/2026", f"${C['F']['installment']:,.2f}", "Monthly", C["F"]["next_due"].strftime("%m/%d/%Y"),
              f"${C['F']['total']:,.2f}", "Active"]]
    write_csv(os.path.join(ws, "payment_plans.csv"), ["Customer", "Plan Start", "Installment", "Frequency", "Next Installment Due", "Remaining", "Status"], plans)
    write_text(os.path.join(ws, "reminder_guidelines.md"),
        f"# Past-due reminders - how we do them\n\n_{BOOKKEEPER}, updated August 2026_\n\n"
        "Reminders go out once a month from the open invoice export. The statement date is the date the export was run.\n\n"
        "## Who gets one\n\n"
        "- Every customer with a balance past due on the statement date gets **one** reminder, however many invoices they have.\n"
        "- Days past due count from the invoice's due date. If the due date is blank in the export, it is the invoice date plus the terms.\n"
        "- Invoices that are not due yet, or that have a zero balance, are not part of the reminder.\n"
        "- Anything marked disputed in the memo is with Dale. Leave it out of the reminder completely and don't mention it.\n\n"
        "## What a standard reminder says\n\n"
        "- Each past-due invoice: invoice number, the balance still owed (not the original amount if they paid part of it), and how many days past due it is.\n"
        "- The total past due.\n"
        "- Tone: friendly up to 30 days, firmer after that. Always polite, never threatening.\n"
        "- If any invoice is more than 60 days past due, add the credit hold paragraph: new service calls for the account are on credit hold "
        "(COD only) until the past-due balance is paid.\n\n"
        "## Customers on a payment plan\n\n"
        "Customers with an active plan in payment_plans.csv get the plan reminder instead: thank them for keeping to the plan and give the amount and due date "
        "of their next installment. Don't list invoices and don't mention credit hold, even if old invoices are still open.\n\n"
        "## Files\n\n"
        "One file per customer, named after the customer, in a reminders folder.\n")
    write_email_thread(os.path.join(ws, "email_from_dale.txt"), [
        {"from": f"{OWNER} <dale@pembertonhvac.com>", "to": "office@pembertonhvac.com", "date": "Wed, 30 Sep 2026 16:42", "subject": "reminders this month",
         "body": (f"Nadia is out until the 12th so can you do the past-due reminders this month? The export is in the shared folder and her guidelines are with it.\n\n"
                  f"Heads up that {C['D']['name']}, {C['C']['name']} and {C['J']['name']} are all over 60 days now, so they get the credit hold paragraph. "
                  f"{C['G']['name']} is arguing their invoice with me, so leave that one alone.\n\nThanks,\nDale")}])

    R = os.path.join(sol, "reminders")
    notes = {"as_of": AS_OF.isoformat(), "customers": []}
    for k, c in C.items():
        if c["gets_file"]:
            write_text(os.path.join(R, f"{c['name'].replace(' ', '_')}.md"), letter(c))
        notes["customers"].append({
            "label": k, "name": c["name"], "key": c["key"], "kind": c["kind"], "gets_file": c["gets_file"], "hold": c["hold"],
            "total": c["total"], "past_due": [{"no": v["no"], "balance": v["balance"], "days": v["days"]} for v in c["past_due"]],
            "excluded": [v["no"] for v in c["excluded"]], "all_invoices": [v["no"] for v in c["invoices"]],
            "installment": c.get("installment"), "next_due": c["next_due"].isoformat() if c.get("next_due") else None})
    write_json(os.path.join(ref, "notes.json"), notes)
    Dk, Jk, Ck, Hk = C["D"], C["J"], C["C"], C["H"]
    write_task_yaml(HERE, {
        "id": "overdue-reminders", "track": "desk", "category": "drafting",
        "title": "Write this month's past-due reminders",
        "ask": "Nadia's out, so please write this month's past-due payment reminders from the open invoice export - one file per customer in a reminders folder. "
               "Her guidelines are in the folder, and Dale's email has a couple of notes.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the export's Days column is each invoice's age from its invoice date; {Dk['name']} shows 88 there but is 58 days past due from its due date (checks: {Dk['name']} reminder figures; per-customer reminder facts)",
            f"two invoices have a blank due date and Net 15 terms; {Jk['name']}'s is 96 days past due once the due date is worked out (checks: {Jk['name']} reminder figures; per-customer reminder facts)",
            f"Dale's email says {Dk['name']} is over 60 days and gets the credit hold paragraph; by the ledger it is 58 days past due, so only {Ck['name']} and {Jk['name']} get it (checks: {Ck['name']} credit hold paragraph; per-customer reminder facts)",
            "one invoice was partly paid; the reminder states the balance, not the original amount (check: per-customer reminder facts)",
            "two customers with active payment plans get the plan reminder (next installment amount and date, no invoice list, no credit hold) even though one has a 90-day invoice; a third customer's plan is marked completed and gets a standard reminder (check: per-customer reminder facts)",
            f"disputed invoices are left out entirely: {C['G']['name']} has nothing else past due and gets no reminder, {Hk['name']}'s reminder carries only its undisputed invoice; not-yet-due and zero-balance invoices are left out too (checks: reminder files; per-customer reminder facts)",
            "the export has a three-line preamble, a BOM, CRLF endings and balances written as '$1,234.50' text (check: per-customer reminder facts)",
        ],
        "checks": [
            {"type": "file_exists", "name": "reminder files", "path": "reminders/*.md"},
            {"type": "text_numbers_present", "name": f"{Dk['name']} reminder figures", "path": ci_glob(Dk["key"]),
             "numbers": [Dk["past_due"][0]["balance"], 58], "rel_tol": 0.0001},
            {"type": "text_numbers_present", "name": f"{Jk['name']} reminder figures", "path": ci_glob(Jk["key"]),
             "numbers": [Jk["past_due"][0]["balance"], 96], "rel_tol": 0.0001},
            {"type": "text_sentence_matches", "name": f"{Ck['name']} credit hold paragraph", "path": ci_glob(Ck["key"]),
             "all": [r"(credit hold|on hold|\bhold\b|\bc\.?o\.?d\b|cash on delivery)"],
             "none": [r"\b(not|no longer|never|won't|will not|isn't|aren't|without)\b"]},
            {"type": "custom", "name": "per-customer reminder facts", "module": "check.py"},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
