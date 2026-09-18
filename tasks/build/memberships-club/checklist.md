# Acceptance checklist: memberships-club

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json`
(seed 0). They hold for any test date from 2026-09-01 to 2027-02-28: no imported expiry date falls
in that window.

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names: trainer Jess Alvarez), and `notes`. Use two browsers or a private window for the second
session. Invitations need no email delivery: the app must show the invite link to the admin. "Reject"
means a visible message and no change after reload. A member is active when not cancelled and their
expiry date is on or after the test date, lapsed when not cancelled and the expiry date has passed.
When an item has you create a member without naming one, create an Annual member with no trainer,
joined on the test date, and delete it once the item is judged, so later counts hold. Do items in
order: 19 to 23 build on each other. A rerun after a change request works on the same app: where an
earlier pass already performed an item's action on a named member (renewed, frozen), judge the item on
the member as that pass left it instead of repeating the action.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Trainer creates and edits records in its scope and has no user management or settings; Read-only is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a member and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only members whose trainer is Jess Alvarez, exactly 23 members, and cannot open another scope's record by URL.
   How to check: As restricted, read the members total and open five records to confirm scope. As admin, copy the URL of member M-01380 (Michelle Bailey, trainer Kofi Mensah); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute member M-01380 (Michelle Bailey, trainer Kofi Mensah)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Active members = 152, Lapsed members = 37, Check-ins in August 2026 = 185, Cancelled members = 31; after the tester creates one member, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a member in scope of Active members, reload, confirm Active members moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Active members = 14.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Whitfield` returns exactly 3 row(s); filtering on Plan = Quarterly returns 50; sorting by Expires descending puts Nicholas Howard (M-01513, `30-Dec-2027`) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 220 data rows and includes the columns Member #, Name, Plan, Expires, Trainer, Status.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a member, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a member without Plan through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. [Exact] The members list holds exactly 220 members (229 file rows minus 4 exact duplicate rows and 5 rows that repeat a member number written without its prefix or padding, with the email in another case): Nadia Foster (`2445` on line 25, `M-02445` on line 110) appears once, and Karen Campbell (M-00124, lines 103 and 105) appears once.
    How to check: As admin, read the members total and search both names. Pass only at exactly 220 and one result for each name. (229 = no dedupe; 225 = only exact duplicates removed.)

16. [Exact] Members who share an email stay separate members: Grace Okonkwo (M-00102) and Daniel Okonkwo (M-00352) share okonkwo.home@yahoo.com; Sean Brannigan (M-02557) and Maeve Brannigan (M-01085) share brannigans@outlook.com; all four exist with their own plans and expiry dates.
    How to check: As admin, search `Okonkwo` and `Brannigan`. Pass only if each search returns exactly two members carrying the member numbers above. (A dedupe on email collapses each pair, and the item-10 Whitfield search to 2.)

