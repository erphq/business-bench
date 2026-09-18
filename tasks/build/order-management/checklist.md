# Acceptance checklist: order-management

Twenty-six binary items: the enterprise baseline (1 to 14, from `docs/build-baseline.md`) and twelve
app items (15 to 26). Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

**This app.** "Restricted" is the Account Manager login for **Jonah Whitaker**; the read-only role is
**Finance**. Open orders are orders at New, Paid, or Packed (plus Backordered or On hold where the app
has those states). Shipped sales is the sum of order totals of Shipped and Delivered orders. An order
total is goods + shipping + tax, with tax on goods only, rounded to the cent. When an item has the
tester create an order without naming one, create it for retail customer **Amanda Bennett** with 1 x
BLK-ASSAM-4OZ at New and delete it (as admin) once the item is checked; items that ship test orders
end by deleting them and setting the stock figures they changed back. Every rerun after a change
request therefore starts from the import figures.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Account Manager creates and edits records in its scope and has no user management or settings; Finance is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a sales order and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only the sales orders of the wholesale customers Jonah Whitaker manages, exactly 16 sales orders, and cannot open another scope's record by URL.
   How to check: As restricted, read the sales orders total and open five records to confirm scope. As admin, copy the URL of order #1008 (Evergreen Health Foods, a Priya Raman customer); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute order #1008 (Evergreen Health Foods, a Priya Raman customer)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Open orders = 34, Shipped sales = 24,338.27, Sales tax on shipped orders = 771.87, Average shipped order = 368.76; after the tester creates one sales order, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a sales order in scope of Open orders, reload, confirm Open orders moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Open orders = 3.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Brick Oven Collective` returns exactly 2 row(s); filtering on Status = Paid returns 12; sorting by Order Total descending puts order #1014 (Stonebridge Cafe, 2,614.62) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 110 data rows and includes the columns Order #, Customer, Status, Order Date, Total.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a sales order, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a sales order without a customer through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] The customers list contains exactly **142** customers (150 file rows minus 5 exact duplicate rows and 3 rows repeating an email in different capitals), and both Maria Lopez customers exist (maria.lopez@gmail.com and mlopez.tea@outlook.com).
    How to check: As admin, read the customers total; search "Maria Lopez" and expect two customers; search "Charles Murphy" (charles.murphy83@yahoo.com and CHARLES.MURPHY83@YAHOO.COM in the file) and expect one. Pass only at exactly 142 with both searches as stated. (150 = no dedupe; 145 = exact rows only; 141 = the two Maria Lopez customers merged.)

16. [Exact] Customer type, account manager, and resale certificate were normalised: exactly **38** wholesale and **104** retail customers; Jonah Whitaker manages **14**, Priya Raman **13**, and Carlos Mendes **11** wholesale customers; **27** wholesale customers are tax-exempt, and Cedar Grove Gift Shop (certificate written "Expired") is not.
    How to check: As admin, filter customers by type, by account manager, and by tax-exempt or certificate status, and open Cedar Grove Gift Shop. Fail on any count that differs, any extra type or manager value (such as "wholesale " or "jonah whitaker" as its own value), or Cedar Grove Gift Shop marked exempt.

17. [Exact] The products list contains exactly **60** products (64 file rows minus 3 exact duplicates and OOL-MILK-2OZ repeated with a trailing space), and prices written as currency strings are numbers: sorting products by retail price, highest first, puts **MAT-CERMON-1LB** (`$148.00`) first.
    How to check: As admin, read the products total and sort by retail price descending. Fail at any other total, if OOL-MILK-2OZ appears twice, or if another product is first (a text sort puts WHT-SILVER-1LB, 96.00, first).

18. [Exact] The product with impossible negative stock (**HRB-PEPMNT-2OZ**, Stock -2) was flagged or corrected at import, not silently kept: the product or an import report the admin can open shows a visible warning, flag, or issue entry; or its stock is 0 with the original -2 recorded on the product or in the import report.
    How to check: As admin, open HRB-PEPMNT-2OZ and any import summary, log, or issues screen. Fail if stock shows -2 with no warning, flag, note, or issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

19. [Exact] Order lines were grouped into exactly **110** orders (219 file lines; "#1006" and "1006" are the same order): order **#1006** (Marigold Kitchen) has exactly 3 lines, and the orders per status are New **16**, Paid **12**, Packed **6**, Shipped **14**, Delivered **52**, Cancelled **10**.
    How to check: As admin, read the orders total, open #1006 and count its lines, then filter by each status. Fail on any other total, a second order numbered 1006, fewer lines on #1006, any extra status value (such as "Canceled" or "delivered" as its own status), or any count that differs.

