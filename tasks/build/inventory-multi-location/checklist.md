# Acceptance checklist: inventory-multi-location

Twenty-six binary items: the enterprise baseline (1 to 14, from `docs/build-baseline.md`) and twelve
app items (15 to 26). Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

**This app.** "Restricted" is the Warehouse Lead login for **Marisol Vega** (Sacramento); the read-only
role is **Bookkeeper**. A stock item is one item held at one warehouse, with its on-hand quantity and
reorder point. Inventory value is on-hand times unit cost summed over stock items, exact to the cent. A
stock item needs reordering when its on-hand is at or below its reorder point. When an item has the
tester create a stock item without naming one, create **01354 Dish detergent manual 4x1 gal** at
**Stockton** (not stocked there) with on-hand 0 and reorder point 5, and delete it once the item is
checked; items that move or adjust imported stock end by reversing the movement. Every rerun after a
change request therefore starts from the import figures.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Warehouse Lead creates and edits records in its scope and has no user management or settings; Bookkeeper is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a stock item and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only the stock items in the Sacramento warehouse, exactly 79 stock items, and cannot open another scope's record by URL.
   How to check: As restricted, read the stock items total and open five records to confirm scope. As admin, copy the URL of the Reno stock item for 26988 Grill brick 12/cs; paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute the Reno stock item for 26988 Grill brick 12/cs's id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Reorder alerts = 29, Inventory value = 1,604,780.55 (1,604,713.75 also passes while the stock item flagged in item 19 still carries -4), Reno inventory value = 592,188.90, Items = 100; after the tester creates one stock item, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a stock item in scope of Reorder alerts, reload, confirm Reorder alerts moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Reorder alerts = 8.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `burnisher` returns exactly 3 row(s); filtering on Warehouse = Stockton returns 65; sorting by On Hand descending puts the Reno stock item for 67331 Straw wrapped jumbo 12x250 (1,450) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 231 data rows and includes the columns Item #, Description, Warehouse, On Hand, Reorder Point.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a stock item, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a stock item without a warehouse through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] The items list contains exactly **100** items (106 file rows minus 4 exact duplicate rows and 2 rows repeating an item number with a trailing space and the description in capitals).
    How to check: As admin, read the total on the items list, or count rows via export or an unfiltered view. Pass only at exactly 100. (106 = no dedupe; 102 = exact duplicate rows only.)

