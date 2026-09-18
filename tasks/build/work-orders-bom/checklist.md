# Acceptance checklist: work-orders-bom

Twenty-six binary items: the enterprise baseline (1 to 14) and this app's items (15 to 26). Each passes
only if every stated condition holds; anything else is a fail. Items marked (CORE) define "first usable".
Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (Sam Whitaker, the supervisor of
Line 2 - Carts), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.
WO-3164 is an in-progress
SNK-1C18 work order on Line 1 - Tables, Dale Pruitt's line, outside Sam's scope.

**Words.** Part numbers are six digits; the files sometimes drop the leading zeros (`1040` is 001040).
Lines are written `Line 2 - Carts`, `Line 2`, `L2`, or `Carts` (likewise for Lines 1 and 3). Open means
Planned (`planned`), Released (`Rel.`), or In Progress (`WIP`); Completed also appears as `Complete` or
`Closed`, and Cancelled as `Void`. A product's material cost is the sum over its BOM of quantity per unit
times the component's unit cost; WIP value is the sum over in-progress work orders of quantity times the
product's material cost.

**Test records.** Every figure is for the imported data. Start the notes or reference of every work order
you create with `QA`, create test work orders on Line 1 - Tables for product TBL-3048 unless an item says
otherwise, and delete each one once the items that use it are done. Items 21 to 25 build on each other:
do them in order and read the dashboard's WIP value where they say so. Stock figures in items 21, 22,
and 24 are import values; on a rerun after an earlier run moved stock, read the before-values and expect
the stated differences.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Line supervisor creates and edits records in its scope and has no user management or settings; Read-only (the accountant) is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a work order and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only work orders on Line 2 - Carts, Sam Whitaker's line, exactly 35 work orders, and cannot open another scope's record by URL.
   How to check: As restricted, read the work orders total and open five records to confirm scope. As admin, copy the URL of work order WO-3164; paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute work order WO-3164's id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: open work orders = 18, work orders in progress = 9, WIP value = 65,174.24, parts below reorder point = 6; after the tester creates one work order, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a work order in scope of open work orders, reload, confirm open work orders moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: open work orders = 9.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `SHF-DUN-2036` returns exactly 3 row(s); filtering on line = Line 3 - Shelving returns 23; sorting by quantity descending puts WO-3103 (120) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 84 data rows and includes the columns work order number, product, quantity, line, status, and due date.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a work order, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a work order without a product through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] Parts were imported once each under their six-digit numbers: exactly **88** parts, **68** components and **20** finished goods (93 file rows minus 3 repeated rows and 2 rows repeating a part under the other form of its number, `2032` / `002032` and `2041` / `002041`); a part written `1021` in the file is stored as **001021**; part **003010** (file value `2,400`) has **2,400** on hand.
    How to check: As admin, read the parts total and the component and finished-good counts (filter by type if needed); search `2032` and confirm exactly one part, numbered 002032; open 001021 and 003010. Fail on any other total, any part numbered `2032`, `2041`, or `1021`, or 003010 showing 2 or 2.4 on hand.

16. [Exact] Bills of materials were imported line by line without doubling: all 20 finished goods have a BOM, and **CRT-BUS-3S** has exactly **11** component lines, including **001040 x 4** (written `1040` in the file) and **003010 x 24** (a line the file repeats); **TBL-2448**'s 003010 line, also repeated, reads **8**. (168 BOM lines in all: 173 file rows minus 4 repeated lines and the unknown-part line of item 17.)
    How to check: As admin, open CRT-BUS-3S's BOM and count its lines; read the 001040 and 003010 quantities; open TBL-2448's BOM and read 003010. Fail if CRT-BUS-3S has other than 11 lines, 003010 shows 48 or appears twice, 001040 is missing, or TBL-2448 shows 16.

17. [Exact] The BOM line that points at an unknown part was flagged, not silently dropped or quietly turned into a part: SHF-WALL-36's BOM in the file lists component `9950` "Wall anchor kit", which is not in the parts list. SHF-WALL-36's BOM, the product, or an import report the admin can open shows a visible warning, flag, or issue entry naming 9950 or Wall anchor kit.
    How to check: As admin, open SHF-WALL-36 and any import summary, log, or issues screen. Fail if its BOM shows its 4 known lines with no trace of the missing part anywhere, or a part 009950 exists with no flag. A mention only in `RESULT.json` notes does not count.

18. [Exact] Material cost rolls up from the BOM at the parts' unit costs: CRT-BUS-3S costs **276.16** per unit (0.75 x 165.28 + 4 x 11.88 + 2 x 11.16 + 2 x 10.90 + 1 x 20.00 + 2 x 11.09 + 24 x 0.16 + 24 x 0.08 + 8 x 0.36 + 1 x 8.78 + 1 x 0.96).
    How to check: As admin, open CRT-BUS-3S's material cost, cost roll-up, or standard cost. Pass only at 276.16 (tolerance 0.01). Fail if no such figure exists for the product. (280.00 = the repeated 003010 line counted twice.)

