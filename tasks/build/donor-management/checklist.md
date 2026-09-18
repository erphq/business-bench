# Acceptance checklist: donor-management

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items 1 to 14 are the enterprise baseline (`docs/build-baseline.md`); 15 to 26 are this app's. Items
marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0). All
donors are fictional.

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

Here "restricted" is Nia Robinson, program officer for Youth Literacy and Scholarships. Omar Haddad
runs Food Pantry, Grace Kim runs Senior Meals, and General Operating has no officer. A household is
everyone at one street address (apartment included); a donor with no address is a household alone.
Dashboard terms: "Raised year to date" totals gifts dated in 2026, one-time gifts and pledge payments
alike, and never the pledge amounts themselves (the seed's last gift is dated 2026-09-05, so run this
list on a 2026 date); "Outstanding pledges" sums each pledge's amount minus its payments; "Letters owed"
counts gifts of 250.00 or more with no acknowledgement recorded (`Y`, `Yes`, `yes`, or `Sent` plus a date
in the file mean acknowledged; blank, `N`, or `n/a` mean not). In item 8, record the new gift (dated
today, under 250.00) to General Operating and delete it once item 9 is checked, so later counts are the
import values. Do items 22 and 23 in order.

Wrong readings the baseline values rule out: the `Alvarez` search matches Kwame Alvarez's G-10157 and
G-10199; the Food Pantry filter returns 67 when `food pantry`, `FOOD PANTRY`, or `Food Pantry ` rows
are not matched, and the same mistake gives Nia 55 gifts instead of 70; year to date reads 74,575.75
with the duplicated gift rows kept and 95,375.75 with 2026 pledge commitments added.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Program Officer creates and edits records in its scope and has no user management or settings; Viewer (the board treasurer) is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create one gift and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only gifts to Nia Robinson's programs, Youth Literacy and Scholarships, exactly 70 gifts, and cannot open another scope's record by URL.
   How to check: As restricted, read the gifts total and open five records to confirm scope. As admin, copy the URL of gift G-10143 (Jennifer Castillo, Food Pantry); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute gift G-10143 (Jennifer Castillo, Food Pantry)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Raised year to date = 73,725.75, Donor households = 150, Outstanding pledges = 37,225.00, Letters owed = 9; after the tester creates one gift, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create one gift in scope of Raised year to date, reload, confirm Raised year to date moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Raised year to date = 36,825.50.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Alvarez` returns exactly 2 row(s); filtering on Program = Food Pantry returns 76; sorting by Amount descending puts G-10206 (Paul Collins, file value `$15,000.00`) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 228 data rows and includes the columns Gift ID, Donor, Gift Date, Amount, Program.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create one gift, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting one gift without a program through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] Donors are counted as households: exactly **150** households from 190 file rows (176 people after removing 8 exact duplicate rows and 6 people re-entered under a second donor id; 26 couples share an address).
    How to check: As admin, read the donor households total. Pass only at 150. (190 = no dedupe; 182 = exact duplicates only; 176 = people, not households; 147 = apartment numbers ignored; 145 = the six donors with no address merged into one.)

16. [Exact] A couple whose address is written two ways is one household holding both people: Eric Lewis (file line 53, `1329 Ocean Street`) and Yuki Ramirez (line 162, `1329 Ocean St`) are in the same household, whose 2026 giving is **200.00** (120.00 + 80.00) and lifetime giving **3,100.00**.
    How to check: As admin, search each name and open the household. Fail if they are in different households, either is missing, or either giving figure differs.

17. [Exact] Neighbours and donors without an address stay separate: Edward Ruiz (`314 Birch Avenue Apt 2`) and Nancy Morgan (`314 Birch Avenue Apt 5`) are different households, and so are each of the six donors with no address: Carol Rogers, Cynthia Allen, Dmitri Chavez, Jennifer Hill, Ronald Kelly, Wei Jones.
    How to check: As admin, search each name. Fail if Edward Ruiz and Nancy Morgan share a household, or any two of the six share one.

18. [Exact] A person entered twice is one donor carrying all their gifts: Carlos Sanchez (line 92 as `D-00007` with `csanchez@yahoo.com`, line 98 as `D-00177` with `Csanchez@yahoo.com`) appears once, with lifetime giving **1,525.00**, of which 1,300.00 was filed under D-00177.
    How to check: As admin, search "Carlos Sanchez". Pass only if one donor appears and lifetime giving reads 1,525.00. (225.00 = the gifts filed under the second id were lost.)

19. [Exact] Gifts are imported once and year to date counts money received: exactly **228** gifts (235 file rows minus 7 duplicated rows), and Raised year to date **73,725.75** is 42,750.75 in one-time gifts plus 30,975.00 in pledge payments.
    How to check: As admin, read the gifts total and the dashboard figure; if the app splits the figure by gift type, both parts must match. Fail if the gift count or the year-to-date figure differs.

20. [Exact] Pledge balances subtract every payment, whatever pledge id it was filed under: PL-0033 (Eric and Angela Lopez, Senior Meals, 1,000.00 quarterly) has three payments of 250.00, one filed as `33`, and shows a balance of **250.00**; Outstanding pledges reads **37,225.00**.
    How to check: As admin, open PL-0033 and the dashboard. Fail if the balance or the total differs. (500.00 = the payment filed as `33` was not linked.)

21. [Exact] The pledge that ends before it starts was flagged at import, not silently accepted: PL-0004 (Donald Edwards, General Operating, 5,000.00) starts `2026-02-01` and ends `01/31/25`; the pledge or an import report the admin can open shows a visible warning, flag, or issue entry.
    How to check: As admin, open PL-0004 and any import summary, log, or issues screen. Fail if the pledge shows as ordinary with no warning anywhere in the app. A mention only in `RESULT.json` notes does not count.

22. (CORE) [Automation] Recording a pledge payment updates the balance and both figures with no other step: a 500.00 payment dated today on PL-0009 (Carol Rivera, Food Pantry, 1,000.00, nothing paid yet) leaves a balance of **500.00**, Outstanding pledges drops by exactly 500.00 (to 36,725.00 if nothing else changed), and Raised year to date rises by exactly 500.00.
    How to check: As admin, note both dashboard figures, record the payment against PL-0009, reload the pledge and the dashboard. Fail on any other movement or if a recalculate step was needed.

23. [Rule] A payment larger than what is left on a pledge is refused: after item 22, a payment of 500.01 on PL-0009 is rejected with a visible message and the balance stays 500.00; a payment of exactly 500.00 is accepted and the balance reads 0.00.
    How to check: As admin, try 500.01 (expect refusal and 500.00 after reload), then 500.00 (expect saved and 0.00). Fail if 500.01 saves or 500.00 is refused.

24. [Automation] Acknowledgement letters are flagged from the amount: the 9 letters owed include the five unacknowledged gifts of exactly 250.00 (G-10142, G-10169, G-10170, G-10196, G-10211); a new 250.00 gift is flagged by itself and Letters owed reads 10; a new 249.99 gift is not flagged; marking the 250.00 gift's letter sent returns the figure to 9.
    How to check: As admin, open the letters-owed list and confirm the five 250.00 gifts are on it; record the two gifts for Ingrid Wright (who has no other gifts or pledges; program General Operating), reload after each, then mark the 250.00 gift's letter sent and reload. Fail on any other reading. (4 owed = a strictly-over-250 rule.)

25. [Permission] A program officer sees donors only through her programs: signed in as restricted, the donor households total is exactly **61** (households with a gift or pledge to Youth Literacy or Scholarships), and Mateo Cook's record shows his Youth Literacy gift G-10159 (150.00) but not his Food Pantry gifts G-10127 and G-10192.
    How to check: As restricted, read the households total and open Mateo Cook. Fail on any other count, or if either Food Pantry gift or its amount appears.

26. [Permission] A program officer records gifts only to her own programs: as restricted, a 40.00 gift from Mateo Cook to Scholarships saves, and the same gift to Food Pantry is refused or the program is not offered.
    How to check: As restricted, record both gifts and reload. Fail if the Food Pantry gift saves or the Scholarships gift is refused.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 4 (5, 6, 25, 26), API 1 (7), Dashboard 2 (8, 9), Exact 9 (10, 11, 15 to 21), Audit 1 (12), Rule 2 (13, 23), Automation 2 (22, 24), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 22.
