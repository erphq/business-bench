# Acceptance checklist: purchase-requests-approvals

Twenty-six binary items: the enterprise baseline (1 to 14, from `docs/build-baseline.md`) and twelve
app items (15 to 26). Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

**This app.** "Restricted" is the Department Approver login for **Denise Harlan** (Transportation); the
read-only role is **Auditor**; the admin is the business office. The fiscal year is 2026-27. Requests
awaiting approval are those Submitted or approved by their department and waiting for the business
office. Budget remaining is the adopted 2026-27 budget minus fully approved requests, exact to the cent.
When an item has the tester create a purchase request without naming its details, create it for
Transportation on account **01-3600-4300** with vendor **Clearview Glass & Glazing LLC**, amount 100.00,
description "Checklist test", submitted and not approved, and delete it (as admin) once the item is
checked; items that approve test requests end by deleting them. Every rerun after a change request
therefore starts from the import figures, except that PO numbers are never reused.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Department Approver creates and edits records in its scope and has no user management or settings; Auditor is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a purchase request and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only the purchase requests of the Transportation department, exactly 30 purchase requests, and cannot open another scope's record by URL.
   How to check: As restricted, read the purchase requests total and open five records to confirm scope. As admin, copy the URL of Technology request PR-27-0067; paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute Technology request PR-27-0067's id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Requests awaiting approval = 34, Budget remaining = 4,555,572.15, Approved this year = 464,927.85, POs issued = 80; after the tester creates one purchase request, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a purchase request in scope of Requests awaiting approval, reload, confirm Requests awaiting approval moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Requests awaiting approval = 7.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Canyon Water Treatment` returns exactly 3 row(s); filtering on Status = Submitted returns 28; sorting by Amount descending puts PR-27-0065 (Curriculum & Instruction, 35,558.00) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 130 data rows and includes the columns Request #, Department, Vendor, Amount, Status, PO Number.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a purchase request, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a purchase request without an account code through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. [Exact] The budget holds exactly **72** lines for 2026-27 (90 file rows minus 12 lines for 2025-26, 4 exact duplicates, and 2 rows repeating a line with its account code written another way), 12 per department, and account code **01-1180-4300** (written `0111804300` and `01.1180.4300` in the file) is one line.
    How to check: As admin, read the total of this year's budget lines, filter by each department, and search for 01-1180-4300. Fail on any other total, any 2025-26 line shown as this year's, or 01-1180-4300 appearing more than once. (90 = all rows; 84 = last year's lines kept; 74 = only exact duplicates removed from this year's rows.)

16. [Exact] The vendors list contains exactly **84** vendors (90 file rows minus 3 exact duplicates and 3 vendors repeated under the same tax ID written without its hyphen), a search for "Gateway Staffing" (also written "Gateway Staffing Inc", tax ID 42-1197693 and 421197693) returns one vendor, and the 6 inactive vendors, such as **Yosemite Bus Sales**, cannot be chosen on a new request.
    How to check: As admin, read the vendors total and run the search; start a new request, open the vendor picker, and search Yosemite Bus Sales (expect it absent or marked not selectable, and refused on save). Fail on any other total, two Gateway Staffing vendors, or a request saved with an inactive vendor.

17. [Exact] Exactly **130** requests were imported, per status Approved **80**, Submitted **28**, Dept Approved (waiting for the business office) **6**, Rejected **16**, and every request is linked to a 2026-27 budget line and a vendor even where the file wrote the account code or department differently.
    How to check: As admin, read the requests total, filter by each status, and filter or sort requests by account and by vendor looking for blanks. Fail on any count that differs or any request without a budget line or vendor.

18. [Exact] The request with an impossible negative amount (**PR-27-0075**, Facilities & Maintenance, Rejected, Amount `-480.00`) was imported and flagged or corrected, not silently kept: the request exists and shows a visible warning, flag, or import-issue entry; or its amount is corrected with the original -480.00 recorded on it or in an import report the admin can open.
    How to check: As admin, open PR-27-0075 and any import summary, log, or issues screen. Fail if it is missing, or shows -480.00 with no warning, flag, note, or issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