19. [Exact] Work orders were imported once each with their status words mapped: exactly **84** work orders (87 file rows: WO-3174 and WO-3123 repeated, and WO-3131 also exported as `3131`): Planned **4**, Released **5**, In Progress **9**, Completed **64**, Cancelled **2**.
    How to check: As admin, filter work orders by each status and read the counts; search `3131` and confirm exactly one work order, WO-3131. Fail on any other count or a work order numbered `3131`. (In Progress 10 = the repeated WO-3174 row counted.)

20. [Exact] The work order due before it starts was flagged or corrected at import, not silently kept: **WO-3181** (SHF-2460-4T, Planned) has Start Date `2026-09-20` and Due Date `9/17/2026` in the file. The work order or an import report the admin can open shows a visible warning, flag, or issue entry; or the date was corrected with the original value recorded on the work order or in the import report.
    How to check: As admin, open WO-3181 and any import summary, log, or issues screen. Fail if it is missing, or shows a due date before its start with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

21. (CORE) [Rule] A work order cannot start while any component is short, and the refusal names the shortage: CRT-2436-2S x 24 needs **48** of **002010** Caster 5in swivel with brake, and **40** are on hand, **8** short; every other component is sufficient.
    How to check: As admin, create QA1 for CRT-2436-2S, quantity 24, on Line 2 - Carts; release it if the app requires that first; try to start it. Pass only if the start is refused with a visible message or availability view naming 002010 (or Caster 5in swivel with brake) and the shortfall (8, or 48 needed against 40 on hand), and after reload QA1 is not in progress and 002010 still shows 40. Then delete QA1.

22. [Automation] Starting a work order takes its components out of stock exactly once: starting QA2 for **SHF-2448-4T x 10** moves 001050 from **574** to **534**, 002031 **492** to **452**, 002040 **2,057** to **1,897**, 002021 **777** to **737**, 005011 **358** to **348**, and 005030 **1,066** to **1,056**.
    How to check: Read the dashboard's WIP value (W0) and the six parts' on-hand figures. As admin, create QA2 for SHF-2448-4T, quantity 10, on Line 3 - Shelving, and start it. Reload the six parts twice. Pass only at the stated after-values (differences 40, 40, 160, 40, 10, 10) with QA2 in progress. Read the dashboard's WIP value again (W1).

23. [Rule] A work order cannot be completed before it has started, or for more than its quantity.
    How to check: As admin, create QA3 for SHF-2448-4T, quantity 5, on Line 3 - Shelving, and without starting it try to complete it (expect a visible refusal and QA3 not completed after reload). On QA2 (in progress, quantity 10) try to complete 12 (expect a visible refusal). Pass only if both are refused and SHF-2448-4T's on hand is unchanged. Delete QA3.

24. (CORE) [Automation] Completing a work order puts the finished units into stock without moving its components again: completing QA2 with quantity 10 raises SHF-2448-4T from **22** to **32** on hand, and the six item-22 components keep their item-22 after-values.
    How to check: As admin, complete QA2 with quantity 10 and do nothing else. Reload SHF-2448-4T and the six components. Pass only if SHF-2448-4T shows 32 and the components are unchanged since item 22, and QA2 shows completed. Read the dashboard's WIP value again (W2).

25. [Exact] The WIP value follows the work: W0 = **65,174.24** (the import value), W1 = **67,015.84** (W0 plus 10 x 184.16, SHF-2448-4T's material cost), and W2 = **65,174.24**.
    How to check: Compare the three readings from items 22 and 24 (tolerance 0.01). Fail if any differs. (68,266.24 at W0 = the repeated WO-3174 row counted.) Then delete QA2.

26. [Permission] A line supervisor can change work orders on his line only, and cannot change bills of materials or part costs.
    How to check: As admin, create QA4 for DOL-1818, quantity 1, on Line 2 - Carts, and QA5 for TBL-3048, quantity 1, on Line 1 - Tables. As restricted: change QA4's quantity to 2 and save (expect success after reload); paste QA5's URL copied from the admin session (expect an error, not-found, or redirect without its details); open CRT-BUS-3S's BOM and try to change a quantity, and open 003010 and try to change its unit cost (expect no control, or a visible rejection and no change after reload). Fail if any of the four differs. Then delete QA4 and QA5 as admin.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 26), API 1 (7), Dashboard 2 (8, 9), Exact 9 (10, 11, 15 to 20, 25), Audit 1 (12), Rule 3 (13, 21, 23), Automation 2 (22, 24), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 21, 24.