17. (CORE) [Exact] Lapsed is computed from the expiry date, not the file's Status column: the lapsed members are exactly 37, including Amy Bailey (M-01951, `Active` in the file, expired 2026-06-30) and Carlos Roberts (M-00403, `Active`, expired 2026-05-07) and excluding Kwame Stewart (M-01198, `Canceled`, expired 2026-05-31); all 31 members whose status is Cancelled, Canceled, or CANCELLED count as cancelled.
    How to check: As admin, open the lapsed list, filter, or dashboard drill-down and read its total; look for the three members; filter cancelled members and read that total. Fail if either total differs, either Active-in-file member is missing from lapsed, or Kwame Stewart shows as lapsed. (Trusting the file's Status gives 10 lapsed; counting cancelled members as lapsed gives 68; missing the `Canceled` spelling gives 22 cancelled and 46 lapsed.)

18. [Exact] The impossible birth date was flagged, not silently imported: Jacob Garcia (M-01231) has date of birth `2031-04-17` in the file; the member exists, and the birth date shows a visible warning, flag, or import-issue entry, or is blank with the original value recorded on the member or in an import report the admin can open.
    How to check: As admin, open Jacob Garcia and any import summary, log, or issues screen. Fail if the member is missing, or the birth date reads 2031-04-17 with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

19. (CORE) [Automation] Renewing an active member adds one term to the current expiry: renewing Betty Thompson (M-01572, Quarterly, expires 2027-04-18) moves her expiry to 2027-07-18 and records a renewal of 180.00 in her history; the members total does not change.
    How to check: As admin, renew her once and reload. Fail if the expiry differs (the test date plus 3 months means the term was counted from today), no renewal record of 180.00 exists, or a second Betty Thompson appears.

20. [Rule] Renewing a lapsed member starts the new term on the renewal day: renewing Amy Bailey (M-01951, Annual, expired 2026-06-30) sets her expiry to the test date plus 12 months, records 660.00, and moves the dashboard's Lapsed members down by one and Active members up by one.
    How to check: As admin, read the dashboard, renew Amy Bailey, reload her record and the dashboard. Fail if the expiry is 2027-06-30 or otherwise not the test date plus 12 months (one day either way is accepted), no 660.00 renewal is recorded, or either figure did not move by exactly one.

21. (CORE) [Rule] A freeze pushes the expiry back by its length and cannot exceed 60 days: freezing Kwame Thomas (M-01669, Monthly, expires 2027-04-10) for 30 days from the test date shows him as frozen with expiry 2027-05-10; a 61-day freeze on Laura Whitfield (M-00143) is rejected.
    How to check: As admin, freeze Kwame Thomas for 30 days starting today and reload; then try a 61-day freeze on Laura Whitfield and reload. Fail if Kwame Thomas shows no frozen state or an expiry other than 2027-05-10, or Laura Whitfield ends up frozen or with a changed expiry.

22. [Exact] Check-ins were imported with double scans counted once: the check-in log holds exactly 226 visits (238 file rows minus 12 second scans a few minutes after the first), 185 of them in August 2026; Deborah Anderson (M-00506, written `506`, `00506`, and `M-00506` in the file) shows exactly 9 visits in August 2026 (11 file rows) and 1 in July.
    How to check: As admin, read the check-in log total with no filter, then filter to August 2026; open Deborah Anderson's visit history. Fail on any difference (238 and 195 = double scans kept; fewer than 9 for Deborah = her rows written `506` or `00506` not matched to her).

23. [Rule] Nobody frozen, lapsed, or cancelled gets in: a check-in is rejected for Kwame Thomas (frozen in item 21), Carlos Roberts (M-00403, lapsed, `Active` in the file), and Kwame Stewart (M-01198, cancelled); a check-in for Mary Parker (M-01346, active) is accepted and appears in the check-in log with the test date and time.
    How to check: As admin, check in each of the four by member number or name, then reload the log. Fail if any of the first three is recorded, or Mary Parker's check-in is refused or missing.

24. [Exact] Plans were read from their spellings (`annual`, `ANNUAL`, `Monthly ` with a trailing space): members per plan are exactly Monthly 102, Quarterly 50, Annual 68, and the plans are priced 65.00, 180.00, and 660.00.
    How to check: As admin, filter members by each plan and read the counts (subtract any member you created and kept); read the prices on the plans screen or on one member of each plan. Fail if a fourth plan spelling exists, or any count or price differs.

25. [Permission] A trainer sees only their own clients' visits: signed in as restricted, the check-in log or client visit views show only visits by Jess Alvarez's clients, exactly 24 in August 2026, including Deborah Anderson's 9; the visit history of Michelle Bailey (M-01380, Kofi Mensah's client) opened by URL from the admin session shows an error, not-found, or access-denied.
    How to check: As restricted, open the check-in log (or each client's visits) filtered to August 2026 and total it; paste Michelle Bailey's visit-history URL. Fail if a non-client's visit appears, the count differs, the trainer cannot see their clients' visits at all, or Michelle Bailey's history renders.

26. [Permission] A front desk login sees and handles every member but cannot manage the app: admin can invite `tester.desk@example.com` with a front desk role; signed in as that user the members list shows every member (220, plus any the tester kept), a check-in for Ethan Whitfield (M-00136) is accepted, and the users and settings areas are absent or refused.
    How to check: As admin, invite the front desk user and accept the invite in a private window. As that user, read the members total, check in Ethan Whitfield, and try the users and settings pages. Fail if no front desk role exists, the total is short, the check-in is refused, or users or settings open.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 4 (5, 6, 25, 26), API 1 (7), Dashboard 2 (8, 9), Exact 8 (10, 11, 15 to 18, 22, 24), Audit 1 (12), Rule 4 (13, 20, 21, 23), Automation 1 (19), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 17, 19, 21.
