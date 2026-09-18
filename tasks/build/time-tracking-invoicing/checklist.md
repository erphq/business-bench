# Acceptance checklist: time-tracking-invoicing

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json`
(seed 0). No figure depends on the test date: every imported entry is dated July or August 2026.

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names: consultant Nadia Okafor), and `notes`. Use two browsers or a private window for the second
session. Invitations need no email delivery: the app must show the invite link to the admin. "Reject"
means a visible message and no change after reload. "Billed hours" are an entry's hours after the
firm's rounding (each entry rounded up to the next 15 minutes); an entry's amount is billed hours times
the client's hourly rate for the consultant's role. When an item has you create a time entry without
naming one, log it as Eleanor Voss for Highfield Robotics, billable, dated the test date, and delete it
once the item is judged, so later counts hold. Do items in order: 20 to 25 build on each other. A rerun
after a change request works on the same app: where an earlier pass already performed an item's action
on a named record (an invoice generated), judge the item on the record that pass left instead of
repeating the action.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Consultant creates and edits records in its scope and has no user management or settings; Read-only is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a time entry and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only Nadia Okafor's own time entries, exactly 22 time entries, and cannot open another scope's record by URL.
   How to check: As restricted, read the time entries total and open five records to confirm scope. As admin, copy the URL of entry TE-40232 (Marcus Iyer); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute entry TE-40232 (Marcus Iyer)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Unbilled amount = 79,372.50, Unbilled hours = 311.75, Billable hours in August 2026 = 289.75, Clients with unbilled time = 23; after the tester creates one time entry, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a time entry in scope of Unbilled amount, reload, confirm Unbilled amount moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Unbilled amount = 8,767.50.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Vantage` returns exactly 6 row(s); filtering on Billable = No returns 39; sorting by Duration (billed or logged hours) descending puts TE-40217 first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 251 data rows and includes the columns Date, Consultant, Client, Hours, Billable, Invoice.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a time entry, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a time entry without Client through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. [Exact] The clients list holds exactly 60 clients (64 file rows minus 2 exact duplicate rows and 2 rows that repeat a client code written without its leading zero): a client search for `Nettlefield` (file lines 47 and 53) returns one client, and a search for `Larkfield` (C-0728 on line 12; C-728 with the name in capitals on line 38) returns one client.
    How to check: As admin, read the clients total and run both searches. Pass only at exactly 60 and one result for each search. (64 = no dedupe; 62 = only exact duplicates removed.)

16. [Exact] Rates were joined to clients across code spellings and currency strings: Kittering Dairy Cooperative (`C-0665` in clients.csv, `665` in rates.csv, rates written `$390.00`) shows Partner 390.00, Senior 250.00, and Associate 150.00 per hour.
    How to check: As admin, open that client or the rate card and read the three hourly rates. Fail if any is missing, zero, or different.

17. [Exact] The impossible rate was flagged, not silently imported: Orchard Lane Grocers (C-0140) has its Associate rate written `-$200.00`; the client exists, and its Associate rate shows a visible warning, flag, or import-issue entry, or is blank or zero with the original -200.00 recorded on the client or in an import report the admin can open.
    How to check: As admin, open Orchard Lane Grocers and any import summary, log, or issues screen. Fail if the client is missing, or the rate reads -200.00 with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

18. [Exact] Timesheet rows were cleaned: entry TE-40072 (file lines 74 and 196) exists once, and durations written four ways were read as time and billed rounded up: TE-40233 `0:20` = 0.50 billed hours (105.00), TE-40137 `1.67` = 1.75 (297.50), TE-40154 `59 min` = 1.00 (210.00), TE-40085 `4h 29m` = 4.50 (1,215.00).
    How to check: As admin, search the entries for TE-40072 and count the results; open the other four entries and read billed hours or amount. Pass only if TE-40072 appears once and all four match on hours or amount. Fail if an entry shows its duration as text only, or the app offers no billed hours or amount before invoicing.

19. (CORE) [Rule] New entries are billed in quarter hours rounded up, entry by entry: three new billable entries of 7 minutes, 1 hour 16 minutes, and 45 minutes record billed hours 0.25, 1.50, and 0.75.
    How to check: As admin, create the three entries (per Setup, as Eleanor Voss for Highfield Robotics on the test date), entering the durations in whatever form the app takes; read each entry's billed hours, or its amount divided by Highfield Robotics' Partner rate; then delete them. Fail if any differs (nearest quarter gives 0.00, 1.25, 0.75; no rounding gives 0.12, 1.27, 0.75).