20. [Exact] Imported orders keep what was charged and did not move stock: order #1006 shows goods **1,411.20**, shipping **15.00**, tax **0.00**, and total **1,426.20**; the dashboard shipped sales is not 62,717.09 (order totals added once per line); and **HRB-HIBISC-4OZ** shows stock **91**, its file value.
    How to check: As admin, open #1006, the dashboard, and HRB-HIBISC-4OZ. Fail if #1006 shows a multiple of its total, shipped sales reads 62,717.09, or HRB-HIBISC-4OZ reads 32 (the file stock minus the 59 units on imported shipped and delivered orders) or any value other than 91.

21. (CORE) [Exact] Retail order totals follow the shipping threshold and tax rule. Order R1 for Amanda Bennett, 2 x BLK-ASSAM-4OZ (18.00) + 1 x OOL-TIEGUA-4OZ (24.50): goods **60.50**, shipping **7.95**, tax **4.99**, total **73.44**. Order R2 for Amanda Bennett, 4 x BLK-ASSAM-4OZ + 1 x OOL-TIEGUA-4OZ: goods **96.50**, shipping **0.00**, tax **7.96**, total **104.46**.
    How to check: As admin, create both orders at New and open each. Pass only if all eight figures match exactly (a figure the app does not show separately passes if the total matches and the other shown figures do). Keep R1 for item 23; delete R2.

22. [Exact] Wholesale order totals use the wholesale price, flat shipping, and the certificate. For **Blue Door Cafe** (certificate on file), 12 x BLK-ASSAM-4OZ at 10.80: goods **129.60**, shipping **15.00**, tax **0.00**, total **144.60**. For **Cedar Grove Gift Shop** (certificate Expired), the same line: goods 129.60, shipping 15.00, tax **10.69**, total **155.29**.
    How to check: As admin, create both orders at New, open each, then delete both. Fail if either uses the retail price, applies retail shipping, taxes Blue Door Cafe, or leaves Cedar Grove Gift Shop untaxed.

23. (CORE) [Automation] Stock comes off when an order ships, and only once: moving R1 through Paid and Packed leaves BLK-ASSAM-4OZ at 40 and OOL-TIEGUA-4OZ at 15; marking it Shipped takes them to **38** and **14**; marking it Delivered and saving it again changes nothing further.
    How to check: As admin, read both stock figures after each of Paid, Packed, Shipped, Delivered, and a re-save, reloading each time. Pass only if the figures are 40 and 15 until Shipped and 38 and 14 from then on. Then delete R1 and set the two stock figures back to 40 and 15.

24. [Rule] An order the stock cannot cover is backordered and cannot ship: an order for Amanda Bennett of 5 x **WHT-SILVER-1LB** (stock 3) shows as backordered, and marking it Shipped is refused with stock still 3; after the admin raises that product's stock to 10, the order ships and stock reads **5**.
    How to check: As admin, create the order, read its status, try to mark it Shipped, reload, and read the stock; set the stock to 10 and ship the order. Fail if it ships at stock 3, stock goes negative, or nothing marks it as backordered. Then delete the order and set the stock back to 3.

25. [Rule] The status flow holds: a shipped order cannot be cancelled, and an order cannot be marked Delivered before it has shipped.
    How to check: As admin, open imported order **#1001** (Shipped), set it to Cancelled, and save; then create a setup order at New and set it straight to Delivered. Pass only if both changes are refused with a visible message and, after reload, #1001 is still Shipped and the new order is not Delivered. Delete the new order.

26. [Permission] The restricted login's customers are exactly Jonah Whitaker's: it sees **14** customers, all wholesale and all his; retail customers such as Amanda Bennett are not visible; and the customer picker on a new order offers only those 14.
    How to check: As restricted, read the customers total and open five; search "Amanda Bennett" (expect nothing); start a new order, open the customer picker, and search "Evergreen Health Foods" (expect nothing). Fail on any other total, any retail or other-manager customer, or a picker that offers one. Cancel the new order without saving.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 26), API 1 (7), Dashboard 2 (8, 9), Exact 10 (10, 11, 15 to 22), Audit 1 (12), Rule 3 (13, 24, 25), Automation 1 (23), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 21, 23.
