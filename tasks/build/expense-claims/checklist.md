# Acceptance checklist: expense-claims

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items 1 to 14 are the enterprise baseline (`docs/build-baseline.md`); 15 to 26 are this app's. Items
marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

Here "restricted" is Grace Liu, the Sales manager. A claim has one or more lines; `claims.csv` has one
row per line, grouped by Claim No. Dashboard terms: "Claims awaiting approval" counts claims at status
Submitted; "Awaiting reimbursement" totals approved claims not yet paid; "Reimbursed in 2026" totals
claims at status Paid; "Claims over policy" counts submitted claims with at least one line above the
limit for the claimant's grade in `expense_policy.csv`. In item 8, "create a claim" means file and
submit one for an Engineering employee (for example Laura Edwards), then delete it once item 9 is
checked, so later counts are the import values. Do items 19 to 26 in order: they build on each other.

Wrong readings the baseline values rule out: the `Hall` search matches Melissa Hall's C-1056, C-1069,
and C-1090; counting lines instead of claims gives 211 or 205 rows in items 10 and 11; totals that drop
amounts written like `$1,405.59` put C-1106 first in the Total sort; matching manager emails
case-sensitively gives Grace 6 reports and 18 claims instead of 28 in item 6.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Manager creates and edits records in its scope and has no user management or settings; Viewer (the auditor) is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create one claim and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only Grace Liu's own claims and those of her 12 direct reports in Sales, exactly 28 claims, and cannot open another scope's record by URL.
   How to check: As restricted, read the claims total and open five records to confirm scope. As admin, copy the URL of claim C-1078 (Laura Edwards, Engineering); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute claim C-1078 (Laura Edwards, Engineering)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Claims awaiting approval = 30, Awaiting reimbursement = 3,248.63, Reimbursed in 2026 = 12,913.16, Claims over policy = 5; after the tester creates one claim, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create one claim in scope of Claims awaiting approval, reload, confirm Claims awaiting approval moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Claims awaiting approval = 7.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Hall` returns exactly 3 row(s); filtering on Status = Paid returns 58; sorting by Total descending puts C-1092 (Sofia Garcia, 2,908.34) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 112 data rows and includes the columns Claim No, Employee, Submitted, Status, Total.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create one claim, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting one claim without a business purpose through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] The employee list holds exactly **60** people: 64 file rows minus 1 exact duplicate (Betty Phillips, lines 27 and 52) and 3 people re-imported with an upper-case email and an unpadded id (William Davis `E-12`, Nicholas Green `E-56`, Stephanie Patel `E-53`); Grace Liu shows exactly **12** direct reports.
    How to check: As admin, read the employees total, then open Grace Liu's team (or filter employees by manager). Pass only at 60 and 12. (64 or 63 = duplicates kept; 6 reports = the manager emails written `Grace.Liu@Tallgrass.io` or `GRACE.LIU@TALLGRASS.IO` were not matched, which drops Amanda Miller, Andrew Hughes, Andrew Okafor, Anna Turner, Charles Turner, and Stephanie Green.)

16. [Exact] The policy imported as 20 categories with a limit per grade, not 60 separate categories: Hotel reads Staff 250.00, Manager 325.00, Executive 450.00; Conference Fees for Staff reads 1,500.00 (file `$1,500.00`); Airfare for Executive has no limit.
    How to check: As admin, open the categories or policy screen and a claim line's category picker. Fail if the picker offers anything other than 20 distinct categories (for example `Meals - Travel` twice), any of the five limits differs, or the Executive airfare limit shows as 0.

17. [Exact] Claims were imported as claims, not lines, and without duplicated lines: exactly **112** claims come from 211 file rows, and claim C-1096 (Ryan Cook, file lines 170 to 172, where the Training & Courses line of 538.32 appears twice) totals **667.91**.
    How to check: As admin, read the claims total and open C-1096. Pass only at 112 claims and a 667.91 total. (211 or 205 = lines counted as claims; 1,206.23 = the duplicated line kept.)

18. [Exact] The expense dated after its claim was submitted was flagged at import, not silently accepted: claim C-1076 (Mark Ruiz, submitted `08/21/2026`) has a Team Events line dated `August 16, 2027`; the claim, the line, or an import report the admin can open shows a visible warning, flag, or issue entry.
    How to check: As admin, open C-1076 and any import summary, log, or issues screen. Fail if the line shows as ordinary with no warning anywhere in the app. A mention only in `RESULT.json` notes does not count.

19. [Exact] The reimbursement figure matches the approved claims: before any batch, the amount awaiting reimbursement is **3,248.63** across exactly **14** approved claims, and Melissa Hall, who has two of them (C-1069 and C-1090), is owed **106.75**.
    How to check: As admin, open the reimbursement or batch screen (or the approved claims list filtered to Melissa Hall). Fail if the total, the claim count, or Melissa Hall's amount differs. (3,871.55 = duplicated lines kept.)

20. (CORE) [Automation] Creating the reimbursement batch pays exactly the approved claims in one step: the batch holds the 14 claims totaling 3,248.63, each of them then shows Paid with the batch reference, Awaiting reimbursement reads 0.00, and Reimbursed in 2026 reads **16,161.79**.
    How to check: As admin, create the batch with the one action the app provides, then reload the claims list and the dashboard. Fail if an approved claim was left out, a claim at any other status was included, a claim had to be marked Paid by hand, or either figure differs.

21. [Exact] Imported submitted claims are checked against the claimant's grade: exactly **5** are over policy, C-1075, C-1084, C-1086, C-1097, and C-1110; C-1074 (Priya Raman, Manager, Hotel 312.40 against the 325.00 Manager limit) and C-1072 (Victor Almeida, Executive, Airfare 1,850.00 with no limit) are not flagged.
    How to check: As admin, open the list behind Claims over policy (or filter claims on the over-policy flag), then open C-1074 and C-1072. Fail if the flagged set differs. (Flagging C-1074 = the Staff limit used for everyone; flagging C-1072 = `no limit` read as zero.)

22. [Permission] An employee login sees only that employee's claims: signed in as Robert Morris (Sales, one of Grace Liu's reports) the claims list shows exactly **5** claims, all his, and Grace Liu's claim C-1087 cannot be opened by URL.
    How to check: As admin, create or invite a login linked to employee Robert Morris with the employee role (or use one named in `RESULT.json` notes); as admin copy C-1087's URL. As Robert, read the claims total, then paste the URL. Fail on any other count or if C-1087's details render.

23. [Rule] A line over 75.00 needs a receipt and a line of exactly 75.00 does not: as Robert Morris, a claim with one Client Entertainment line of 75.01 and no receipt cannot be submitted; the same claim at 75.00 with no receipt submits.
    How to check: As Robert, create a claim with purpose "Receipt test" and that line, submit (expect a visible refusal and not Submitted after reload); change the amount to 75.00 and submit (expect Submitted). Fail if 75.01 submits or 75.00 is refused.

24. [Exact] Reimbursement is capped at the limit for the claimant's grade: a claim by Robert Morris (Staff) with Hotel 300.00 (receipt), Meals - Travel 48.50 (no receipt), and Taxi & Rideshare 92.00 (receipt) shows **440.50** claimed and **378.50** reimbursable (250.00 + 48.50 + 80.00).
    How to check: As Robert, create and submit that claim with purpose "Cap test", then open it as admin. Pass only if both amounts appear as stated. Fail if the reimbursable amount is 440.50, the claim is refused outright, or no reimbursable amount is shown.

25. [Permission] Managers approve their reports' claims but never their own: Grace Liu approves the Cap test claim, after which Awaiting reimbursement reads **378.50**; she cannot approve her own claim C-1087.
    How to check: As restricted, approve the Cap test claim and reload (expect Approved). As admin, read Awaiting reimbursement (expect 378.50: item 20 paid everything else and the Receipt test claim is still Submitted). As restricted, open C-1087 and try to approve it (expect no control, or a rejection and still Submitted after reload). Fail on any other outcome.

26. [Rule] An approved claim is locked against its employee and manager: neither Robert Morris nor Grace Liu can change the Hotel line on the approved Cap test claim.
    How to check: As Robert, then as restricted, open the Cap test claim and try to change the Hotel amount to 200.00 and save (expect no control, or a rejection and 300.00 after reload). Fail if either edit saves.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 4 (5, 6, 22, 25), API 1 (7), Dashboard 2 (8, 9), Exact 9 (10, 11, 15 to 19, 21, 24), Audit 1 (12), Rule 3 (13, 23, 26), Automation 1 (20), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 20.
