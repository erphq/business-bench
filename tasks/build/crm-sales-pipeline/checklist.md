# Acceptance checklist: crm-sales-pipeline

Twenty-six binary items: the enterprise baseline (1 to 14, from `docs/build-baseline.md`) and twelve
app items (15 to 26). Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

**This app.** "Restricted" is the Rep login for **Leila Haddad**; the read-only role is **Analyst**.
Open deals are deals in Lead, Qualified, Proposal, or Negotiation. The weighted pipeline is the sum over
open deals of Amount times the stage probability (Lead 0.10, Qualified 0.25, Proposal 0.50, Negotiation
0.75); a blank amount counts as zero. Money is exact to the cent. When an item has the tester create a
deal without naming one, create it on account **Alder Street Clinics** (a Rahul Patel account) at stage
Lead with amount 10,000.00 and delete it once the item is checked; items that change an imported deal
end by changing it back. Every rerun after a change request therefore starts from the import figures.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Rep creates and edits records in its scope and has no user management or settings; Analyst is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a deal and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only the deals owned by Leila Haddad (the deals on her accounts), exactly 30 deals, and cannot open another scope's record by URL.
   How to check: As restricted, read the deals total and open five records to confirm scope. As admin, copy the URL of Tomasz Nowak's deal Dunmore Hospitality - Board advisory; paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute Tomasz Nowak's deal Dunmore Hospitality - Board advisory's id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Open deals = 67, Open pipeline value = 4,732,000.00, Weighted pipeline = 1,810,800.00, Won value = 728,000.00; after the tester creates one deal, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a deal in scope of Open deals, reload, confirm Open deals moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Open deals = 23.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Coppermine Analytics` returns exactly 2 row(s); filtering on Stage = Proposal returns 17; sorting by Amount descending puts Sable Point Lighthouse Foundation - Data strategy first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 90 data rows and includes the columns Deal, Account, Owner, Stage, Amount, Expected Close.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a deal, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a deal without an account through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] The accounts list contains exactly **72** accounts (80 file rows minus 5 exact duplicate rows and 3 rows repeating an account with its name in capitals and its website written differently).
    How to check: As admin, read the total on the accounts list, or count rows via export or an unfiltered view. Pass only at exactly 72. (80 = no dedupe; 75 = exact duplicate rows only; 69 = the four blank-website accounts collapsed into one.)

16. [Exact] Account duplicates are merged and blank websites are kept apart: a search for "Bellwether Logistics" (in the file as `https://www.bellwetherlogistics.com/` and again as BELLWETHER LOGISTICS with `WWW.BELLWETHERLOGISTICS.COM`) returns exactly one account, and the four blank-website accounts, Foxhollow Veterinary Group, Pilgrim Freight Lines, Trailhead Bicycles, and Xander Data Centers, each exist as one account.
    How to check: As admin, run the search, then search each of the four names. Pass only if every search returns exactly one account.

17. [Exact] The contacts list contains exactly **142** contacts (150 file rows minus 2 exact duplicates and 6 rows repeating an email in different capitals); the five blank-email contacts Amy Kim, Emily Castillo, Kenneth Thomas, Luis Tanaka, and Nadia Perez are separate contacts; and **Nancy Clark** exists twice, once at Driftwood Studios and once at Pilgrim Freight Lines.
    How to check: As admin, read the contacts total; search "Dmitri King" (dmitri.king@ellerytextiles.com and DMITRI.KING@ELLERYTEXTILES.COM in the file) and expect one result; search each blank-email name and expect one each; search "Nancy Clark" and expect two, at those two accounts. Pass only at exactly 142 with every search as stated. (150 = no dedupe; 148 = exact rows only; 138 = blank emails merged; 141 = the two Nancy Clarks merged.)

