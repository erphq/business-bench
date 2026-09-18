#!/usr/bin/env python3
"""faq-from-tickets: two months of helpdesk tickets for a coffee subscription become a five-question FAQ.

    python gen.py [--seed N]

Business: a small roaster that sells coffee subscriptions. The owner wants the five questions customers ask
most, answered the way the current policy says, for the website.

Traps (each caught by a check, see task.yaml):
  * the same question is asked a dozen ways and the tags are inconsistent or blank; topics come from reading the
    messages                                                              (check: top five questions in order)
  * customers write in again ("any update?", "still waiting") and those repeat tickets carry no topic words;
    counted per ticket, cancellations jump above the order-change deadline and Canada shipping pushes free
    shipping out of the top five; counted once per customer (the owner's rule) they do not
                                                                          (check: top five questions in order)
  * policy changed on 1 August: pause limit, damaged-bag window, change deadline, the cancellation minimum and the
    free-shipping threshold; July replies, one agent's August replies and the old saved replies file all carry the
    old answers                                                           (checks: one per policy answer; withdrawn minimum absent)
"""
from __future__ import annotations
import os, sys
from datetime import date, datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

COMPANY = "Nightjar Coffee Roasters"

# topic -> (distinct customers, extra follow-up tickets)
PLAN = [("pause", 34, 3), ("damaged", 28, 2), ("deadline", 22, 2), ("cancel", 17, 8), ("freeship", 13, 1),
        ("canada", 9, 11), ("grind", 7, 0), ("gift", 6, 1), ("decaf", 4, 0)]
TOP5 = ["pause", "damaged", "deadline", "cancel", "freeship"]

ASK = {
    "pause": ["I'm going to be traveling for {n} weeks in {month}. Can I put my subscription on hold while I'm away?",
              "How long can I pause my coffee subscription? We have a new baby and are drowning in beans.",
              "Is there a way to stop deliveries for a bit without cancelling? Moving house next month.",
              "Can I pause for {n} weeks? I still have two unopened bags.",
              "Hi - going to be away most of {month}. What's the longest I can pause for?",
              "hey can i hold my shipments for a couple months, have too much coffee lol",
              "Please pause my subscription until I get back from a work trip ({n} weeks).",
              "What happens if I pause? Does it restart on its own or do I have to remember?",
              "I want a break from deliveries over the summer, not cancel. Possible?",
              "Can you put order #{order} and the next ones on hold for {n} weeks?"],
    "damaged": ["My bag of {coffee} arrived with the valve torn and the beans taste stale. What can you do?",
                "The box was crushed and one bag split open all over the mailbox. Order #{order}.",
                "This month's {coffee} tastes flat, roast date on the bag is almost two months ago?",
                "Bag arrived ripped. Can I get a replacement or my money back?",
                "Order #{order} showed up soaking wet, bag is ruined.",
                "The coffee I got is not what I ordered and it's stale. How do refunds work?",
                "Beans arrived broken and dusty, the seal was open. Not happy.",
                "How long do I have to report a damaged delivery? Mine came {n} days ago and I was away.",
                "The {coffee} bag burst in transit, coffee everywhere.",
                "Received a bag that was already opened?? Want a refund please."],
    "deadline": ["What's the last day I can change my next bag before it roasts?",
                 "I tried to swap my {coffee} for the {coffee2} but it said too late. When is the cutoff?",
                 "How late in the week can I update my shipping address for the next order?",
                 "When do I need to make changes to my upcoming delivery?",
                 "By when do I have to switch coffees for next week's box?",
                 "Missed the window to change my order again. What's the deadline exactly?",
                 "Is there a cutoff for editing the next shipment? Want to add a second bag.",
                 "If I change my coffee on {weekday}, does it apply to this week's roast?"],
    "cancel": ["How do I cancel my subscription?",
               "I'd like to cancel please, moving abroad.",
               "Can I cancel after just one shipment or is there a commitment?",
               "Please cancel my subscription effective immediately.",
               "I can't find where to cancel in my account.",
               "Is there a fee to cancel? I only signed up last month.",
               "Want to stop my subscription for good. What do I do?"],
    "freeship": ["Why was I charged shipping on my one-off order of {amt}?",
                 "How much do I have to spend to get free shipping?",
                 "Do subscriptions ship free or just big orders?",
                 "Shipping fee on a {amt} order seems steep - is there a free shipping minimum?",
                 "Is shipping free if I add a mug to my order?",
                 "What's your free shipping threshold these days?"],
    "canada": ["Do you ship to Canada? I'm in {ca_city}.",
               "How much is shipping to Canada?",
               "Can I send a subscription to my sister in {ca_city}?",
               "Do you deliver internationally? Specifically Canada.",
               "Is there duty on orders shipped to Canada?"],
    "grind": ["Which grind should I pick for an AeroPress?",
              "Do you sell whole bean or only ground?",
              "What grind size is best for a French press?",
              "Is your espresso grind fine enough for a home machine?"],
    "gift": ["Do you have gift subscriptions? Want to send 3 months to my dad.",
             "Can I buy a subscription as a gift and choose the start date?",
             "Gift card or gift subscription options?"],
    "decaf": ["Do you have a decaf option for subscriptions?",
              "Is your decaf Swiss Water process?"],
}
FOLLOWUP = ["Following up on my message from last week - I haven't heard back.",
            "Any update on this?",
            "Hi, still waiting on a reply to my earlier email.",
            "Sending this again in case it got lost.",
            "Hello? Second time asking.",
            "Just checking whether anyone saw my last ticket."]
