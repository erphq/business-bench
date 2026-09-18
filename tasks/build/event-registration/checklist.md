# Acceptance checklist: event-registration

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json`
(seed 0). No figure depends on the test date.

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names: session chair Helena Varga), and `notes`. Use two browsers or a private window for the
second session. Invitations need no email delivery: the app must show the invite link to the admin.
"Reject" means a visible message and no change after reload. Revenue counts the Amount of confirmed
registrations only. When an item has you create a registration without naming one, register a new
attendee (`tester.attendee@example.com`, amount 195.00) for WS-019 Frontline Retention, which has free
seats, and delete it once the item is judged, so later counts hold. Do items in order: 20 to 24 build
on each other. A rerun after a change request works on the same app: where an earlier pass already
performed an item's action on a named registration (cancelled, promoted), judge the item on the record
that pass left instead of repeating the action.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Session chair creates and edits records in its scope and has no user management or settings; Read-only is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a registration and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only registrations for the sessions Helena Varga chairs (WS-084, WS-157, WS-161), exactly 39 registrations, and cannot open another scope's record by URL.
   How to check: As restricted, read the registrations total and open five records to confirm scope. As admin, copy the URL of registration R-37091 (Patricia Stewart, WS-155); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute registration R-37091 (Patricia Stewart, WS-155)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Confirmed registrations = 255, Waitlisted registrations = 9, Revenue from confirmed registrations = 39,306.00, Full sessions = 5; after the tester creates one registration, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a registration in scope of Confirmed registrations, reload, confirm Confirmed registrations moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Confirmed registrations = 34.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Dorsey` returns exactly 13 row(s); filtering on Status = Waitlisted returns 9; sorting by Registered At descending puts R-35356 (Fatima Tanaka, `9/10/2026 4:45 PM`) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 276 data rows and includes the columns Registration ID, Attendee, Email, Session, Status, Amount.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a registration, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a registration without Email through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. [Exact] The rooms list holds exactly 60 rooms (64 file rows minus 2 exact duplicate rows and 2 rows repeating a room code written without its hyphen, name in capitals): Lakeside Breakout 4 (lines 22 and 54) appears once; Harbor Suite 8 (`RM-343` on line 27, `RM343` / `HARBOR SUITE 8` on line 24) appears once; sorting rooms by capacity, largest first, puts Grand Hall (written `1,200`) first.
    How to check: As admin, open the rooms list, read the total, search both names, and sort by capacity. Fail if the total differs, either room appears twice, or another room sorts first.

16. [Exact] The sessions list holds exactly 60 sessions (64 file rows minus 2 exact duplicates and 2 rows repeating a session under its bare number): WS-169 Rolling Forecasts (lines 43 and 45) appears once; WS-084 Safety Culture, whose room is written `rm-052`, shows room Harbor Studio 3 with capacity 18; the 8 sessions priced `Free` show a price of 0.00.
    How to check: As admin, read the sessions total, search `Rolling Forecasts`, open WS-084, and filter or sort sessions by price. Fail if the total differs, WS-169 appears twice, WS-084 has no room or capacity, or a `Free` session has no numeric price.

17. [Exact] The impossible session was flagged, not silently imported: WS-128 Working Capital on 2026-10-13 is written with start `11:00 AM` and end `10:15 AM`; the session exists, and its times show a visible warning, flag, or import-issue entry, or are corrected with the original values recorded on the session or in an import report the admin can open.
    How to check: As admin, open WS-128 and any import summary, log, or issues screen. Fail if the session is missing, or it shows an end before its start with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

18. (CORE) [Exact] Registration statuses were read from eight spellings (`Confirmed`, `confirmed`, `CONFIRMED`, `Waitlisted`, `waitlist`, `Wait list`, `Cancelled`, `canceled`): after removing 8 exact duplicate rows there are 276 registrations, 255 confirmed, 9 waitlisted, 12 cancelled; WS-084 shows 18 of 18 seats confirmed and 3 waitlisted, and the full sessions are exactly WS-002, WS-007, WS-037, WS-084, WS-155.
    How to check: As admin, filter registrations by each status and read the counts; open WS-084; filter or read the full sessions. Fail on any difference.