18. [Exact] Contacts are linked to their accounts even where the file wrote the account in capitals or with a trailing space: account **Millbrook Orthopedics** shows exactly **3** contacts, Anthony Murphy, Jennifer Myers, and Paul Watson (Jennifer Myers's row reads "Millbrook Orthopedics " with a trailing space), and no contact is without an account.
    How to check: As admin, open Millbrook Orthopedics and read its contacts; then filter or sort the contacts list by account and look for blanks. Fail if the account shows a different number, Jennifer Myers is missing from it, or any contact has no account.

19. [Exact] Stages were mapped onto the six pipeline stages: the stage field offers exactly Lead, Qualified, Proposal, Negotiation, Won, Lost, and the deals per stage are Lead **18**, Qualified **20**, Proposal **17**, Negotiation **12**, Won **13**, Lost **10**.
    How to check: As admin, open a deal's stage selector and list the options, then filter or group the deals list by each stage. Fail on any extra value (such as "lead", "PROPOSAL", or "Closed Won" as its own stage) or any count that differs.

20. [Exact] Expected Close was imported as a date: sorting deals by Expected Close, latest first, puts **Riverlane Apartments - Succession planning** (file value `Jun 30 2027`) first.
    How to check: As admin, sort the deals list by Expected Close descending. Fail if the field cannot be sorted as a date or another deal is first (a text sort puts Xander Data Centers - Process redesign, "September 08, 2026", first).

21. [Exact] The deal with an impossible negative amount (**Parkstone Engineering - Cost reduction program**, Lost, Amount `-4,500.00`) was imported and flagged or corrected, not silently kept: the deal exists and shows a visible warning, flag, or import-issue entry; or its amount is blank or 0 with the original -4,500.00 recorded on the deal or in an import report the admin can open.
    How to check: As admin, open the deal and any import summary, log, or issues screen. Fail if the deal is missing, or shows -4,500.00 with no warning, flag, note, or issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

22. (CORE) [Exact] The weighted pipeline follows stage changes: moving **Ashgrove Manufacturing - Operations assessment** (Leila Haddad, 65,000.00) from Proposal to Negotiation raises the weighted pipeline by exactly **16,250.00** (65,000.00 x (0.75 - 0.50)), from 1,810,800.00 to **1,827,050.00**, and Leila Haddad's own weighted pipeline from 490,300.00 to **506,550.00**; moving it back restores both.
    How to check: As admin, read the dashboard weighted pipeline, move the deal to Negotiation, reload, and read it again; as restricted, open the dashboard and read the weighted pipeline. Then, as admin, move the deal back to Proposal and reload. Pass only if the admin figure is 1,827,050.00 after the move and 1,810,800.00 after the move back, and the restricted figure was 506,550.00. Fail if a figure does not move or is off by any amount.

23. [Rule] A deal cannot be moved into Proposal without both an amount and a contact.
    How to check: As admin, create a deal on the setup account at stage Qualified with no amount and no contact; try to move it to Proposal (expect rejection); set amount 10,000.00 and try again (expect rejection); add contact Jennifer Peterson and try again (expect success). Delete the deal. Pass only if both first attempts show a visible message and the stage still reads Qualified after reloading each time, and the last attempt saves Proposal.

24. [Rule] A deal cannot be marked Lost without a lost reason.
    How to check: As admin, create a deal on the setup account (stage Lead, amount 10,000.00, contact Jennifer Peterson); set the stage to Lost with the lost reason empty and save (expect rejection; after reload the stage is still Lead); then pick or enter the reason "Price" and save (expect success). Delete the deal. Fail if the first save is accepted.

25. (CORE) [Automation] A rep can log a call, email, or meeting on a deal, and the entry appears on that deal and on its account with who logged it and when.
    How to check: As restricted, open Ashgrove Manufacturing - Operations assessment, log a call dated 2026-09-14 with the note "Pricing follow-up", and reload. As admin, open that deal and then its account, Ashgrove Manufacturing. Pass only if the call shows in both places with the type call, the date 2026-09-14, the note, and Leila Haddad as the person who logged it. Fail if activities cannot be logged, show in only one place, or show no user or the wrong user.

26. [Permission] Scope covers accounts and contacts too: the restricted login sees exactly **26** accounts and **47** contacts, all on accounts owned by Leila Haddad, and cannot open Tomasz Nowak's account **Amberly Cosmetics** by URL.
    How to check: As restricted, read the accounts and contacts totals and open five of each to confirm the owner. As admin, copy the URL of Amberly Cosmetics and paste it in the restricted session. Pass only on both exact totals and an error, not-found, or redirect that does not render that account's name, website, or contacts.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 26), API 1 (7), Dashboard 2 (8, 9), Exact 10 (10, 11, 15 to 22), Audit 1 (12), Rule 3 (13, 23, 24), Automation 1 (25), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 22, 25.