SUBJ = {"pause": ["Pause subscription", "Going away", "hold deliveries", "Question about pausing", "vacation"],
        "damaged": ["Damaged bag", "Order problem", "stale coffee", "Bag arrived torn", "Issue with my delivery"],
        "deadline": ["Changing my next order", "Too late to swap?", "cutoff", "Update next shipment", "Question"],
        "cancel": ["Cancel", "Cancel subscription", "cancellation", "Stop subscription"],
        "freeship": ["Shipping charge", "Free shipping?", "shipping cost", "Question about shipping"],
        "canada": ["Shipping to Canada", "International shipping", "Canada", "Question about shipping"],
        "grind": ["Grind question", "Whole bean?", "Which grind"],
        "gift": ["Gift subscription", "Gifts"], "decaf": ["Decaf", "decaf?"]}
TAGS = {"pause": ["subscription", "pause", "", "account"], "damaged": ["quality", "refund", "damaged", "", "shipping"],
        "deadline": ["subscription", "order-change", "", "account"], "cancel": ["churn", "cancel", "subscription", ""],
        "freeship": ["shipping", "billing", ""], "canada": ["shipping", "international", "shipping"],
        "grind": ["product", ""], "gift": ["gift", "product"], "decaf": ["product", ""]}
OLD_REPLY = {
    "pause": "You can pause for up to 8 weeks - just reply with your dates and we'll set it up for you.",
    "damaged": "So sorry! If you let us know within 14 days of delivery we'll send a replacement or add store credit to your account.",
    "deadline": "Changes need to be in by Wednesday 5 pm Pacific to make that week's roast.",
    "cancel": "Subscriptions have a minimum of three shipments; after that you can cancel from your account page.",
    "freeship": "Orders over $35 ship free within the US.",
    "canada": "We ship to Canada for a flat $12.",
    "grind": "AeroPress: medium-fine. French press: coarse. Whole bean is always available.",
    "gift": "Gift subscriptions come in 3, 6 and 12 months.",
    "decaf": "Yes, our decaf is a Swiss Water process Colombian.",
}
NEW_REPLY = {
    "pause": "You can pause any subscription for up to 12 weeks from Account > Subscriptions > Pause, and it restarts on its own.",
    "damaged": "Sorry about that! Send us a photo within 30 days of delivery and we'll send a free replacement or refund you, your choice.",
    "deadline": "Changes to your next shipment need to be made by Thursday at 11:59 pm Pacific; we roast and ship on Monday.",
    "cancel": "You can cancel any time from Account > Subscriptions. No minimum and no fee.",
    "freeship": "US orders of $45 or more ship free, and subscriptions always ship free.",
    "canada": "We ship to Canada for a flat $14 per order; duties are included.",
    "grind": "AeroPress: medium-fine. French press: coarse. Whole bean is always available.",
    "gift": "Gift subscriptions come in 3, 6 and 12 months and you pick the start date.",
    "decaf": "Yes, our decaf is a Swiss Water process Colombian.",
}
COFFEES = ["Ethiopia Guji", "Night Owl Blend", "Colombia Huila", "Kenya Nyeri", "Morning Chorus", "Guatemala Antigua"]
CA_CITIES = ["Vancouver", "Toronto", "Calgary", "Montreal", "Victoria"]


