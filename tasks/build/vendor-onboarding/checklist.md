# Acceptance checklist: vendor-onboarding

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items 1 to 14 are the enterprise baseline (`docs/build-baseline.md`); 15 to 26 are this app's. Items
marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

Here "restricted" is Rosa Delgado, category manager for Ingredients and Packaging. The other managers
are Dev Malhotra (Logistics), Mei Chen (Facilities), and Tom Okafor (IT & Services). Dashboard terms:
"Vendors in onboarding" counts vendors at stage New, Documents, or Review; "Insurance alert" counts
approved vendors whose Certificate of Insurance has expired or expires within 30 days of today. Every
insurance expiry in the seed is on or before 2026-08-28 or in 2028, so the figures below hold for any
test date from 2026-09-01 to 2027-12-01. In item 8, create the new vendor in the Facilities category
(stage New) and delete it once item 9 is checked, so later counts are the import values. Do items 20
to 23 in order: they walk one vendor through the stages.

Wrong readings the baseline values rule out: in item 10 the `Lakeshore` search matches Lakeshore Flour
Mills and Lakeshore Sugar Refining (3 rows means the re-entered duplicate was kept); the Packaging
filter returns 17 when rows written `PACKAGING` or `Packaging ` are not matched; a text sort on Annual
Spend puts Cold Chain Transport Inc. (`97691.25`) first. In item 6, matching the category as written
gives Rosa 41 vendors instead of 54.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Category Manager creates and edits records in its scope and has no user management or settings; Viewer (accounts payable) is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a vendor and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only the Ingredients and Packaging categories (Rosa Delgado's), exactly 54 vendors, and cannot open another scope's record by URL.
   How to check: As restricted, read the vendors total and open five records to confirm scope. As admin, copy the URL of Highway 30 Carriers (V-0088, Logistics); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute Highway 30 Carriers (V-0088, Logistics)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Vendors in onboarding = 50, Approved vendors = 58, Insurance alert = 6, Annual spend with approved vendors = 8,648,502.69; after the tester creates one vendor, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a vendor in scope of Vendors in onboarding, reload, confirm Vendors in onboarding moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Vendors in onboarding = 24.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Lakeshore` returns exactly 2 row(s); filtering on Category = Packaging returns 22; sorting by Annual Spend descending puts Copper Kettle Grain Co. (file value `$479,615.05`) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 116 data rows and includes the columns Vendor No, Vendor Name, Category, Tax ID, Stage, Annual Spend.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a vendor, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a vendor without a category through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] The vendors list contains exactly **116** vendors: 126 file rows minus 6 exact duplicate rows minus 4 vendors re-entered from the second system under a `SUP-` number with the same Tax ID written without its dash.
    How to check: As admin, read the vendors total with no filter applied, or count an export. Pass only at exactly 116. (126 = no dedupe; 120 = exact duplicates only; 112 = the five vendors with a blank Tax ID collapsed into one.)

16. [Exact] Re-entered vendors appear once: a vendor search for "Pioneer Industrial Supply" (file lines 77 and 104: V-0040 with Tax ID `39-5934900`, and SUP-2857 written `PIONEER INDUSTRIAL SUPPLY` with `395934900`) returns exactly one vendor, and a search for "Brightpath Software" (lines 107 and 119: `Brightpath Software Inc.` and `Brightpath Software, Inc.`) returns exactly one vendor.
    How to check: As admin, run both searches. Pass only if each returns exactly one vendor.

17. [Exact] The five vendors whose Tax ID is blank in the file exist as separate vendors: Heartland Dairy, Ironbridge Consulting, Keystone Packaging Inc., Summit Roofing Inc., Sweetwater Honey LLC.
    How to check: As admin, search each full name. Pass only if all five exist, each as its own vendor with an empty Tax ID.

18. [Exact] Documents land on the right vendor whatever number they were filed under: Ridgeway Closures (V-0035, whose documents are filed as `V-35`, `v-0035`, and `0035`) shows W-9, Certificate of Insurance, and Code of Conduct received; Pioneer Industrial Supply (V-0040, whose W-9 and Certificate of Insurance are filed under its second number `SUP-2857`) also shows all three received.
    How to check: As admin, open each vendor's document checklist. Fail if any of the six shows as missing.

19. (CORE) [Exact] The document checklist depends on category: Harvest Valley Honey LLC (V-0010, Ingredients, stage Documents) shows W-9, Certificate of Insurance, and Code of Conduct received and **Food Safety Certificate** missing; Ironclad Corrugated (V-0074, Packaging) has the same three documents and shows its checklist complete.
    How to check: As admin, open both vendors. Fail if Harvest Valley Honey LLC shows complete or does not name the Food Safety Certificate as missing, or if Ironclad Corrugated shows anything missing. (Both vendors' code of conduct rows are written `Signed Code of Conduct`; both count.)

20. [Rule] A vendor with a missing required document cannot be approved.
    How to check: As admin, open Harvest Valley Honey LLC (stage Documents) and try to set its stage to Approved. Pass if the app refuses with a visible message, or offers no way to reach Approved while the document is missing, and after reloading the stage is still Documents. Fail if it reaches Approved.

21. (CORE) [Automation] Completing the paperwork moves the vendor to Review with no other action: once the tester records a Food Safety Certificate for Harvest Valley Honey LLC (expires 2028-06-30), its stage reads Review.
    How to check: As admin, confirm the stage is Documents, add the certificate with expiry 2028-06-30 (attach any small file if the app requires one), save, reload. Pass only if the stage now reads Review and the tester never touched the stage field. Fail if it stays at Documents or the stage had to be set by hand.

22. [Permission] Only the admin approves: Rosa can move Pinnacle Carton Co. (V-0069, Packaging, stage New) to Documents but cannot approve Harvest Valley Honey LLC; the admin can.
    How to check: As restricted, move Pinnacle Carton Co. to Documents and reload (expect it saved). Open Harvest Valley Honey LLC, now at Review, and try to set Approved (expect no control, or a rejection and still Review after reload). Then, as admin, approve it. Fail if restricted approves, cannot move Pinnacle Carton Co., or admin cannot approve.

23. [Exact] The approved-vendor figure follows approvals: after item 22 the dashboard's Approved vendors reads **59** (58 imported plus Harvest Valley Honey LLC) and Vendors in onboarding is exactly one lower than just before the approval.
    How to check: As admin, note Vendors in onboarding before approving in item 22; after approving, reload the dashboard. Pass only if Approved vendors is 59 and Vendors in onboarding dropped by exactly one. If an earlier item approved another vendor, expect 58 plus all approvals.

24. [Exact] Lapsed insurance was read from the documents: exactly **6** approved vendors hold a Certificate of Insurance that has expired, and the Insurance alert lists exactly these: Brightpath CPA Group, Brightpath Legal LLP, Copper Kettle Orchards, Frontier Logistics, Precision Mechanical, Sunridge Honey LLC.
    How to check: As admin, open the list behind the Insurance alert (or filter approved vendors on lapsed insurance). Pass only if exactly these six appear, each with its expiry date. (Sunridge Honey LLC's certificate row is written `Cert. of Insurance`; an import that only reads rows named `Certificate of Insurance` drops it.)

25. [Automation] The insurance alert follows today's date with no manual step: when Cornerstone Landscaping's (V-0066, Facilities) insurance expiry is set to 20 days from today it joins the alert and the figure reads **7**; set to 45 days from today it leaves and the figure reads **6**.
    How to check: As admin, set Cornerstone Landscaping's Certificate of Insurance expiry to today + 20 days, save, reload the dashboard (expect 7 with the vendor listed); set it to today + 45 days, save, reload (expect 6 without it). Fail if either reading differs or a refresh, recalculate, or re-import action was needed.

26. [Exact] The impossible certificate was flagged at import, not silently accepted: Highway 30 Transport Inc. (V-0087, stage Review) has a Certificate of Insurance issued `2026-03-16` that expires `16-Mar-2025`; the vendor, its document, or an import report the admin can open shows a visible warning, flag, or issue entry for it.
    How to check: As admin, open Highway 30 Transport Inc. and any import summary, log, or issues screen. Fail if the certificate shows as ordinary with no warning anywhere in the app. A mention only in `RESULT.json` notes does not count.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 22), API 1 (7), Dashboard 2 (8, 9), Exact 10 (10, 11, 15 to 19, 23, 24, 26), Audit 1 (12), Rule 2 (13, 20), Automation 2 (21, 25), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 19, 21.
