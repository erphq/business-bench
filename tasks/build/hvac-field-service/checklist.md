# Acceptance checklist: hvac-field-service

Runs before 13 September 2026 were graded on items 1 to 20 only.

Thirty-one binary items: the original twenty and the enterprise baseline added on 13 September 2026
(items 21 to 31). Each passes only if every stated condition holds; anything else is a fail.
Nine items marked (CORE) define "first usable". Reference numbers come from
`reference/counts.json` (seed 0).

**Setup.** Open `RESULT.json` in the run workspace. "Admin" is `admin.user`; "restricted" is
`restricted.user`, a sales rep login. "The rep" is the rep named in `notes`; if notes do not
say, read the Rep field on the customers the restricted login can see. "Closing a job" means
setting it to the app's closed / completed / done state. Do items in order: 17 to 20 build on
each other.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off (cellular data only), open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Exact] The customers list contains exactly **112** customers (120 file rows minus 5 exact duplicates and 3 same-email-different-case duplicates).
   How to check: As admin, read the total on the customers list, or count rows via export or an unfiltered view. Pass only at exactly 112. (120 = no dedupe; 115 = case-sensitive email dedupe; 107 = the six blank-email customers wrongly collapsed into one.)

4. [Exact] Duplicated customers appear once: a customer search for "Beavercreek Montessori" (exact duplicate, file lines 9 and 73) returns exactly one customer, and a search for "Pamela Brandt" (pamela.brandt@icloud.com / pamela.brandt@ICLOUD.COM, lines 95 and 105) returns exactly one customer.
   How to check: As admin, run both searches. Pass only if each returns exactly one result.

5. [Exact] All six customers whose Email is blank in the file exist as separate customers: Harold Hensley, Judith Fitzgerald, Omar Kaminski, Pamela Grimes, Robert Abernathy, Theresa Gaines.
   How to check: As admin, search each name. Pass only if all six exist, each as its own customer record with an empty email.

6. [Exact] Last Service was imported as a date, not text: sorting customers by Last Service, newest first, puts customer **Marcus Haddad** (file value `2026-09-03`) first and **Irene Ibarra** (file value `9/1/2026`) second.
   How to check: As admin, sort the customers list by Last Service descending, or filter Last Service on or after 2026-09-01 and confirm exactly those two. Fail if the field cannot be sorted or filtered as a date, or a different customer is first (a text sort puts Raymond Duffy, "September 22, 2024", first).

7. [Exact] The parts list contains exactly **60** parts.
   How to check: As admin, read the total on the parts list or count rows with no filter applied. Pass only at exactly 60.

8. [Exact] Currency-string prices ("$2,480.00") were imported as numbers: sorting parts by Sell Price, highest first, puts **CMP-3T-R410A** (2,480.00) first.
   How to check: As admin, sort parts by Sell Price descending. Fail if the sort is unavailable or a different SKU is first (a text sort puts PMP-COND-115 first).

9. [Exact] SKUs with trailing spaces in the file were trimmed: an exact-match search for `IGN-HSI-80V` and for `DISC-60A-NF` (no trailing space) finds each part, and the stored SKU has no trailing space.
   How to check: As admin, filter parts by SKU equals each value; open each part and select or copy the SKU. Fail if either is not found by exact match or the copied value ends with a space.

10. [Exact] The part with negative stock in the file (**FLT-16x25x1**, On Hand -3) was flagged or corrected at import, not silently kept: the part or an import report the admin can open shows a visible warning, flag, or issue entry; or its on-hand is 0 with the original -3 recorded on the part or in the import report.
    How to check: As admin, open FLT-16x25x1 and any import summary, log, or issues screen. Fail if on-hand shows -3 with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

11. (CORE) [Permission] The restricted login sees only the rep's customers, and all of them: exactly **58** if the rep is Dana, **37** if Marcus, **17** if Priya; every visible customer has that rep in its Rep field.
    How to check: Log in as restricted; read the customers total; open at least 5 customers and read the Rep field. Fail on any other count or any customer belonging to another rep.

