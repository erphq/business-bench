# Acceptance checklist: property-maintenance

Twenty-six binary items: the enterprise baseline (1 to 14) and this app's items (15 to 26). Each passes
only if every stated condition holds; anything else is a fail. Items marked (CORE) define "first usable".
Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (Rosa Delgado, the building
manager for Harbor View and Elm Court), and `notes`. Use two browsers or a private window for the second
session. Invitations need no email delivery: the app must show the invite link to the admin.
WR-00449 is
an open request at Northgate Lofts L408, a Tom Becker building outside Rosa's scope.

**Test records.** Every figure is for the imported data. Start the title or description of every record
you create with `QA`, create test work requests at Northgate Lofts unless an item names another building,
and delete each test record (or cancel it where the app has no delete) once the items that use it are
done. Items 21 to 26 build on each other: do them in order and keep QA1 to QA4 until item 26 is done.
"Turn a request into a work order" means the app's accept, convert, or create-work-order action.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Building manager creates and edits records in its scope and has no user management or settings; Read-only (the accountant) is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a work request and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only work requests for Rosa Delgado's buildings (Harbor View and Elm Court), exactly 58 work requests, and cannot open another scope's record by URL.
   How to check: As restricted, read the work requests total and open five records to confirm scope. As admin, copy the URL of work request WR-00449; paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute work request WR-00449's id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: open work requests = 26, estimated cost of open work requests = 21,370.00, vacant units = 12, work requests completed in August 2026 = 15; after the tester creates one work request, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a work request in scope of open work requests, reload, confirm open work requests moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: open work requests = 9.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `dishwasher` returns exactly 6 row(s); filtering on building = Cedar Terrace returns 24; sorting by estimated cost descending puts WR-00447 (6,850.00) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 150 data rows and includes the columns request number, building, unit, category, status, and estimated cost.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a work request, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a work request without a building through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] Units were imported once each into exactly six buildings: exactly **178** units (186 file rows minus 5 repeated rows and 3 rows repeating a unit under another spelling of its building) in exactly **6** buildings: Harbor View 40, Elm Court 24, Northgate Lofts 36, Cedar Terrace 28, Riverside Commons 32, Maple Row Townhomes 18.
    How to check: As admin, open the buildings list (or the building choices on the units list) and read the names; read the units total; filter units by each building. Pass only at 6 buildings with those unit counts and 178 units. (13 buildings = the file's spellings such as "Cedar Ter.", "CEDAR TERRACE", and "Harbor View Apts" kept apart; 186 units = no dedupe.)

16. [Exact] Tenants appear once each: exactly **166** tenants (173 file rows minus 3 repeated rows and 4 rows re-entered with the same email in different capitals, such as `LTANAKA@GMAIL.COM` for Linda Tanaka); the two tenants named **Amy Ortiz** (aortiz@yahoo.com in Harbor View 205, aortiz94@me.com in Riverside Commons 201) remain two separate tenants.
    How to check: As admin, read the tenants total; search "Linda Tanaka" (expect exactly one tenant); search "Amy Ortiz" (expect exactly two, one per unit). Fail on any other count. (170 = case-sensitive email dedupe; 165 = tenants merged by name.)

17. [Exact] Every tenant is attached to their unit even where the file prefixed the unit number, and vacancy follows from it: tenant **Yuki Clark** (file unit `#103`) is the tenant of Harbor View unit 103, and exactly **12** units have no tenant, among them **Elm Court A10** and **Maple Row Townhomes 16**.
    How to check: As admin, open Harbor View unit 103 and confirm Yuki Clark is its tenant; open the vacant units (a filter, list, or the dashboard figure's drill-down) and confirm 12 including the two named units. Fail if Yuki Clark is unlinked or linked to a unit named "#103", or the vacant units differ.

18. [Exact] The impossible lease was flagged or corrected at import, not silently kept: tenant **Luis Carter** (Maple Row Townhomes 14) has Lease Start `01-May-2026` and Lease End `4/30/2026` in the file, an end before its start. The tenant exists, and the tenant or an import report the admin can open shows a visible warning, flag, or issue entry; or the lease end was corrected with the original value recorded on the tenant or in the import report.
    How to check: As admin, open Luis Carter and any import summary, log, or issues screen. Fail if the tenant is missing, or the lease shows an end before its start with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

19. [Exact] Rents and balances were imported as numbers: sorting tenants by monthly rent, highest first, puts **John Hall** (Harbor View 410, file value `$3,100.00`) first, and tenant **Donna Jones** (Harbor View 303, file value `($45.00)`) shows a credit of **45.00** (a balance of -45.00).
    How to check: As admin, sort tenants by rent descending; open Donna Jones. Fail if the sort is unavailable, a different tenant is first (a text sort puts a rent beginning with 2 first), or Donna Jones shows 45.00 owed, 0.00, or a blank balance. If an earlier change-request test charged her, expect -45.00 plus those charges.

20. [Exact] Open requests are counted once each and broken down by building: open work requests are Harbor View **6**, Elm Court **3**, Northgate Lofts **3**, Cedar Terrace **5**, Riverside Commons **6**, Maple Row Townhomes **3** (26 in total). Open means New, Assigned, In Progress, or Waiting on Vendor in any of the file's wordings (`new`, `In progress`, `Waiting - vendor`); `Completed`, `complete`, `Closed`, `Cancelled`, and `Canceled` are not open. Requests exported twice under an unpadded number (`412`, `WR-318`) are the same requests as WR-00412 and WR-00318.
    How to check: As admin, open the dashboard or report that shows open work requests by building and read the six figures. Search requests for `412` and for `318`: no request is numbered exactly `412` or `WR-318`, and WR-00412 and WR-00318 each appear exactly once. Fail if the breakdown is absent or any figure differs. (28 in total = repeated rows counted; 80 = only the exact words Completed and Cancelled treated as closed.)

21. (CORE) [Automation] Turning a work request into a work order creates exactly one work order linked to that request, carrying its building, unit, category, and description, and the request shows it.
    How to check: As admin, create request QA1 at Northgate Lofts unit L101, category Plumbing, description "QA kitchen sink leak". Turn it into a work order and reload. Pass only if exactly one work order exists linked to QA1 with building Northgate Lofts, unit L101, category Plumbing, and that description, and QA1 shows the link or a status saying a work order was issued. Then use the same action on QA1 again: pass only if it is refused or opens the existing work order instead of creating a second one.

22. [Rule] Vendors were imported once each, and a work order can only go to a vendor that does its kind of work: the vendors list has exactly **58** vendors ("Apex Plumbing LLC" and "KEYWAY LOCKSMITHS" in the file are the same vendors as "Apex Plumbing, LLC" and "Keyway Locksmiths"); on QA1's Plumbing work order **Brightline Electric** (Electrical only) cannot be assigned and **Apex Plumbing, LLC** can.
    How to check: As admin, read the vendors total; on QA1's work order try to assign Brightline Electric, then Apex Plumbing, LLC, and reload. Pass only at 58 vendors, if Brightline Electric is absent from the choices or rejected with a visible message, and if Apex Plumbing, LLC stays assigned after reload.

23. [Rule] A vendor whose insurance has expired cannot be assigned: **Summit Pest Solutions** (Pest Control, insurance expired, file value `3/31/2026`) is refused on a Pest Control work order, and **Evergreen Pest Co.** (Pest Control, insured to 2027-06-30) is accepted.
    How to check: As admin, create request QA2 at Northgate Lofts unit L101, category Pest Control, description "QA ants in kitchen"; turn it into a work order; try to assign Summit Pest Solutions, then Evergreen Pest Co., and reload. Pass only if Summit Pest Solutions is absent from the choices or rejected with a visible message, and Evergreen Pest Co. stays assigned after reload.

24. (CORE) [Rule] A work order estimated over 1,500.00 cannot be sent to its vendor or started until the admin approves it, and a building manager cannot approve it; an estimate of exactly 1,500.00 needs no approval.
    How to check: Signed in as restricted, create request QA3 at Harbor View unit 101, category Plumbing, description "QA water heater replacement"; turn it into a work order with estimated cost 2400 and vendor Apex Plumbing, LLC; try to move it to the app's sent, scheduled, or in-progress state. Pass only if that is refused with a visible message and Rosa has no working approve control. As admin, approve QA3's work order; as restricted, move it forward (expect success). As restricted, create QA4 the same way with estimated cost 1500 and move it forward (expect success with no approval). Fail if QA3 moves before approval, Rosa can approve it, or QA4 is held for approval.

25. [Automation] Completing a work order completes its request, and the open figure follows: completing QA1's work order with actual cost 185.00 sets QA1 to completed, and the dashboard's open work requests drops by exactly one.
    How to check: As admin, read the dashboard's open work requests; open QA1's work order, mark it completed with actual cost 185.00, and reload both the request and the dashboard. Pass only if QA1 shows completed (or the app's closed equivalent) without anyone editing QA1 itself, and the figure is exactly one lower. Fail if QA1 stays open or the figure does not move.

26. [Permission] Rosa's scope covers units, tenants, and work orders as well: signed in as restricted she sees exactly **64** units and **61** tenants, all in Harbor View or Elm Court, and no work order from another building.
    How to check: As restricted, read the units and tenants totals and open three of each. Open the work orders list and confirm QA1 and QA2 (Northgate Lofts) are absent; as admin copy the URL of QA2's work order and paste it in the restricted session. Pass only at 64 units and 61 tenants, no record from another building, and an error, not-found, or redirect for QA2's work order. Then delete QA1 to QA4.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 26), API 1 (7), Dashboard 2 (8, 9), Exact 8 (10, 11, 15 to 20), Audit 1 (12), Rule 4 (13, 22 to 24), Automation 2 (21, 25), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 21, 24.