19. [Exact] Revenue counts confirmed seats only: WS-084's revenue is 3,871.00 (its three waitlisted rows carry 735.00 that does not count), and total revenue is 39,306.00.
    How to check: As admin, read WS-084's revenue on the session page or a revenue report (or total the confirmed amounts filtered to WS-084), and the dashboard total. Fail if either differs (42,364.00 = every row counted; 40,961.00 = waitlisted amounts counted).

20. [Exact] The badge export has exactly 137 rows, one per attendee with at least one confirmed registration, each with the attendee's name and company: Ronald Ruiz (Uptown Fitness, three confirmed registrations, email written in three different cases) appears once, and Ryan Lopez (only a waitlisted registration) does not appear.
    How to check: As admin, before item 21, run the badge export and open the file; count rows and search both names. Fail if the export is absent, the count differs (255 = one badge per registration; 139 = emails compared case-sensitively), Ronald Ruiz appears more than once, or Ryan Lopez appears.

21. (CORE) [Rule] A full session never gets more confirmed seats than its room holds: registering a new attendee (`tester.waitlist@example.com`) for WS-084 does not confirm them; the registration is waitlisted or the confirmation is rejected, and WS-084 still shows 18 confirmed.
    How to check: As admin, create the registration with status Confirmed if the form offers it, then reload WS-084. Fail if the new registration is confirmed or WS-084 shows 19 confirmed.

22. [Rule] The server refuses a manual confirmation into a full session: changing Nadia Kim's waitlisted registration (R-33838, WS-084) to Confirmed through the form is rejected, and replaying that status change (devtools > copy as cURL) is also rejected.
    How to check: As admin, try the change in the form; copy any status-update request the app sends for a registration and re-issue it with R-33838's id and Confirmed; reload WS-084. Fail if Nadia Kim is confirmed or WS-084 shows more than 18 confirmed.

23. (CORE) [Automation] Cancelling a confirmed seat promotes the longest-waiting registration by arrival time, with no manual step: cancelling Ronald Richardson (R-31715, confirmed in WS-084) makes Dorothy Murphy (R-32464, registered `8/15/2026 5:50 PM`, file line 147) confirmed, while Nadia Kim (R-33838, `2026-08-16 10:40`, line 144) and Ryan Lopez (R-36363, `17-Aug-2026 12:25`, line 146) stay waitlisted; WS-084 again shows 18 confirmed.
    How to check: As admin, read the dashboard Revenue and Waitlisted figures (for item 24), cancel R-31715, and reload WS-084. Fail if anyone other than Dorothy Murphy was promoted (Nadia Kim = file order; Ryan Lopez = timestamps compared as text), nobody was promoted, or a manual step was needed.

24. [Exact] The figures follow the promotion: after item 23 the dashboard Revenue is exactly 49.00 higher than the value read at the start of item 23 (Ronald Richardson's 196.00 early-bird seat out, Dorothy Murphy's 245.00 in), and Waitlisted registrations is exactly one lower.
    How to check: As admin, reload the dashboard and compare. Fail if revenue moved by any other amount or Waitlisted did not fall by exactly one.

25. [Rule] A session cannot move into a room smaller than its confirmed seats: moving WS-084 (18 confirmed) to Convention Meeting Room 9 (RM-283, capacity 12, unused in that time slot) is rejected, and WS-084 stays in Harbor Studio 3.
    How to check: As admin, edit WS-084's room to RM-283 and save; reload. Fail if the move saves.

26. [Permission] A session chair manages registrations only in their own sessions and cannot change rooms: as restricted, cancelling Emily Clark (R-33825, confirmed in WS-161, Helena's session) succeeds; replaying a cancel for Richard Jones (R-31095, WS-033, chaired by Priyanka Rao) from the restricted session is rejected; changing any room's capacity is absent or rejected.
    How to check: As restricted, cancel R-33825 and copy that request as cURL; re-issue it with R-31095's id; try to edit a room capacity (for example Harbor Studio 3); reload each as admin. Fail if Emily Clark is not cancelled, Richard Jones is cancelled, or a room capacity changed.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 26), API 1 (7), Dashboard 2 (8, 9), Exact 10 (10, 11, 15 to 20, 24), Audit 1 (12), Rule 4 (13, 21, 22, 25), Automation 1 (23), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 18, 21, 23.
