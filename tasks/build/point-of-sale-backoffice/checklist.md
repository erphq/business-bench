# Acceptance checklist: point-of-sale-backoffice

Twenty-six binary items: the enterprise baseline (1 to 14) and this app's items (15 to 26). Each passes
only if every stated condition holds; anything else is a fail. Items marked (CORE) define "first usable".
Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (Owen Brooks, the store manager
for Mill Road), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.
The main list is the daily sales
entries: one per store per trading day (Mill Road is closed on Mondays).

**Words.** Net sales = Gross Sales - Discounts. Cash expected = net sales - Card Sales. Variance = Cash
Counted - cash expected: negative is short, positive is over. Stores are written `Harbor Street`,
`Harbor St`, `HARBOR ST.`, `Mill Road`, `Mill Rd`, and `MILL RD`.

**Test records.** Every figure is for the imported data. Put `QA` in the note of every entry you create,
create test entries for Harbor Street dated 2026-09-01 or later with gross 1,000.00, discounts 0.00, card
1,000.00, and cash counted 0.00 unless an item gives other figures, and delete each test record once the
item that uses it is done. Undo test price changes as item 23 says.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Store manager creates and edits records in its scope and has no user management or settings; Read-only (the bookkeeper) is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a daily sales entry and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only Mill Road's daily sales entries (Owen Brooks's store), exactly 53 daily sales entries, and cannot open another scope's record by URL.
   How to check: As restricted, read the daily sales entries total and open five records to confirm scope. As admin, copy the URL of Harbor Street's 2026-08-15 entry; paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute Harbor Street's 2026-08-15 entry's id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: total net sales = 212,983.94, August 2026 net sales = 105,383.29, August 2026 cash over or short = -42.18, August 2026 days more than 5.00 over or short = 7; after the tester creates one daily sales entry, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a daily sales entry in scope of total net sales, reload, confirm total net sales moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: total net sales = 75,463.45.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Tomasz` returns exactly 7 row(s); filtering on store = Mill Road returns 53; sorting by gross sales descending puts Harbor Street's 2026-08-15 entry (3,612.75) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 115 data rows and includes the columns date, store, gross sales, discounts, card sales, and cash counted.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a daily sales entry, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a daily sales entry without a store through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] Menu items were imported once each with prices as numbers: exactly **57** items (61 file rows minus 2 repeated rows and 2 rows re-typed with a lower-case code, `crs-alm` "Almond Croissant " and `lat-16` "Latte 16 oz"); **51** are sold at both stores (`Both` or `All stores`), **3** at Harbor Street only, **3** at Mill Road only; sorting items by price, highest first, puts **TUM-16** Travel tumbler 16oz (`$28.00`) first.
    How to check: As admin, read the items total; filter or group items by where they are sold; search `CRS-ALM` and `LAT-16` (expect exactly one item each); sort by price descending. Fail on any other count or order. (61 = no dedupe; 59 = codes compared case-sensitively; a text sort puts TST-AVO, `9.50`, first.)

16. [Exact] The impossible price was flagged or corrected at import, not silently kept: **COO-CHO** Chocolate chip cookie has Price `-2.75` in the file. The item exists, and the item or an import report the admin can open shows a visible warning, flag, or issue entry; or the price was corrected with the original value recorded on the item or in the import report.
    How to check: As admin, open COO-CHO and any import summary, log, or issues screen. Fail if the item is missing, or shows a negative price with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

17. [Exact] Modifiers were imported once each and attached through their categories: exactly **32** modifiers in **7** groups (69 file rows, one per modifier per category it applies to, including the re-typed `Oat Milk` and `caramel` rows and one repeated row); Oat milk is **+0.75** (written `+$0.75` and `75c`) and Skim milk is **0.00** (written `free`); **LAT-16** Latte 16oz offers exactly **20** modifiers and **TST-AVO** Avocado toast exactly **5**.
    How to check: As admin, read the modifiers total and groups; open Oat milk and Skim milk; open LAT-16 and TST-AVO (or the modifier picker for each) and count the modifiers offered. Fail on any other count or price. (66 or 69 modifiers = one per row; Oat milk 75.00 = `75c` read as dollars.)

18. [Exact] Daily takings were imported once each with money as numbers and every spelling of a store mapped: July 2026 net sales are Harbor Street **69,330.72** and Mill Road **38,269.93**.
    How to check: As admin, filter the entries to July 2026 and each store (or open a report that shows it) and read net sales. Pass only at both figures (tolerance 0.01). (Mill Road 41,202.60 = its 2026-07-24 and 2026-07-29 rows, each exported twice, counted twice; lower figures = rows written with another spelling of the store left out.)