def build(seed: int) -> dict:
    r = rng(seed * 1000 + 202)
    agents_new = ["Maya", "Luis"]
    stale_agent = "Tyler"
    tickets = []
    used_emails = set()

    def new_customer():
        while True:
            f, l = person(r)
            e = email_for(r, f, l)
            if e not in used_emails:
                used_emails.add(e)
                return f, l, e

    customers_by_topic = {}
    for topic, n_cust, n_follow in PLAN:
        custs = [new_customer() for _ in range(n_cust)]
        customers_by_topic[topic] = custs
        for i, (f, l, e) in enumerate(custs):
            created = datetime(2026, 7, 1, 8, 0) + timedelta(minutes=r.randint(0, 60 * 24 * 58))
            text = r.choice(ASK[topic]).format(n=r.choice([3, 5, 6, 10]), month=r.choice(["September", "October"]),
                                                order=r.randint(40100, 48900), coffee=r.choice(COFFEES),
                                                coffee2=r.choice(COFFEES), weekday=r.choice(["Wednesday", "Friday"]),
                                                amt=f"${r.randint(22, 44)}.00", ca_city=r.choice(CA_CITIES))
            text = f"Hi,\n\n{text}\n\nThanks,\n{f}"
            tickets.append({"created": created, "email": e, "name": f"{f} {l}", "subject": r.choice(SUBJ[topic]),
                            "body": text, "topic": topic, "followup": False, "tags": r.choice(TAGS[topic])})
        # follow-ups: from customers of this topic, no topic words in the body
        for k in range(n_follow):
            f, l, e = custs[k % max(1, min(len(custs), 4 if topic in ("cancel", "canada") else len(custs)))]
            first = next(t for t in tickets if t["email"] == e and not t["followup"])
            created = min(first["created"] + timedelta(hours=r.randint(20, 140)), datetime(2026, 8, 31, 17, r.randint(0, 59)))
            email = e.upper() if r.random() < 0.4 else (e.capitalize() if r.random() < 0.5 else e)
            tickets.append({"created": created, "email": email, "name": f"{f} {l}", "subject": "Re: " + first["subject"],
                            "body": f"{r.choice(FOLLOWUP)}\n\n{f}", "topic": topic, "followup": True, "tags": ""})
    tickets.sort(key=lambda t: t["created"])
    for i, t in enumerate(tickets):
        t["id"] = 20417 + i
        if t["followup"]:
            t["agent"] = r.choice(agents_new)
            t["reply"] = "Thanks for following up - see my earlier reply above." if r.random() < 0.6 else ""
            t["status"] = "Closed" if t["reply"] else "Open"
            continue
        if t["created"] < datetime(2026, 8, 1):
            t["agent"] = r.choice(agents_new + [stale_agent])
            t["reply"] = OLD_REPLY[t["topic"]]
        else:
            t["agent"] = r.choice(agents_new + [stale_agent, stale_agent])
            t["reply"] = OLD_REPLY[t["topic"]] if t["agent"] == stale_agent else NEW_REPLY[t["topic"]]
        t["status"] = "Closed" if r.random() < 0.9 else "Pending"
    counts_customer = {topic: len({t["email"].strip().lower() for t in tickets if t["topic"] == topic}) for topic, _, _ in PLAN}
    counts_ticket = {topic: sum(1 for t in tickets if t["topic"] == topic) for topic, _, _ in PLAN}
    by_cust = sorted(counts_customer, key=lambda k: -counts_customer[k])
    by_tick = sorted(counts_ticket, key=lambda k: -counts_ticket[k])
    assert by_cust[:5] == TOP5, (by_cust, counts_customer)
    assert set(by_tick[:5]) != set(TOP5) and by_tick[:5] != TOP5, counts_ticket
    return {"tickets": tickets, "counts_customer": counts_customer, "counts_ticket": counts_ticket, "by_tick": by_tick}


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    rows = [[t["id"], t["created"].strftime("%Y-%m-%d %H:%M"), t["name"], t["email"], t["subject"], t["body"], t["tags"],
             t["status"], t["agent"], t["reply"]] for t in d["tickets"]]
    write_csv(os.path.join(ws, "helpdesk_tickets_2026-07-01_to_2026-08-31.csv"),
              ["Ticket ID", "Created", "Requester", "Requester email", "Subject", "Description", "Tags", "Status", "Assignee", "Latest public reply"],
              rows, bom=True)

    write_text(os.path.join(ws, "subscription_policies.md"), f"""# {COMPANY} - Customer policies

Effective 1 August 2026. Replaces the March 2026 policies. Support replies and saved replies written before
this date may quote the old terms.

## Subscriptions
- **Pausing.** Any subscription can be paused for up to 12 weeks from Account > Subscriptions > Pause. It
  restarts automatically on the date you pick. Longer breaks: cancel and resubscribe.
- **Changes to the next shipment** (coffee, bag size, grind, address) must be made by Thursday at 11:59 pm
  Pacific. We roast on Monday and ship the same day. Changes after the cutoff apply to the following shipment.
- **Cancelling.** Cancel any time from Account > Subscriptions. There is no minimum number of shipments and no
  cancellation fee. A shipment that has already been roasted will still arrive.

## Shipping
- Subscriptions always ship free within the US.
- One-off US orders of $45 or more ship free; below $45 shipping is a flat $6.95.
- Canada: flat $14 per order, duties included. We do not ship anywhere else.

## Damaged, wrong or stale coffee
- Email a photo within 30 days of delivery. We send a free replacement or a refund to the original payment
  method, whichever the customer prefers.

## Products
- Every coffee is available whole bean or ground for drip, pour-over, AeroPress, French press or espresso.
- Decaf: Swiss Water process Colombia, available in subscriptions.
- Gift subscriptions: 3, 6 or 12 months, prepaid, start date chosen by the buyer.
""")

    write_text(os.path.join(ws, "saved_replies_2026-03.txt"), f"""SAVED REPLIES (helpdesk macros) - last edited March 2026

[Pause]
{OLD_REPLY['pause']}

[Damaged / stale]
{OLD_REPLY['damaged']}

[Change next order]
{OLD_REPLY['deadline']}

[Cancel]
{OLD_REPLY['cancel']}

[Free shipping]
{OLD_REPLY['freeship']}

[Canada]
{OLD_REPLY['canada']}

[Grind]
{OLD_REPLY['grind']}
""")

    write_text(os.path.join(ws, "note_from_dana.txt"), """Website FAQ

We keep answering the same things by email. I want an FAQ page with the five questions customers ask us most,
most-asked first. Just the five, don't pad it out.

How to count: go by the July and August tickets. Count each customer once per question - people email two or
three times about the same thing when we're slow ("any update?") and that shouldn't push a question up the list.

Answers have to follow the policy doc that took effect 1 August. Do not copy what the team replied in the
tickets, some of those replies (and the old saved replies) are out of date.

Dana
""")

    # reference solution
    faq = f"""# Frequently asked questions

## How long can I pause my subscription?
You can pause any subscription for up to 12 weeks from Account > Subscriptions > Pause. It restarts automatically on the date you choose. If you need a longer break, cancel and resubscribe when you are ready.

## My coffee arrived damaged or stale. What can I do?
Email us a photo within 30 days of delivery and we will send a free replacement or a refund to your original payment method, whichever you prefer.

## When is the deadline to change my next shipment?
Changes to your next shipment (coffee, bag size, grind or address) must be made by Thursday at 11:59 pm Pacific. We roast and ship on Monday; changes made after the cutoff apply to the following shipment.

## How do I cancel my subscription?
You can cancel any time from Account > Subscriptions. There is no minimum number of shipments and no cancellation fee. A shipment that has already been roasted will still arrive.

## Do you offer free shipping?
Subscriptions always ship free within the US. One-off US orders of $45 or more ship free; orders under $45 pay a flat $6.95.
"""
    write_text(os.path.join(sol, "faq.md"), faq)
    write_json(os.path.join(ref, "topics.json"), {"top5_in_order": TOP5, "counts_per_customer": d["counts_customer"],
                                                   "counts_per_ticket": d["counts_ticket"],
                                                   "not_in_faq": [t for t, _, _ in PLAN if t not in TOP5]})

    write_task_yaml(HERE, {
        "id": "faq-from-tickets", "track": "desk", "category": "drafting",
        "title": "Website FAQ from the summer support tickets",
        "ask": "Can you turn our July and August support tickets into an FAQ for the website? Dana's note says what she wants. Save it as faq.md.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "each question is asked eight or ten different ways and the Tags column is inconsistent (a quarter blank, 'shipping' on Canada, free-shipping and damaged tickets alike), so topics come from reading the messages (check: top five questions in order)",
            f"repeat tickets ('any update?', 'sending this again') carry no topic words and some use the email in a different case; counted per ticket the order is {', '.join(d['by_tick'][:5])}, which lifts Canada shipping into the five and cancellations above the change deadline; counted once per customer, as Dana's note says, it is {', '.join(TOP5)} (check: top five questions in order)",
            "Dana wants exactly five questions; grind, gift, decaf and Canada questions must not be padded in (check: top five questions in order)",
            "the pause limit rose from 8 to 12 weeks on 1 August; July replies, Tyler's August replies and the saved replies file still say 8 (check: pause answer uses the current limit)",
            "the damaged-coffee window is 30 days with a refund option, not 14 days with store credit (check: damaged coffee answer uses the current window)",
            "the change deadline moved from Wednesday 5 pm to Thursday 11:59 pm Pacific (check: change deadline answer)",
            "the three-shipment minimum was withdrawn; cancel any time, no fee (checks: cancel answer; withdrawn minimum absent)",
            "free shipping on one-off orders starts at $45, not $35 (check: free shipping answer uses the current threshold)",
        ],
        "checks": [
            {"type": "file_exists", "name": "faq.md exists", "path": "faq.md"},
            {"type": "custom", "name": "top five questions in order", "module": "check.py"},
            {"type": "text_sentence_matches", "name": "pause answer uses the current limit", "path": "faq.md",
             "all": [r"(\bpaus|on hold|\bhold\b)", r"(\b12\b|\btwelve\b)[\s-]*weeks?"], "none": [r"(\b8\b|\beight\b)[\s-]*weeks?"]},
            {"type": "text_sentence_matches", "name": "damaged coffee answer uses the current window", "path": "faq.md",
             "all": [r"(\b30\b|\bthirty\b)[\s-]*days?", r"(refund|replace)"], "none": [r"(\b14\b|\bfourteen\b)[\s-]*days?", r"store credit"]},
            {"type": "text_sentence_matches", "name": "change deadline answer", "path": "faq.md",
             "all": [r"\bthursday", r"(11:59|\bmidnight\b)"], "none": [r"\bwednesday"]},
            {"type": "text_sentence_matches", "name": "cancel answer", "path": "faq.md",
             "all": [r"\bcancel", r"(any ?time|at any point|whenever you (like|want|choose))"], "none": [r"\bminimum of\b", r"\bat least (3|three)\b", r"\bafter (3|three)\b"]},
            {"type": "text_sentence_matches", "name": "free shipping answer uses the current threshold", "path": "faq.md",
             "all": [r"\$\s?45\b", r"(\bfree\b|no shipping (charge|fee))"], "none": [r"\$\s?35\b"]},
            {"type": "text_not_contains", "name": "withdrawn minimum absent", "path": "faq.md",
             "phrases": ["minimum of three", "minimum of 3", "three shipments", "3 shipments"]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