20. [Exact] Unbilled time is tracked per client, including late entries from an earlier month and excluding non-billable time: Kittering Dairy Cooperative's unbilled amount is exactly 5,955.00 (its six August entries, 5,272.50, plus TE-40132, a 2026-07-31 entry of 682.50 that was never invoiced; the non-billable TE-40141 adds nothing).
    How to check: As admin, read Kittering's unbilled amount on its client page or an unbilled report, or filter unbilled entries to that client and total them. Fail if no per-client figure or filter exists, or the value differs (5,272.50 = the late July entry missed; 6,150.00 = the non-billable entry counted).

21. (CORE) [Automation] Generating the August 2026 invoice for Kittering Dairy Cooperative creates one invoice whose lines are exactly its six billable August entries (TE-40172, TE-40196, TE-40203, TE-40221, TE-40235, TE-40239): 20.25 billed hours, total 5,272.50.
    How to check: As admin, read the dashboard Unbilled amount (for item 25), then run the app's invoice generation for that client and month (tax or discount 0 if present) and open the invoice. Pass only if the lines are exactly those six entries and the total is exactly 5,272.50. Fail if generation needs the tester to pick entries one by one (5,210.00 = nearest-quarter rounding; 5,185.83 = no rounding; 5,955.00 = late July entry included; 5,467.50 = non-billable entry included).

22. [Exact] Invoice lines carry billed hours, the rate for the consultant's role, and the amount: on the item-21 invoice, TE-40235 (Nadia Okafor, Senior, written `227 min`) reads 4.00 hours at 250.00 = 1,000.00, and TE-40239 (Eleanor Voss, Partner, written `0.67`) reads 0.75 hours at 390.00 = 292.50.
    How to check: As admin, open the item-21 invoice and read both lines. Fail if either line's hours, rate, or amount differs, or the lines show no hours or rate.

23. (CORE) [Rule] Invoiced entries are locked for everyone: after item 21, changing the duration of TE-40221 as admin is rejected; the imported July entry TE-40015 (invoice INV-2607-0654) can be neither edited nor deleted as admin; signed in as restricted, Nadia Okafor's own invoiced entry TE-40079 cannot be edited.
    How to check: Attempt each of the four changes and reload. Pass only if every one is rejected (no control, or a visible message) and every value is unchanged after reload.

24. [Rule] No time is billed twice: generating Kittering Dairy Cooperative's August 2026 invoice again creates no second invoice containing any of the six entries (refused, or an empty invoice of 0.00), and generating its July 2026 invoice yields exactly 682.50 holding only TE-40132 (every other billable July entry already carries invoice INV-2607-0665 from the old system).
    How to check: As admin, run generation for August again, then for July; open the client's invoices. Fail if any entry appears on two invoices, the July invoice holds any entry other than TE-40132, or its total differs.

25. [Exact] The dashboard's unbilled figure follows invoicing: after items 21 and 24 the Unbilled amount is exactly 5,955.00 lower than the value read at the start of item 21.
    How to check: As admin, reload the dashboard and subtract. Fail if the difference is not exactly 5,955.00.

26. [Permission] A consultant logs time only as themselves and cannot invoice: signed in as restricted, the new-entry form offers no way to pick another consultant (or saving one for Marcus Iyer is rejected); a replayed create request naming Marcus Iyer is rejected or saved as Nadia Okafor; no invoice generation is available or accepted.
    How to check: As restricted, open the entry form and try to choose Marcus Iyer; create an entry, copy its request as cURL, change the consultant to Marcus Iyer's id or name, and re-issue; as admin check who the replayed entry belongs to; look for invoice generation as restricted and re-issue the admin session's generation request (from devtools) with the restricted session's cookie or token. Fail if an entry is saved under Marcus Iyer or an invoice is generated. Delete the test entries afterwards.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 26), API 1 (7), Dashboard 2 (8, 9), Exact 10 (10, 11, 15 to 18, 20 to 22, 25), Audit 1 (12), Rule 4 (13, 19, 23, 24), Automation 1 (21), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 19, 21, 23.