19. (CORE) [Exact] Every daily entry shows its cash-up: net sales, cash expected, and variance. Harbor Street's **2026-08-04** entry (file: gross `2,395.17`, discounts `51.75`, card `1,987.96`, counted `$344.54`) shows net sales **2,343.42**, cash expected **355.46**, and variance **-10.92** (10.92 short); a new entry with gross 1,850.00, discounts 42.50, card 1,402.30, and cash counted 398.00 shows **1,807.50**, **405.20**, and **-7.20**.
    How to check: As admin, open the 2026-08-04 Harbor Street entry and read the three figures; create a Harbor Street entry for 2026-09-02 with the new figures and a note "QA recount", save, and read them. Pass only if all six figures match (tolerance 0.01; "10.92 short" and "7.20 short" count). Fail if a figure is missing, or the sign says over. Delete the new entry.

20. [Rule] An entry more than 5.00 over or short cannot be saved without an explanation; one exactly 5.00 off can.
    How to check: As restricted, create a Mill Road entry for 2026-09-01 with gross 1,200.00, discounts 0.00, card 900.00, cash counted 292.00 (8.00 short) and no note: expect a visible refusal and no entry after reload. Add the note "QA recount" and save (expect success). Create a Mill Road entry for 2026-09-02 with gross 1,200.00, discounts 0.00, card 900.00, cash counted 305.00 (5.00 over) and no note (expect success). Fail if the 8.00-short entry saves without a note or the 5.00-over entry is refused. Delete both.

21. [Rule] A store has at most one entry per day.
    How to check: As admin, create a Harbor Street entry dated 2026-08-10 (already imported): expect a visible refusal and still one Harbor Street entry for that date after reload. Create a Mill Road entry dated 2026-08-10 (a Monday, when Mill Road has no entry): expect it to save. Fail if the second Harbor Street entry saves or the Mill Road one is refused. Delete the Mill Road entry.

22. [Exact] Item performance for August 2026 across both stores ranks the top five items by net sales: **AMR-16** Americano 16oz **4,511.70** (1,037 sold), **HOT-12** Hot chocolate 12oz **4,296.27** (936), **MOC-16** Mocha 16oz **4,173.63** (672), **CHA-12** Chai latte 12oz **4,031.96** (797), **AMR-12** Americano 12oz **3,679.64** (955).
    How to check: As admin, open the item performance view for August 2026 with both stores and sort by net sales. Pass only if these five appear in this order with these figures (tolerance 0.01). Fail if the view is absent. (MOC-12 first = Harbor Street's August MOC-12 row, exported twice, counted twice; missing items = lower-case codes such as `amr-16` or months written `2026-08` not matched.)

23. (CORE) [Audit] Every price change is recorded with the old price, the new price, who made it, and when, and past sales keep their figures.
    How to check: As admin, with devtools > Network open, change LAT-16 Latte 16oz from 5.25 to 5.50 and save (copy that save request as cURL for item 24); then change it back to 5.25. Open the item's history or the price-change log. Pass only if both changes appear, each with old and new price, the admin user, and a timestamp, and LAT-16's August 2026 item performance still shows Harbor Street 2,294.72 and Mill Road 807.38. Fail if either change is missing a field.

24. [Permission] Only the admin can change prices.
    How to check: As restricted, open LAT-16 and try to change its price (expect no control, or a visible refusal and 5.25 after reload). Replay the item-23 price-change request with the restricted session's cookie or token in place of the admin's. Fail if the price changes by either route or a price-change entry is logged for Owen.

25. [Permission] Signed in as restricted, item performance covers Mill Road only: August 2026's top item is **CHA-16** Chai latte 16oz **2,149.33** (380 sold), followed by **LAT-12** Latte 12oz 1,812.19, and no Harbor Street figure appears.
    How to check: As restricted, open item performance for August 2026. Fail if the top two differ or any Harbor Street figure or combined figure appears.

26. [Permission] A store manager can create and edit entries for his own store only.
    How to check: As restricted, create an entry: the store is fixed to Mill Road, or choosing Harbor Street is refused with a visible message. Create a Mill Road entry for 2026-09-08 with the test figures; in devtools replay its create request with the store changed to Harbor Street and the date to 2026-09-09. Fail if a Harbor Street entry exists after reload as admin. Delete the Mill Road entry.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 5 (5, 6, 24, 25, 26), API 1 (7), Dashboard 2 (8, 9), Exact 8 (10, 11, 15 to 19, 22), Audit 2 (12, 23), Rule 3 (13, 20, 21), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 19, 23.
