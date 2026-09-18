# Acceptance checklist: asset-tracking

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json`
(seed 0). They hold for any test date from 2026-09-01 to 2027-02-28: no imported warranty ends
between 2026-09-01 and 2027-04-30.

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names: Owen Pratt, Boise site manager), and `notes`. Use two browsers or a private window for the
second session. Invitations need no email delivery: the app must show the invite link to the admin.
"Reject" means a visible message and no change after reload. A warranty ends at the purchase date
plus the warranty length (a bare number is months; blank or `none` is no warranty). Asset value is the
purchase cost of every asset not disposed of. When an item has you create an asset without naming
one, create an in-stock Dell P2723DE monitor at Omaha costing 389.00, purchased on the test date with
a 36-month warranty, and delete it once the item is judged, so later counts hold. Do items in order:
18 to 24 build on each other. A rerun after a change request works on the same app: where an earlier
pass already performed an item's action on a named asset (reassigned, disposed), judge the item on the
asset as that pass left it instead of repeating the action.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Site manager creates and edits records in its scope and has no user management or settings; Read-only is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create an asset and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only assets at the Boise site, exactly 42 assets, and cannot open another scope's record by URL.
   How to check: As restricted, read the assets total and open five records to confirm scope. As admin, copy the URL of asset IT-000555 (Denver); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute asset IT-000555 (Denver)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Asset value = 268,866.00, Assets assigned to people = 139, Warranties expired = 154, Assets in stock = 41; after the tester creates one asset, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create an asset in scope of Asset value, reload, confirm Asset value moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Asset value = 51,865.00.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Latitude 7440` returns exactly 19 row(s); filtering on Type = Monitor returns 60; sorting by Purchase Cost descending puts IT-002158 (Dell PowerEdge R760, `$18,450.00`) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 240 data rows and includes the columns Asset Tag, Type, Site, Status, Purchase Cost, Warranty End.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create an asset, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting an asset without Site through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] Asset tags were restored to IT- plus six digits and duplicates collapsed: the register holds exactly 240 assets (250 file rows minus 4 exact duplicate rows and 6 rows repeating an asset under a shortened tag); IT-002955 (`IT-002955` on line 33, `IT-2955` on line 251) and IT-000704 (lines 155 and 231) each appear once; IT-000555, written `000555` in the file, is found by searching `IT-000555` and shows that tag.
    How to check: As admin, read the assets total; search each of the three tags exactly as written here. Pass only at exactly 240, one result per search, and tags displayed in the IT-000000 form. (250 = no dedupe; 246 = only exact duplicates removed.)

16. [Exact] Site names were read from their spellings (`Denver HQ`, `DENVER`, `SLC`, `salt lake city`, `Boise ` with a space, `omaha`): assets per site are exactly Denver 100, Salt Lake City 58, Boise 42, Omaha 40, and asset value per site is Denver 87,544.00, Salt Lake City 78,190.00, Boise 51,865.00, Omaha 51,267.00.
    How to check: As admin, filter assets by each site and read the totals; read the value per site on the dashboard or a report (or total the filtered purchase costs of non-disposed assets). Fail if a fifth site spelling exists, or any count or value differs.

17. [Exact] Warranty ends were computed from four ways of writing the length: IT-001291 (purchased `October 25, 2021`, warranty `24`) ends 2023-10-25; IT-003223 (`06/20/2019`, `36 months`) ends 2022-06-20; IT-003501 (`04/22/2022`, `3 years`) ends 2025-04-22; IT-001030 (`02/23/25`, `5 yr`) ends 2030-02-23.
    How to check: As admin, open the four assets and read the warranty end (or the purchase date and warranty length the app stores, if it shows the end only in lists). Fail if any end date differs or a warranty length was imported as text the app cannot compute from.

18. [Exact] Assignment history is kept in date order across date formats: IT-001053 (Apple MacBook Pro 14, Salt Lake City) shows exactly three assignments, oldest first: Nancy Carter from `February 22, 2021` to `2022-05-07`, Edward Young from `07/17/2022` to `04/22/2023`, and Nadia Lee from `2023-04-23` with no return date, who is its current holder.
    How to check: As admin, open IT-001053's history. Fail if a row is missing (two of them are written with the tag `1053`), the order differs, or the current holder is not Nadia Lee.

