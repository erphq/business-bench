#!/usr/bin/env python3
"""contract-renewal-summary: a hotel group's managed Wi-Fi services agreement, its go-live certificate, two signed
amendments, an unsigned draft amendment and the vendor's renewal email become a renewal summary memo for the owner.

    python gen.py [--seed N]

Business: a group of small coastal inns. The owner is thinking of putting guest Wi-Fi out to bid and wants to know when
the network services contract ends, the last day to give notice, what it costs per year now, and what happens if
nobody acts.

Traps (each caught by a check, see task.yaml):
  * the initial term runs 36 months from the Service Commencement Date on the go-live certificate (April 1, 2024), not
    from the agreement's Effective Date (March 15, 2024), so it ends March 31, 2027   (check: term, notice and the vendor's figures)
  * Amendment 2 lengthens the non-renewal notice from 90 to 120 days, so notice is due by December 1, 2026
                                                                                        (check: term, notice and the vendor's figures)
  * the current annual value is the original schedule plus Amendment 1's added property plus Amendment 2's upgrade;
    the account manager's email quotes the original schedule                           (check: current annual value)
  * Amendment 3 is an unsigned draft (managed TV service and a 24-month extension) that changes nothing
                                                                                        (checks: current annual value; term, notice and the vendor's figures)
  * the account manager's email gives a March 15 renewal date and a December 15 notice deadline
                                                                                        (check: term, notice and the vendor's figures)
  * the agreement renews automatically for 12-month terms with increases capped at 4 percent  (checks: automatic renewal; renewal price cap)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CUSTOMER = "Saltmarsh Inn Group, LLC"
VENDOR = "Brightline Hospitality Networks, Inc."
EFFECTIVE = date(2024, 3, 15)
COMMENCE = date(2024, 4, 1)
TERM_END = date(2027, 3, 31)
NOTICE_DAYS = 120
OLD_NOTICE_DAYS = 90
NOTICE_BY = TERM_END - timedelta(days=NOTICE_DAYS)
AM_RENEW = date(2027, 3, 15)
AM_NOTICE = date(2026, 12, 15)


def words(n: int) -> str:
    return {36: "thirty-six", 12: "twelve", 90: "ninety", 120: "one hundred twenty", 24: "twenty-four", 4: "four"}[n]


def build(seed: int) -> dict:
    r = rng(seed * 43 + 23)
    inn = r.choice([2400, 2500, 2350])
    harbor = r.choice([1850, 1900, 1750])
    pelican = r.choice([1600, 1650, 1550])
    driftwood = r.choice([1150, 1100, 1200])
    upgrade = inn + r.choice([450, 500, 400])
    iptv = r.choice([600, 650, 700])
    ppl = people(r, 5)
    P = {k: f"{f} {l}" for k, (f, l) in zip(["owner", "am", "vendor_signer", "gm", "cfo"], ppl)}
    base = inn + harbor + pelican
    monthly = upgrade + harbor + pelican + driftwood
    annual = monthly * 12
    naive = {"original": base * 12, "amend1_only": (base + driftwood) * 12, "amend2_only": (upgrade + harbor + pelican) * 12,
             "with_draft": (monthly + iptv) * 12}
    assert len({annual, *naive.values()}) == 5
    return dict(inn=inn, harbor=harbor, pelican=pelican, driftwood=driftwood, upgrade=upgrade, iptv=iptv, P=P, base=base, monthly=monthly,
                annual=annual, naive=naive)


def long(d: date) -> str:
    return d.strftime("%B %-d, %Y")


def emit(seed: int) -> None:
    d = build(seed)
    P = d["P"]
    ws, ref, sol = task_dirs(HERE)
    C = os.path.join(ws, "contracts")
    # ---- MSA
    write_pdf_document(os.path.join(C, "Brightline_MSA_Saltmarsh_executed.pdf"), [
        ("title", "Managed Network Services Agreement"),
        ("p", f"This Managed Network Services Agreement (the \"Agreement\") is entered into as of {long(EFFECTIVE)} (the \"Effective Date\") between "
              f"{VENDOR}, a Delaware corporation (\"Brightline\"), and {CUSTOMER}, a Maine limited liability company (\"Customer\")."),
        ("h", "1. Definitions"),
        ("p", "\"Properties\" means the Customer locations listed in Schedule A, as amended from time to time. \"Services\" means the managed guest and "
              "staff wireless network, internet circuits, network hardware, monitoring and 24/7 guest support described in Schedule B. "
              "\"Service Commencement Date\" means the date on which Brightline certifies the Services live at all Properties then listed in "
              "Schedule A, as confirmed in a Go-Live Certificate signed by both parties."),
        ("h", "2. Services"),
        ("p", "Brightline will provide the Services at each Property in accordance with the service levels in Schedule B."),
        ("h", "3. Term and Renewal"),
        ("p", f"3.1 Initial Term. This Agreement begins on the Effective Date and continues for {words(36)} (36) months from the Service Commencement Date "
              "(the \"Initial Term\")."),
        ("p", f"3.2 Renewal. Upon expiration of the Initial Term, this Agreement will renew automatically for successive renewal terms of {words(12)} (12) "
              f"months each (each a \"Renewal Term\") unless either party gives the other written notice of non-renewal at least {words(OLD_NOTICE_DAYS)} "
              f"({OLD_NOTICE_DAYS}) days before the end of the then-current term."),
        ("p", f"3.3 Renewal Pricing. Brightline may increase the fees for a Renewal Term by no more than {words(4)} percent (4%) over the fees in effect at the "
              "end of the preceding term, on at least sixty (60) days' written notice."),
        ("h", "4. Fees"),
        ("p", "4.1 Customer will pay the monthly fees in Schedule A, invoiced monthly in advance and due net 30. "
              "4.2 Fees for any Property added by amendment begin on that amendment's effective date. "
              "4.3 Fees are fixed for the Initial Term except as changed by a written amendment signed by both parties."),
        ("h", "5. Termination for Cause"),
        ("p", "Either party may terminate this Agreement if the other party materially breaches it and fails to cure within thirty (30) days of written notice."),
        ("h", "9. Notices"),
        ("p", "Notices under this Agreement must be in writing and delivered by courier or certified mail to Brightline Hospitality Networks, Inc., "
              "Attn: Contracts, 500 Commerce Way, Suite 210, Burlington, MA 01803, or to Customer at its address below. Notice is effective on receipt."),
        ("h", "Schedule A - Properties and Monthly Fees"),
        ("table", [["Property", "Location", "Service tier", "Monthly fee"],
                   ["The Saltmarsh Inn", "Kennebunkport, ME", "500 Mbps", f"${d['inn']:,.2f}"],
                   ["Harbor House", "Ogunquit, ME", "300 Mbps", f"${d['harbor']:,.2f}"],
                   ["Pelican Lodge", "Wells, ME", "300 Mbps", f"${d['pelican']:,.2f}"],
                   ["Total", "", "", f"${d['base']:,.2f}"]], {"grid": True, "shade_header": True}),
        ("spacer", 10),
        ("p", f"Signed for Brightline: {P['vendor_signer']}, VP Sales. Signed for Customer: {P['owner']}, Managing Member. Date: {long(EFFECTIVE)}."),
    ], font="Times-Roman", base_size=10)
    # ---- go-live certificate
    write_pdf_document(os.path.join(C, "Go-Live_Certificate.pdf"), [
        ("title", "Go-Live Certificate"),
        ("kv", [("Agreement", f"Managed Network Services Agreement dated {long(EFFECTIVE)}"), ("Customer", CUSTOMER), ("Provider", VENDOR)]),
        ("spacer", 6),
        ("p", "Brightline certifies, and Customer confirms, that the Services are live at all Properties listed in Schedule A: The Saltmarsh Inn "
              "(live March 26, 2024), Harbor House (live March 28, 2024) and Pelican Lodge (live April 1, 2024)."),
        ("kv", [("Service Commencement Date", long(COMMENCE))]),
        ("spacer", 6),
        ("p", f"Accepted: {P['gm']}, Director of Operations, for Customer - April 2, 2024"),
    ], font="Helvetica", base_size=10, pagesize="a4")
    # ---- Amendment 1
    write_pdf_document(os.path.join(C, "Amendment_1_Driftwood_Cottages.pdf"), [
        ("title", "Amendment No. 1"),
        ("p", f"to the Managed Network Services Agreement dated {long(EFFECTIVE)} between {VENDOR} and {CUSTOMER}."),
        ("p", "Amendment Effective Date: October 1, 2024"),
        ("p", "1. Schedule A is amended to add the following Property:"),
        ("table", [["Property", "Location", "Service tier", "Monthly fee"], ["Driftwood Cottages", "Cape Porpoise, ME", "200 Mbps", f"${d['driftwood']:,.2f}"]]),
        ("p", "2. Services at Driftwood Cottages are co-terminous with the Agreement. This Amendment does not change the Initial Term, the Service "
              "Commencement Date or any other term of the Agreement."),
        ("p", f"Signed: {P['vendor_signer']} (Brightline), {P['owner']} (Customer), September 18, 2024."),
    ], font="Helvetica", base_size=10)
    # ---- Amendment 2
    write_pdf_document(os.path.join(C, "Amendment_2_signed.pdf"), [
        ("title", "Amendment No. 2"),
        ("small", f"Managed Network Services Agreement dated {long(EFFECTIVE)} - {VENDOR} / {CUSTOMER}"),
        ("p", "Amendment Effective Date: February 1, 2026"),
        ("h", "1. Bandwidth upgrade"),
        ("p", f"The service tier for The Saltmarsh Inn is upgraded from 500 Mbps to 1 Gbps. Its monthly fee in Schedule A changes from ${d['inn']:,.2f} to "
              f"${d['upgrade']:,.2f}. No other Property fee changes."),
        ("h", "2. Notice of non-renewal"),
        ("p", f"In Section 3.2 of the Agreement, the words \"at least {words(OLD_NOTICE_DAYS)} ({OLD_NOTICE_DAYS}) days\" are replaced with \"at least "
              f"{words(NOTICE_DAYS)} ({NOTICE_DAYS}) days\"."),
        ("h", "3. No other changes"),
        ("p", "Except as set out above, the Agreement, as amended by Amendment No. 1, remains in full force and effect."),
        ("p", f"Signed for Brightline: {P['vendor_signer']}, January 20, 2026. Signed for Customer: {P['owner']}, January 22, 2026."),
    ], font="Courier", base_size=9)
    # ---- Amendment 3 draft
    write_pdf_document(os.path.join(C, "Amendment_3_DRAFT_for_discussion.pdf"), [
        ("title", "DRAFT - Amendment No. 3"),
        ("small", "For discussion only. Not an offer. Not binding unless signed by both parties."),
        ("p", f"1. Add managed in-room TV (IPTV) at all Properties for a monthly fee of ${d['iptv']:,.2f}."),
        ("p", f"2. Extend the Initial Term by {words(24)} (24) months."),
        ("p", "Signed for Brightline: ____________________     Signed for Customer: ____________________"),
    ], font="Helvetica", base_size=10)
    # ---- account manager email
    write_email_thread(os.path.join(ws, "email_from_brightline.txt"), [
        {"from": f"{P['am']} <{P['am'].split()[0].lower()}@brightlinehn.com>", "to": f"{P['owner']} <{P['owner'].split()[0].lower()}@saltmarshinns.com>",
         "date": "Tue, 8 Sep 2026 11:20", "subject": "Your Brightline agreement - renewal coming up",
         "body": (f"Hi {P['owner'].split()[0]},\n\nHope the summer season was a good one. A quick heads-up that your Brightline agreement comes up for renewal on "
                  f"{long(AM_RENEW)}. If you'd like to make any changes, we'd need to hear from you by {long(AM_NOTICE)} (90 days before).\n\n"
                  f"For your planning, your current annual contract value is ${d['base'] * 12:,}. I also attached the IPTV proposal we talked about "
                  "in the spring in case you'd like to add it at renewal.\n\n"
                  f"Best,\n{P['am']}\nAccount Manager, Brightline Hospitality Networks")}])
    # ---- owner note
    write_text(os.path.join(ws, "note_from_owner.txt"),
        f"From {P['owner']}:\n\n"
        "We're thinking about putting the guest Wi-Fi out to bid before we get locked in again. Before I call anyone, I need a short renewal "
        "summary of the Brightline contract from what we actually signed: when the current term ends, the last day we can give notice if we "
        "don't want to renew, what we're paying per year right now, and what happens if we do nothing. All the contract documents are in the "
        "contracts folder.\n")

    facts = {"term_end": [TERM_END.isoformat(), (TERM_END + timedelta(days=1)).isoformat()], "notice_by": [NOTICE_BY.isoformat(), (NOTICE_BY - timedelta(days=1)).isoformat()],
             "notice_days": NOTICE_DAYS, "annual": d["annual"], "monthly": d["monthly"], "am_renew": AM_RENEW.isoformat(), "am_notice": AM_NOTICE.isoformat(),
             "am_annual": d["base"] * 12, "effective_end": (date(2027, 3, 14)).isoformat(), "naive": d["naive"]}
    write_json(os.path.join(ref, "facts.json"), facts)
    memo = (f"# Renewal summary: Brightline managed Wi-Fi agreement\n\n"
            f"To: {P['owner']}\nRe: {VENDOR} - Managed Network Services Agreement dated {long(EFFECTIVE)}\n\n"
            "## Key dates\n\n"
            f"- **Current term ends: {long(TERM_END)}.** The initial term is 36 months from the Service Commencement Date, which the Go-Live "
            f"Certificate sets as {long(COMMENCE)} (not the {long(EFFECTIVE)} signing date). Neither signed amendment changes the term.\n"
            f"- **Last day to give notice of non-renewal: {long(NOTICE_BY)}.** Amendment No. 2 changed the notice period in Section 3.2 from 90 to "
            f"{NOTICE_DAYS} days before the end of the term. Notice must be in writing and is effective when Brightline receives it (courier or "
            "certified mail to Brightline, Attn: Contracts, 500 Commerce Way, Suite 210, Burlington, MA 01803).\n\n"
            "## What we pay now\n\n"
            f"Current monthly fees total ${d['monthly']:,}, so the current annual value is ${d['annual']:,}:\n\n"
            "| Property | Monthly fee | Source |\n|---|---|---|\n"
            f"| The Saltmarsh Inn (1 Gbps) | ${d['upgrade']:,} | Amendment No. 2, from February 1, 2026 |\n"
            f"| Harbor House | ${d['harbor']:,} | Schedule A |\n"
            f"| Pelican Lodge | ${d['pelican']:,} | Schedule A |\n"
            f"| Driftwood Cottages | ${d['driftwood']:,} | Amendment No. 1, from October 1, 2024 |\n"
            f"| **Total** | **${d['monthly']:,}** | |\n\n"
            "Amendment No. 3 (managed TV and a 24-month extension) is an unsigned draft and changes nothing.\n\n"
            "## If we do nothing\n\n"
            f"The agreement renews automatically for a 12-month renewal term (April 1, 2027 to March 31, 2028), and Brightline may raise the fees "
            "for the renewal term by up to 4% with at least 60 days' written notice.\n\n"
            "## Note on Brightline's email\n\n"
            f"The account manager's September 8 email gives the wrong renewal date, uses the old 90-day notice period and quotes the original "
            "annual value from before both amendments. The dates and figures above are from the signed documents.\n")
    write_text(os.path.join(sol, "renewal_summary.md"), memo)

    write_task_yaml(HERE, {
        "id": "contract-renewal-summary", "track": "desk", "category": "drafting",
        "title": "Renewal summary for the Wi-Fi services contract",
        "ask": (f"{P['owner'].split()[0]} wants a renewal summary of our Brightline Wi-Fi contract before we decide whether to go out to bid; the note in the "
                "folder says what is needed. Save it as renewal_summary.md.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            f"the initial term runs 36 months from the Service Commencement Date on the go-live certificate ({long(COMMENCE)}), not the Effective Date ({long(EFFECTIVE)}), so it ends {long(TERM_END)} (check: term, notice and the vendor's figures)",
            f"Amendment 2 lengthens the non-renewal notice from 90 to 120 days, so notice is due by {long(NOTICE_BY)}; 90 days gives December 31, 2026 and counting from the Effective Date gives mid-December or mid-November (check: term, notice and the vendor's figures)",
            f"the current annual value is ${d['annual']:,} (${d['monthly']:,} a month: Schedule A plus Amendment 1's Driftwood Cottages plus Amendment 2's upgrade); the original schedule gives ${d['naive']['original']:,}, Amendment 1 alone ${d['naive']['amend1_only']:,} (check: current annual value)",
            f"Amendment 3 is an unsigned draft adding IPTV at ${d['iptv']:,} a month and a 24-month extension; counting it gives ${d['naive']['with_draft']:,} (checks: current annual value; term, notice and the vendor's figures)",
            f"the account manager's email gives a {long(AM_RENEW)} renewal, a {long(AM_NOTICE)} notice deadline and ${d['base'] * 12:,} a year; a summary may mention them only as wrong (check: term, notice and the vendor's figures)",
            "the agreement renews automatically for 12-month terms and renewal fees may rise by up to 4 percent (checks: automatic renewal; renewal price cap)",
        ],
        "checks": [
            {"type": "file_exists", "name": "renewal_summary.md exists", "path": "renewal_summary.md"},
            {"type": "text_numbers_present", "name": "current annual value", "path": "renewal_summary.md", "numbers": [d["annual"]], "rel_tol": 0.00001},
            {"type": "custom", "name": "term, notice and the vendor's figures", "module": "check.py"},
            {"type": "text_sentence_matches", "name": "automatic renewal", "path": "renewal_summary.md",
             "all": [r"automatic|auto-?renew|evergreen|renews? (itself )?(on its own|by itself)", r"\b12\b|twelve|one[- ]year|1[- ]year|annual|yearly"],
             "none": [r"\b(not|no|never|won't|doesn't|does not|will not|isn't)\b[^.;]{0,25}\bauto"]},
            {"type": "text_sentence_matches", "name": "renewal price cap", "path": "renewal_summary.md",
             "all": [r"(?<![\d.])4\s*(%|percent|per cent)|four percent", r"increas|rais|price|fee|go up|escalat"]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
