# Acceptance checklist: quoting-tool

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items 1 to 14 are the enterprise baseline (`docs/build-baseline.md`); 15 to 26 are this app's. Items
marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

Here "restricted" is Aaliyah Brooks, one of three sales reps (with Jordan Price and Sven Lindqvist). A
quote has one or more lines; `quotes.csv` has one row per line, grouped by Quote No. A line's unit cost
is the product's board feet times the material's cost per board foot plus the product's labor cost;
its margin is (unit price after the quote discount minus unit cost) divided by the unit price after
discount. A quote total is the sum of quantity times unit price, less the quote discount. Dashboard
terms: "Open quotes" counts quotes at Draft or Sent; "Win rate" is won quotes divided by won plus lost
quotes (Expired, Sent, and Draft excluded), tolerance 0.05 percentage points; "Out for decision" totals
Sent quotes; "Won value" totals Won quotes. Margins in this list are accepted within 0.1 points. In
item 8, create the new quote as a Draft owned by Jordan Price and delete it once item 9 is checked, so
later counts are the import values. Do items 23 to 26 in order.

Wrong readings the baseline values rule out: the `Mitchell` search matches Amanda Mitchell's Q-2134
and Q-2204; counting lines instead of quotes gives 216 rows in items 10 and 11; a win rate of 25.0%
divides by all 120 quotes and 39.5% counts Expired as lost; matching the Rep field as written (it
appears as `AALIYAH BROOKS`, `aaliyah brooks`, or with a trailing space) gives Aaliyah 38 quotes
instead of 43.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Sales Rep creates and edits records in its scope and has no user management or settings; Viewer (the bookkeeper) is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a quote and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only quotes owned by Aaliyah Brooks, exactly 43 quotes, and cannot open another scope's record by URL.
   How to check: As restricted, read the quotes total and open five records to confirm scope. As admin, copy the URL of quote Q-2174 (Mateo Parker, Jordan Price's); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute quote Q-2174 (Mateo Parker, Jordan Price's)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Open quotes = 44, Win rate = 45.5%, Out for decision = 147,369.50, Won value = 144,238.70; after the tester creates one quote, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a quote in scope of Open quotes, reload, confirm Open quotes moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Open quotes = 17.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Mitchell` returns exactly 2 row(s); filtering on Status = Won returns 30; sorting by Total descending puts Q-2172 (Yuki Watson, 17,515.00) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 120 data rows and includes the columns Quote No, Customer, Rep, Status, Total.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a quote, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a quote without a customer through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] Products and materials are imported once each: exactly **60** products (64 file rows minus 2 exact duplicates and 2 rows re-keyed as `frm-sb` and `STD-DT84 ` with a trailing space) and exactly **60** materials (62 file rows minus 2 exact duplicates).
    How to check: As admin, read both totals with no filter applied. Pass only at 60 and 60. (62 to 64 products = duplicates or re-keyed rows kept as separate products.)

16. [Exact] Costs written as currency strings were imported as numbers: sorting materials by cost, highest first, puts **MAH-84-FAS** (file value `$18.22`) first, and product SHK-DT72 shows a labor cost of **1,280.00** (file value `$1,280.00`).
    How to check: As admin, sort materials by cost descending, then open SHK-DT72. Fail if the sort is unavailable, another code is first (a text sort puts CHE-44-FAS, `9.60`, first), or the labor cost is blank or 0.

17. [Exact] Quotes were imported as quotes, without duplicated lines, and with the discount applied: exactly **120** quotes, and Q-2165 (Stephanie Rogers, discount `5%`, file lines 116 to 118, where the frm-dr6 line is exported twice) totals **7,153.50**.
    How to check: As admin, read the quotes total and open Q-2165. Pass only at 120 quotes and 7,153.50. (11,224.25 = the duplicated line kept; 7,530.00 = the discount ignored.)

18. [Exact] The negative quantity was flagged at import, not silently accepted: Q-2187 (Westbrook Plumbing, Draft, file line 158) has a STD-DT84 line with quantity `-2`; the quote, the line, or an import report the admin can open shows a visible warning, flag, or issue entry.
    How to check: As admin, open Q-2187 and any import summary, log, or issues screen. Fail if the line shows as ordinary with no warning anywhere in the app. A mention only in `RESULT.json` notes does not count.

19. [Exact] The win rate follows the data: the admin dashboard reads **45.5%** (30 won of 66 decided) and the restricted dashboard **28.6%** (6 of 21); after the admin marks Aaliyah's Sent quote Q-2173 (Brian Hall) as Lost, they read **44.8%** and **27.3%**.
    How to check: Read both dashboards, mark Q-2173 Lost as admin, reload both. Fail if any of the four readings differs or the figure did not move.

20. [Exact] A quote line shows its cost and margin: a new quote with 1 × SHK-DT72 in WAL-84-FAS at 4,250.00 and no discount shows a unit cost of **2,000.28** (44 board feet × 16.37 + 1,280.00) and a margin of **52.93%**.
    How to check: As restricted, create the quote for customer "Line test" and open the line. Fail if the cost or margin is absent or differs (tolerance 0.01 on cost).

21. (CORE) [Rule] No line may be sent below a 30% margin after discount: a quote whose only line is 1 × SHK-DT72 in WAL-84-FAS at 3,000.00 with a 5% discount (net 2,850.00, margin **29.81%**) cannot be sent, and the same quote with no discount (margin 33.32%) can.
    How to check: As restricted, create the quote for customer "Floor test" with a 5% discount and try to send it (expect a visible refusal, and not Sent after reload); set the discount to 0 and send (expect Sent). Fail if the 5% version is sent or the 0% version is refused.

22. [Exact] Imported open quotes below the floor are flagged: exactly **4** open quotes are flagged, Q-2185, Q-2204, Q-2205, and Q-2215. Q-2204 (discount written `0.1`, STD-DT72 line at 34.55% before discount and 27.27% after) must be among them; Q-2192 (its lowest line, SHK-BN48, is 31.53% after its 10% discount) must not.
    How to check: As admin, open the flagged or below-floor list, or filter open quotes on the margin flag. Fail if the set of imported quotes differs. (Missing Q-2204 or Q-2215 = margin computed before discount.)

23. [Rule] A discount over 10% needs the owner's approval before the quote goes out: a quote with 1 × SHK-DT72 in WAL-84-FAS at 4,250.00 and a 12% discount (margin 46.52%) cannot be sent without approval, while the same line with a 10% discount sends.
    How to check: As restricted, create "Discount test" with 12% and try to send (expect a refusal or a pending-approval state, not Sent after reload). Create "Discount test 2" with 10% and send (expect Sent). Fail if the 12% quote is sent or the 10% quote is held.

24. [Permission] Only the admin approves a discount: restricted cannot approve "Discount test"; after the admin approves it, restricted can send it.
    How to check: As restricted, look for an approve control on "Discount test" and use it if present (expect no control, or a rejection and still unapproved after reload). As admin, approve it. As restricted, send it (expect Sent). Fail on any other outcome.

25. (CORE) [Automation] Winning a quote creates its order with no retyping: marking "Conversion test" Won creates an order linked to that quote and customer, with no separate create-order step.
    How to check: As restricted, create "Conversion test" with 1 × SHK-DT72 in WAL-84-FAS at 4,250.00 and 6 × SHK-DC in WAL-44-FAS at 640.00, discount 5%; send it; confirm no order exists; mark it Won and reload. Pass only if an order linked to the quote now exists and the tester did nothing but mark the quote Won. Fail if an order existed earlier or a button or second step was needed.

26. [Exact] The order carries the quote's lines and total, and the won quote is locked: the item-25 order shows both lines and a total of **7,685.50** ((4,250.00 + 6 × 640.00) × 0.95), and the quote's lines can no longer be edited.
    How to check: As admin, open the order, then the quote, and try to change the chair quantity to 4 and save (expect no control, or a rejection and 6 after reload). Fail if the total differs, a line is missing, or the quote edit saves.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 24), API 1 (7), Dashboard 2 (8, 9), Exact 10 (10, 11, 15 to 20, 22, 26), Audit 1 (12), Rule 3 (13, 21, 23), Automation 1 (25), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 21, 25.