19. [Exact] The impossible assignment was flagged, not silently imported: assignments.csv line 149 records IT-000673 (written `IT-673`) assigned to Amanda Wright on `24-Jul-2023` and returned `21-Nov-2021`; the assignment exists in IT-000673's history with a visible warning, flag, or import-issue entry, or is corrected with the original dates recorded on the asset or in an import report the admin can open.
    How to check: As admin, open IT-000673's history and any import summary, log, or issues screen. Fail if the row is missing, or it shows a return before its start with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

20. (CORE) [Automation] Reassigning an asset closes the previous assignment by itself: assigning IT-001053 to Ryan Harris (Salt Lake City) ends Nadia Lee's assignment with the test date as its return date, adds Ryan Harris as the open assignment, and leaves exactly four history rows with one open.
    How to check: As admin, assign IT-001053 to Ryan Harris without editing Nadia Lee's row, then reload its history. Fail if Nadia Lee's assignment is still open or has another return date, two assignments are open, or the history does not have four rows.

21. [Rule] A disposed asset cannot be assigned, and an asset is never held by two people at once: assigning IT-002418 (Disposed, Omaha) is rejected, and replaying the item-20 assign request so that IT-001053 gains a second open assignment for another person leaves it with exactly one open assignment (the replay is rejected, or it closes Ryan Harris's assignment as item 20 did).
    How to check: As admin, try the IT-002418 assignment in the form; copy the item-20 assign request as cURL, change the employee, and re-issue it; reload both assets' histories. Fail if IT-002418 gains an assignment or IT-001053 shows two open assignments.

22. [Automation] The expiry alert lists warranties ending within 60 days, from live data: a new asset whose warranty ends 30 days after the test date appears on it, a new asset whose warranty ends 120 days after the test date does not, and no imported asset appears on it.
    How to check: As admin, create two assets (per Setup, but with purchase dates that make the 36-month warranty end 30 and 120 days after the test date, or with those end dates entered directly if the app takes them); open the alert list or dashboard panel; delete both assets afterwards. Fail if the list is absent, the first asset is missing, the second appears, or any imported asset appears.

23. (CORE) [Rule] Nothing is disposed of while assigned, and laptops need a confirmed wipe first: disposing of IT-003055 (Lenovo ThinkPad T14, Denver, assigned to Cynthia Parker) is rejected; after returning it, disposing of it without confirming a data wipe is rejected; with the wipe confirmed and a disposal date and method given it becomes Disposed.
    How to check: As admin, read the dashboard Asset value (for item 24), attempt each step and reload after each. Fail if the first or second attempt disposes of it, no wipe confirmation exists for a laptop, or the third attempt does not.

24. [Exact] The figures follow the disposal: after item 23 the dashboard Asset value is exactly 1,389.00 lower than the value read at the start of item 23, Denver's asset value is 86,155.00, and IT-003055 cannot be assigned to anyone.
    How to check: As admin, reload the dashboard and the Denver value; try assigning IT-003055. Fail if the value moved by any other amount, Denver's value differs, or the assignment saves.

25. [Permission] A site manager acts only at their own site: signed in as restricted, returning IT-001925 (Dell U3423WE monitor, Boise, assigned to Leila Morris) succeeds; replaying that return request with IT-000555's id (Denver) is rejected; creating an asset with Site set to Denver is rejected or saved at Boise.
    How to check: As restricted, return IT-001925 and copy that request as cURL; re-issue it with IT-000555's id; create an asset choosing Denver if offered (or replay the create with the site changed to Denver); reload as admin. Fail if IT-001925 is still assigned, IT-000555's assignment changed, or an asset created by restricted sits at Denver. Delete the created asset afterwards.

26. [Exact] The expired-warranty list counts only assets you still own that had a warranty: it holds exactly 154 assets, including IT-003469 (Lenovo ThinkPad USB-C Dock, in stock, ended 2020-03-25), and excluding IT-002418 (Disposed, ended 2023-01-21) and IT-004080 (Dell WD19S dock with a blank warranty).
    How to check: As admin, open the expired-warranty list or dashboard drill-down (before item 23 the count is 154; IT-003055's warranty ended 2024-10-23, so after item 23 expect 153). Fail if the count differs (176 = disposed assets included), IT-003469 is missing, or either excluded asset appears.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 25), API 1 (7), Dashboard 2 (8, 9), Exact 10 (10, 11, 15 to 19, 24, 26), Audit 1 (12), Rule 3 (13, 21, 23), Automation 2 (20, 22), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 20, 23.