19. (CORE) [Exact] Budget remaining is computed per line from approved requests only: **01-3600-4300** (Transportation - Materials & Supplies) shows budget 48,000.00, approved **7,427.75** (PR-27-0012 912.60, PR-27-0015 2,389.40, PR-27-0031 4,125.75), and remaining **40,572.25**, with the Submitted PR-27-0049 (1,840.00) not deducted; and **01-3600-5300** (Transportation - Dues & Memberships) shows remaining **1,234.50**.
    How to check: As admin, open both budget lines (or a budget view listing them). Fail if either remaining figure differs or 38,732.25 (the submitted request deducted) is shown.

20. [Rule] A request under 2,500.00 needs only the department head: a setup request of **2,499.99**, approved by Denise Harlan, is fully approved at once with a PO number, and 01-3600-4300's remaining becomes **38,072.26**.
    How to check: As admin, create the request (amount 2,499.99); as restricted, approve it; as admin, reload the request and the budget line. Fail if it waits for the business office, has no PO number, or the remaining differs. Keep it for item 22.

21. (CORE) [Automation] A request of 2,500.00 or more needs the business office after the department head: a setup request of **2,500.00**, approved by Denise Harlan, waits for the business office with no PO number and 01-3600-4300 still at 38,072.26; after the admin approves it, it is fully approved with a PO number and the line's remaining is **35,572.26**.
    How to check: As admin, create the request; as restricted, approve it; as admin, reload the request and the line, then approve it and reload both again. Fail if the first approval completes it, a PO number or budget deduction appears before the business office approves, or any figure differs. Keep it for item 22.

22. (CORE) [Exact] PO numbers continue the imported sequence in the same format: the item-20 request gets **PO-27-0081** and the item-21 request **PO-27-0082** (the highest imported number is PO-27-0080, although the file also writes numbers as PO27-0057 and PO-27-9), and no number is issued twice. On a rerun after a change request, expect one more than the highest PO number already issued.
    How to check: As admin, read both PO numbers and search the requests for each to confirm it appears once. Fail if the numbers restart, skip, repeat, or take another format (PO-27-0058, which follows the text-sorted PO27-0057, is a fail). Then delete both requests and confirm 01-3600-4300 is back to 40,572.25.

23. [Rule] A request can only be charged to its own department's budget lines: a Transportation request on **01-7700-4300** (a Technology line) is refused.
    How to check: As admin and again as restricted, try to create a Transportation request on 01-7700-4300 (pick it, type it, or replay a create request with that code). Pass only if every attempt is refused with a visible message and no such request exists after reload.

24. [Rule] A request cannot be rejected without a reason, and rejecting leaves the budget untouched.
    How to check: As restricted, reject a setup request with the reason empty (expect refusal; still Submitted after reload), then with the reason "Not budgeted" (expect Rejected). As admin, confirm 01-3600-4300 still shows 40,572.25. Delete the request.

25. [Permission] A department head cannot approve another department's request: Denise Harlan cannot see or approve Technology's **PR-27-0067** (Submitted), including by replaying her approve request.
    How to check: As restricted, search for PR-27-0067 (expect nothing); replay the approve request captured in item 20 with PR-27-0067's id. As admin, reload PR-27-0067. Pass only if it is still Submitted with no department approval recorded.

26. [Permission] Staff see only their own requests and cannot approve them: a Requester invited for Transportation sees only the requests they created, not the other 30 Transportation requests, and cannot approve their own.
    How to check: As admin, invite `tester.requester@example.com` as a Requester in Transportation through the item-3 flow. As that person, create a setup request, then read the requests list (expect exactly that one) and look for an approve control on it; replay Denise Harlan's approve request from item 20 with its id. As admin, confirm it is still Submitted, then delete it and remove the user. Fail if the requester sees any other request or can approve their own.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 4 (5, 6, 25, 26), API 1 (7), Dashboard 2 (8, 9), Exact 8 (10, 11, 15 to 19, 22), Audit 1 (12), Rule 4 (13, 20, 23, 24), Automation 1 (21), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 19, 21, 22.
