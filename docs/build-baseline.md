# Enterprise baseline for build-track apps

Every build task's `checklist.md` opens with these items, numbered 1 to 14, with the placeholders in
angle brackets filled from the task's `reference/counts.json`. App-specific items follow from 15. Items
marked (CORE) define "first usable" together with the task's own core items. A tester works the list
with the app URL, `RESULT.json`, and this text; nothing else. "Reject" means a visible message and no
change after reload.

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

**Test records.** Delete every record you create once the item that needed it is judged, so later exact
counts and dashboard figures keep their imported values. Where the app refuses deletion (by design or
because audit rules forbid it), note the extra records and adjust later expected counts by exactly that
many.

**The item-8 record.** Create the record item 8 asks for outside the restricted login's scope, so the
scoped counts in items 6 and 9 keep their values, and delete it once item 9 is judged.

**Percentages.** A percentage figure passes when it matches to one decimal place, written as a percent or
a fraction.

**Reruns after a change request.** Each change turn is graded on the app as it stands after that turn.
Rerun the full list. Where an item acts on a named record that an earlier pass already changed (an invoice
generated, a member renewed), judge that record as the earlier pass left it rather than repeating the
action. Expected counts and dashboard figures are the imported values plus any records a change request
itself asks the app to create; the change file states those deltas.

**Dates.** Where an expected value depends on the test date (lapsed, expiring, overdue), the task's
checklist introduction states the window of test dates for which the quoted values hold.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; <STAFF_ROLE> creates and edits records in its scope and has no user management or settings; <VIEWER_ROLE> is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create one <MAIN_ENTITY> and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only <SCOPE_RULE>, exactly <SCOPE_COUNT> <MAIN_ENTITY_PLURAL>, and cannot open another scope's record by URL.
   How to check: As restricted, read the <MAIN_ENTITY_PLURAL> total and open five records to confirm scope. As admin, copy the URL of <OUT_OF_SCOPE_EXAMPLE>; paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute <OUT_OF_SCOPE_EXAMPLE>'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: <KPI_1> = <KPI_1_VALUE>, <KPI_2> = <KPI_2_VALUE>, <KPI_3> = <KPI_3_VALUE>, <KPI_4> = <KPI_4_VALUE>; after the tester creates one <MAIN_ENTITY>, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create one <MAIN_ENTITY> in scope of <KPI_1>, reload, confirm <KPI_1> moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: <KPI_1> = <SCOPED_KPI_1_VALUE>.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `<SEARCH_TERM>` returns exactly <SEARCH_COUNT> row(s); filtering on <FILTER_FIELD> = <FILTER_VALUE> returns <FILTER_COUNT>; sorting by <SORT_FIELD> descending puts <SORT_TOP> first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly <EXPORT_ROWS> data rows and includes the columns <EXPORT_COLUMNS>.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create one <MAIN_ENTITY>, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting one <MAIN_ENTITY> without <REQUIRED_FIELD> through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

---

Tags used: Delivery, Sharing, Permission, API, Dashboard, Exact, Audit, Rule, Persistence, plus the
task's own Automation and Rule items. Core baseline: 1, 3, 5, 6, 8, 14.