12. [Permission] The restricted login cannot open another rep's customer by URL.
    How to check: As admin, open a customer whose Rep is not the restricted rep (Beavercreek Montessori is Priya's, Gerald Mensah is Marcus's, Marcus Haddad is Dana's) and copy the browser URL. In a separate session logged in as restricted, paste the URL. Pass only if the page shows an error, not-found, or access-denied, or redirects away, without rendering that customer's name, phone, email, or address.

13. [Permission] The restricted login cannot fetch another rep's customer through the app's API or data endpoint.
    How to check: As restricted, open devtools > Network, load your own customer list and one customer record, and note the request(s) that returned customer data (JSON, REST, GraphQL, or a data-query URL). Copy as cURL and re-issue with the other rep's customer id substituted; also re-issue the list request with any rep or owner filter parameter removed. Pass only if every response is 401, 403, or 404, or contains no other-rep customer (no name, phone, email, or address of one). If every customer screen is server-rendered HTML with no separate data request, this item passes when item 12 passes.

14. [Permission] A technician login sees only the jobs assigned to that technician.
    How to check: As admin, create technician user T (or use a technician login named in `RESULT.json` notes) and a second technician U; create job A assigned to T and job B assigned to U, any customers. Log in as T: the jobs list shows A and not B, and pasting B's URL shows an error or access-denied without B's customer or details. Fail if T can see or open B, or if admin cannot create a technician login at all.

15. [Rule] A job's technician must be an existing technician record; a made-up name cannot be saved as the technician.
    How to check: As admin, edit a job's technician field. Pass if the field is a selection limited to existing technicians, or if typing "Nobody Real" and saving is rejected with a visible message. Fail if "Nobody Real" saves.

16. [Rule] A job cannot be closed without a technician assigned.
    How to check: As admin, create a job with a customer and no technician; attempt to close it. Pass only if the app refuses with a visible message and, after reloading, the job is still not closed; then assign a technician and confirm closing succeeds.

17. (CORE) [Automation] Closing a job creates its invoice automatically, with no separate "create invoice" action.
    How to check: As admin, create a job for any customer, assign a technician, add at least one part line; confirm no invoice exists for the job. Close the job and reload. Pass only if an invoice linked to that job and customer now exists and the tester did nothing other than close the job. Fail if an invoice existed before closing, or a button or second step was needed to create it.

18. [Exact] The invoice total equals parts at sell price x quantity plus labor hours x the hourly rate the tester enters. Job: 2 x CAP-45-5-440 (38.50) + 1 x MTR-COND-14HP (289.00) + 2.5 labor hours at $95.00/hour = 77.00 + 289.00 + 237.50 = **603.50**.
    How to check: As admin, create that job with the rate 95 entered wherever the app takes it (job, invoice, or settings) and tax or discount set to 0 if present; assign a technician; close it; open the created invoice. Pass only if the total is exactly 603.50 and the invoice shows both part lines and the labor amount. Fail if the rate cannot be entered or the total differs by any amount.

19. [Automation] Parts on-hand decrements by the quantity used on a job: **CAP-45-5-440** is 24 after import; after the item-18 job (quantity 2) is closed it shows **22**.
    How to check: Before item 18, read CAP-45-5-440 on-hand (24; if an earlier test changed it, note the value and expect start minus 2). After closing the job, open the part. Pass only if on-hand is exactly 22 (or start minus 2). Fail if unchanged or decremented twice.

20. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After items 17 to 19, ask the operator to restart the app or server (if no operator is available, wait 10 minutes). Then, in a different browser or a private window, log in as admin. Pass only if the customers total is still 112, the item-18 job and its 603.50 invoice are present, and CAP-45-5-440 on-hand is still 22. Fail if any is missing or has reverted to import values.

---

Tags (items 1 to 20): Delivery 2 (1, 2), Exact 9 (3 to 10, 18), Permission 4 (11 to 14), Rule 2 (15, 16), Automation 2 (17, 19), Persistence 1 (20). Core: 1, 3, 11, 17, 20.

## Enterprise baseline (added 13 September 2026)

Items 21 to 31 are items 3 to 13 of the enterprise baseline for build apps, with this app's figures
filled in from `reference/counts.json`. Work them after item 20. The staff role is the sales rep; the
restricted login is the rep named in `notes`, and "another rep's customer" means one whose Rep is not the
restricted rep (Beavercreek Montessori is Priya's, Gerald Mensah is Marcus's, Marcus Haddad is Dana's).
Name any
customer you create `QA ...`, give it a rep other than the restricted rep, and delete it as soon as the
item that created it is done, so that items 3, 11, 24, 27, 28, and 29 read the import values, also on a
rerun. The seed has no jobs or invoices: open jobs and this month's invoiced total start at 0 and 0.00,
and by item 26 they must match the jobs and invoices that items 14 to 19 created.

---

21. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
    How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

22. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
    How to check: Reopen the item-21 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-21 viewer for item 23. Fail on any of the three.

23. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Sales rep creates and edits records in its scope and has no user management or settings; Read-only (the bookkeeper) is read-only, every create, edit, and delete control is absent or rejected.
    How to check: As the item-21 viewer, try to create a customer and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

24. (CORE) [Permission] Row-level scope: the restricted login sees only the rep's customers, exactly 58 (Dana), 37 (Marcus), or 17 (Priya) customers, and cannot open another scope's record by URL.
    How to check: As restricted, read the customers total and open five records to confirm scope. As admin, copy the URL of another rep's customer; paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

25. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
    How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute another rep's customer's id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 23 and 24 pass.

26. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: customers = 112, parts = 60, open jobs = the number of jobs not closed on the jobs list (0 on import), invoiced this month = the sum of this month's invoices on the invoices list (0.00 on import; the 603.50 invoice from item 18 among them); after the tester creates one customer, the affected figure changes accordingly on reload.
    How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a customer in scope of customers, reload, confirm customers moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

27. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: customers = 58 (Dana), 37 (Marcus), or 17 (Priya).
    How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

28. [Exact] The main list has working search, at least one filter, and column sort: searching `Ortega` returns exactly 3 row(s); filtering on Rep = Priya returns 17; sorting by Last Service descending puts Marcus Haddad first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

29. [Exact] Export of the main list to CSV produces exactly 112 data rows and includes the columns Customer, Phone, Email, Service Address, and Rep.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

30. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a customer, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

31. [Rule] Required fields are validated by the server: submitting a customer without a customer name through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

---

Tags (items 21 to 31): Sharing 2 (21, 22), Permission 2 (23, 24), API 1 (25), Dashboard 2 (26, 27), Exact 2 (28, 29), Audit 1 (30), Rule 1 (31). Core: 21, 23, 24, 26. All core items: 1, 3, 11, 17, 20, 21, 23, 24, 26.
