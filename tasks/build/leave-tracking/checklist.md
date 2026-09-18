# Acceptance checklist: leave-tracking

Twenty-six binary items: the enterprise baseline (1 to 14, from `docs/build-baseline.md`) and twelve
app items (15 to 26). Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

**This app.** "Restricted" is the Manager login for **Grace Oduya** (Customer Support); the read-only
role is **Payroll**. Today is taken as 2026-09-13. Leave days are working days from start to end
inclusive, skipping Saturdays, Sundays, and company holidays on their observed date. A manager's team
is the staff whose Manager is that person. When an item has the tester create a leave request without
naming one, create an Annual request for **Anna Green** (Grace Oduya's team, balance 14) for
2026-11-16 to 2026-11-16 at Pending and delete it once the item is checked; items that create requests
end by deleting them, so every rerun after a change request starts from the import figures.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Manager creates and edits records in its scope and has no user management or settings; Payroll is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a leave request and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only the leave requests of Grace Oduya's team (the eight people whose manager is Grace Oduya), exactly 27 leave requests, and cannot open another scope's record by URL.
   How to check: As restricted, read the leave requests total and open five records to confirm scope. As admin, copy the URL of Dmitri Walker's request LR-2026-0132 (Engineering); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute Dmitri Walker's request LR-2026-0132 (Engineering)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Pending requests = 10, Active staff = 40, Annual leave remaining (days) = 492.5, Annual leave days approved in 2026 = 317; after the tester creates one leave request, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a leave request in scope of Pending requests, reload, confirm Pending requests moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Pending requests = 2.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Paul Perez` returns exactly 3 row(s); filtering on Status = Pending returns 10; sorting by Start descending puts James Bennett's request LR-2026-0150 (start 2026-12-28) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 150 data rows and includes the columns Employee, Type, Start, End, Days, Status.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a leave request, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a leave request without a start date through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] Exactly **40** staff are active (60 file rows: 16 former staff with a past End Date, 2 exact duplicates, 2 rows repeating an email in other capitals). **Owen Pratt** (End Date 2026-10-30) is active; **Daniel Kim** is active as E0064, while his 2024 record E0060 (same email, left 2024-06-28) is not; former staff such as Angela Chavez are not active.
    How to check: As admin, read the active staff total and search Owen Pratt, Daniel Kim, and Angela Chavez. Pass only at exactly 40 with Owen Pratt active, exactly one active Daniel Kim (E0064), and Angela Chavez inactive or absent. (60 = all rows; 56 = End Date ignored; 39 = Owen Pratt treated as gone, or Daniel Kim's leaver row kept.)

16. [Exact] Departments and teams were normalised: exactly six departments with active headcounts Operations **5**, Engineering **10**, Customer Support **9**, Sales **7**, Finance **4**, People & Admin **5**, and Grace Oduya's team has **8** people.
    How to check: As admin, list the department values and filter active staff by each; filter staff by manager Grace Oduya. Fail on any extra department value (such as "Eng", "Support", or "People and Admin" as its own department) or any count that differs.

17. [Exact] Balances were imported as numbers and not reduced again by the imported requests: **Susan Parker** has **3** days (file "3 days"); sorting active staff by balance, highest first, puts **Kwame Campbell** (27.5, file "27.5 days") first; and **Mateo Mensah** has **15.5**, his file value, although the file holds approved annual leave for him.
    How to check: As admin, open Susan Parker and Mateo Mensah and sort staff by balance descending. Fail if any balance differs, the sort is unavailable, or another person is first.

18. [Exact] The requests list contains exactly **150** leave requests (153 file rows minus 3 exact duplicates), every one linked to an active person even though Employee ID is written three ways: **Joshua Wright** (E0055, written E0055, 55, and E55) has exactly **6** requests.
    How to check: As admin, read the requests total; open Joshua Wright or filter requests by him; filter or sort requests for a blank employee. Fail on any other total, any request without a person, or a different count for Joshua Wright.

19. [Exact] Status and type were normalised: requests per status are Approved **104**, Pending **10**, Rejected **12**, Cancelled **24**, and per type Annual **115** (including the 24 rows written "Vacation"), Sick **25**, Unpaid **10**.
    How to check: As admin, filter requests by each status and each type. Fail on any count that differs or any extra value such as "Vacation", "approved", or "Canceled" standing on its own.

20. [Exact] The request whose end is before its start (**LR-2026-0131**, Jessica Parker, Start 2026-10-23, End 2026-10-21, Cancelled) was imported and flagged or corrected, not silently kept: it exists and shows a visible warning, flag, or import-issue entry; or its dates are corrected with the original dates recorded on it or in an import report the admin can open.
    How to check: As admin, open LR-2026-0131 and any import summary, log, or issues screen. Fail if it is missing, or shows End before Start with no warning, flag, note, or issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

21. [Exact] Imported requests count working days only: **LR-2026-0149** (Mateo Mensah, 2026-12-21 to 2026-12-31) is **6** days (Dec 24, 25, and 31 are holidays), and **LR-2026-0083** (Luis Haddad, 2026-06-29 to 2026-07-06) is **5** days (Independence Day is observed on Friday July 3).
    How to check: As admin, open both requests and read their day counts. Fail if either differs (LR-2026-0083 at 6 means the Saturday July 4 date was used instead of the observed July 3).

22. (CORE) [Automation] A request goes to the manager and approval takes the days off the balance: an Annual request for **Anna Green** from 2026-10-05 to 2026-10-09 is **5** days and waits as Pending with her balance still **14**; when Grace Oduya approves it, her balance becomes **9**.
    How to check: As admin, create the request and reload: status Pending, 5 days, balance 14. As restricted, find it among the team's requests and approve it; as admin reload Anna Green. Pass only if every figure matches and the balance changed only on approval. Note the approve request in devtools > Network for item 26. Keep the request for item 25.

23. (CORE) [Exact] Holidays are left out of new requests too: an Annual request for Anna Green from 2026-11-23 to 2026-11-27 counts **3** days (Thanksgiving and the day after are holidays), and after Grace Oduya approves it her balance is **6**.
    How to check: As admin, create the request and read its days; approve it as restricted; read Anna Green's balance as admin. Fail if the request shows 5 days or the balance is not 6. Keep the request for item 25.

24. [Rule] Asking for days a teammate is already off shows a warning naming that teammate, without blocking: a request for **Chloe Hughes** (Grace Oduya's team) on 2026-10-14 warns that **Jacob Okafor** is off (LR-2026-0124, approved, 2026-10-13 to 2026-10-14) and still saves as Pending, while a request for **Jonathan Chavez** (Finance) on the same day shows no warning.
    How to check: As admin, create both requests, reading the screen as each is created and as Grace Oduya opens Chloe Hughes's request to approve it. Pass only if the warning names Jacob Okafor for Chloe Hughes, Chloe Hughes's request saves, and no warning appears for Jonathan Chavez. Delete both requests.

25. [Automation] Cancelling approved leave gives the days back, and sick leave never touches the balance: cancelling the item-22 and item-23 requests returns Anna Green's balance to **14**; an approved Sick request for her from 2026-10-19 to 2026-10-20 leaves it at **14**.
    How to check: As admin, cancel the item-22 request and read the balance (expect **11**), then cancel the item-23 request and read it again (expect 14). Create the Sick request, approve it as restricted, and read the balance. Fail if a cancellation does not restore its days or the sick request changes the balance. Delete the three requests.

26. [Permission] A manager cannot approve their own leave or another team's: Grace Oduya cannot approve an Annual request of her own (2026-11-02 to 2026-11-03), and cannot approve Dmitri Walker's **LR-2026-0132** (Engineering, Pending) even by replaying the approve request.
    How to check: As admin, create the request for Grace Oduya. As restricted, try to approve it (expect no control or a refusal); replay the item-22 approve request with LR-2026-0132's id and then with the new request's id. As admin, reload both. Pass only if both are still Pending. Delete Grace Oduya's request.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 26), API 1 (7), Dashboard 2 (8, 9), Exact 10 (10, 11, 15 to 21, 23), Audit 1 (12), Rule 2 (13, 24), Automation 2 (22, 25), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 22, 23.