16. [Exact] Item numbers keep their leading zeros and link to stock rows written without them: item **01038 Floor machine 17in 175rpm** is listed as `01038` and shows stock at all three warehouses, Reno **12**, Sacramento **9**, Stockton **3** (the file's Reno row reads `1038`); no item numbered `1038` exists and no stock item lacks an item.
    How to check: As admin, search items for 01038 and open it; search items for 1038 and expect only 01038; filter or sort stock items for a blank item. Fail if the number shows as 1038, any of the three on-hand figures differs, a separate 1038 item exists, or any stock item has no item.

17. [Exact] Warehouse names were normalised and duplicate stock rows merged: there are exactly **231** stock items (236 file rows minus 5 exact duplicates), the warehouse field has exactly three values, Reno, Sacramento, and Stockton, and they hold Reno **87**, Sacramento **79**, and Stockton **65** stock items.
    How to check: As admin, open the warehouse filter or field and list its values, then filter the stock list by each warehouse. Fail on any extra value (such as RNO, SAC, "Stockton ", or "Reno NV") or any count that differs.

18. [Exact] Unit costs written as currency strings were imported as numbers: sorting items by Unit Cost, highest first, puts **54286 Auto scrubber 20in battery** (`$3,480.00`) first.
    How to check: As admin, sort items by Unit Cost descending. Fail if the sort is unavailable or another item is first (a text sort puts 17605 Floor stripper 5 gal, 96.50, first).

19. [Exact] The stock item with an impossible negative on-hand (**36362 Wet floor sign at Stockton**, On Hand -4) was flagged or corrected at import, not silently kept: the stock item or an import report the admin can open shows a visible warning, flag, or issue entry; or its on-hand is 0 with the original -4 recorded on the stock item or in the import report.
    How to check: As admin, open that stock item and any import summary, log, or issues screen. Fail if on-hand shows -4 with no warning, flag, note, or issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

20. [Exact] The reorder list holds exactly the stock items at or below their reorder point: **29** entries, including **26445 Portion cup 2oz 2500/cs at Reno** (on-hand 12, reorder point 12) and not **38987 Foam cup 12oz 1000/cs at Reno** (on-hand 13, reorder point 12).
    How to check: As admin, open the reorder list and count its entries; look for both stock items. Fail on any other count, if the Portion cup is missing, or if the Foam cup is listed. (22 = only stock items strictly below the point.)

21. (CORE) [Automation] A transfer moves stock between warehouses as one action: transferring 10 of **11493 Hand sanitizer gel 4x1000ml** from Reno (on-hand 48) to Sacramento (on-hand 6) leaves Reno at **38** and Sacramento at **16**, records one transfer showing the item, quantity, both warehouses, the user, and the date, and leaves the inventory value unchanged.
    How to check: As admin, read both on-hand figures and the dashboard inventory value; create the transfer; reload. Pass only if Reno reads 38, Sacramento 16, the transfer record shows all six details, and the inventory value is exactly what it was. Fail if either side was not updated or had to be edited separately. Then transfer 10 back from Sacramento to Reno and confirm 48 and 6.

22. [Rule] A transfer cannot send more than the source warehouse holds.
    How to check: As admin, try to transfer 49 of 11493 Hand sanitizer gel 4x1000ml from Reno (on-hand 48) to Sacramento. Pass only if the app refuses with a visible message and, after reload, Reno still reads 48 and Sacramento 6.

23. [Rule] A stock adjustment cannot be saved without a reason.
    How to check: As admin, adjust **53397 Scrub sponge 20/cs at Reno** (on-hand 45) by -3 with the reason left empty and save. Pass only if the save is refused with a visible message and on-hand still reads 45 after reload. Fail if the adjustment saves or if the app has no way to enter a reason at all.

24. (CORE) [Exact] An adjustment with a reason changes on-hand and value exactly and is kept in the stock item's history: -3 of **53397 Scrub sponge 20/cs at Reno** (unit cost 18.40) with reason Damaged takes on-hand from 45 to **42** and lowers the inventory value and the Reno inventory value by exactly **55.20** (1,604,780.55 to **1,604,725.35**; 592,188.90 to **592,133.70**), and the history shows the quantity, the reason, the user, and the time.
    How to check: As admin, read the two dashboard values, save the adjustment with reason Damaged, reload, and read on-hand, both values, and the stock item's history. Pass only if all four conditions hold. Then adjust +3 with reason Count correction and confirm on-hand 45 and both values restored.

25. [Automation] The reorder list updates by itself: adjusting **04088 Degreaser heavy duty 4x1 gal at Reno** from 15 to 12 (reorder point 12) adds it to the reorder list and raises the reorder alerts figure from 29 to **30** with no other action; adjusting it back to 15 removes it and the figure returns to 29.
    How to check: As admin, adjust by -3 with reason Count correction, reload the reorder list and the dashboard; then adjust by +3 with the same reason and reload both. Fail if the stock item does not appear after the first adjustment, still appears after the second, or the figure does not move with it.

26. [Permission] The restricted login changes only Sacramento stock: Marisol Vega can transfer out of Sacramento, but a transfer out of Reno and an adjustment to a Reno stock item are refused, on screen and when the request is replayed.
    How to check: As restricted, transfer 1 of 11493 Hand sanitizer gel 4x1000ml from Sacramento to Reno and note the request in devtools > Network; as admin confirm Sacramento 5 and Reno 49. As restricted, try the same transfer with Reno as the source, first in the form and then by replaying the noted request with the source warehouse changed to Reno; try to adjust any Reno stock item the same way. Pass only if both Reno actions are refused (no control, or a rejection) and, as admin after reload, Reno still reads 49. Finally, as admin, transfer 1 from Reno back to Sacramento.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 26), API 1 (7), Dashboard 2 (8, 9), Exact 9 (10, 11, 15 to 20, 24), Audit 1 (12), Rule 3 (13, 22, 23), Automation 2 (21, 25), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 21, 24.
