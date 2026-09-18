# Acceptance checklist: recruiting-pipeline

Twenty-six binary items: the enterprise baseline (1 to 14) and this app's items (15 to 26). Each passes
only if every stated condition holds; anything else is a fail. Items marked (CORE) define "first usable".
Reference numbers come from `reference/counts.json` (seed 0).

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (Ken Okafor, the hiring manager
for Engineering), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.
Matthew Adams applied only to
REQ-0139 Sales Manager, a Maria Santos role outside Ken's scope.

**Words.** A candidate is a person; an application is that person's candidacy for one role. Stages are
Applied, Screen, Interview, Offer, Hired, plus the closed outcomes Rejected, Withdrawn, and Offer declined.
The file's other stage words mean: `New applicant` = Applied, `Phone Screen` and `Screening` = Screen,
`Onsite` = Interview, `Offer Extended` = Offer, `Not selected` = Rejected. Active means at Applied, Screen,
Interview, or Offer.

**Test records.** Every figure is for the imported data. Give every candidate you create a name starting
with `QA` and an `@example.com` email, apply test candidates to REQ-0158 (a Maria Santos role) unless an
item names another role, and delete each test record once the items that use it are done. Items 21 to 26
build on each other on REQ-0161: do them in order.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Hiring manager creates and edits records in its scope and has no user management or settings; Read-only (the CEO) is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a candidate and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only candidates who applied to Ken Okafor's roles, exactly 87 candidates, and cannot open another scope's record by URL.
   How to check: As restricted, read the candidates total and open five records to confirm scope. As admin, copy the URL of candidate Matthew Adams; paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute candidate Matthew Adams's id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: active candidates = 102, open roles = 21, offers out = 5, average time to hire (days) = 33.6; after the tester creates one candidate, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a candidate in scope of active candidates, reload, confirm active candidates moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: active candidates = 45.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Mitchell` returns exactly 3 row(s); filtering on source = Agency returns 21; sorting by expected salary descending puts Jeffrey Gray (266,000) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 196 data rows and includes the columns name, email, role, stage, and source.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a candidate, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a candidate without an email address through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. [Exact] Roles were imported once each with their owners: exactly **61** roles (63 file rows minus 2 repeated rows): **21** Open, **5** On hold, **31** Filled, **4** Cancelled (the file also writes `open`, `On Hold`, and `Closed - filled`); Hiring Manager written `K. Okafor` or `Okafor, Ken` is Ken Okafor, who owns exactly **23** roles, **9** of them open.
    How to check: As admin, read the roles total; filter roles by each status; filter by hiring manager Ken Okafor, then by Ken Okafor and Open. Fail on any other count. (A manager filter that finds fewer than 23 kept "K. Okafor" and "Okafor, Ken" as other people.)

16. (CORE) [Exact] Candidates are people, each listed once with every role they applied for: exactly **196** candidates (211 file rows minus 6 repeated rows, 4 re-applications with the email in different capitals such as `DONNAMITCHELL7@OUTLOOK.COM`, and 5 second applications by people already in the list); **Brian Mitchell** is one candidate with two applications, REQ-0136 Implementation Consultant and REQ-0150 QA Automation Engineer; **Donna Mitchell** is one candidate with one application, REQ-0149 Product Manager.
    How to check: As admin, read the candidates total; search "Brian Mitchell" and open the result; search "Donna Mitchell" and open the result. Pass only at 196 and if each search returns exactly one candidate showing the stated applications. (211 = no dedupe; 205 = only exact repeats removed; 201 = one row per application; 200 = emails compared case-sensitively.)

17. [Exact] Every application is linked to its role however the file wrote the id, and two different people who share a name stay apart: role **REQ-0142** QA Automation Engineer has exactly **11** applications (written `REQ-0142`, `REQ-142`, and `142` in the file), and there are two candidates named **Rebecca Phillips** (rebecca.phillips@gmail.com for REQ-0149; rphillips69@outlook.com for REQ-0145, whose note says she is not the same person).
    How to check: As admin, open REQ-0142 and count its candidates or applications; search "Rebecca Phillips". Pass only at 11 applications on REQ-0142 and exactly two Rebecca Phillips candidates, each with her own role. Fail if any application is unattached or attached to a role numbered "142".

18. [Exact] Salaries were imported as numbers: sorting roles by salary maximum, highest first, puts **REQ-0101** Machine Learning Engineer (file value `$250,000`) first, and candidate **Susan Williams** (file value `159k`) shows an expected salary of **159,000**.
    How to check: As admin, sort roles by salary maximum descending; open Susan Williams. Fail if the sort is unavailable, a different role is first (a text sort puts REQ-0156, `85000`, first), or Susan Williams shows 159, "159k" as text, or blank.

19. [Exact] The impossible hire date was flagged or corrected at import, not silently kept: **Carol Alvarez** (REQ-0110) applied `2025-12-13` and has Hired On `10/31/2025`, six weeks before she applied. The candidate or an import report the admin can open shows a visible warning, flag, or issue entry; or the date was corrected with the original value recorded on the candidate or in the import report.
    How to check: As admin, open Carol Alvarez and any import summary, log, or issues screen. Fail if she is missing, or the application shows a hire before the application date with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

20. [Exact] Time to hire (days from Applied to Hired On) is shown per department, excluding the flagged row: Engineering **32.0** (12 hires), Sales **33.4** (11), Customer Success **34.4** (5), Product & Design **39.7** (3); **33.6** over all 31 hires.
    How to check: As admin, open the dashboard or report that breaks time to hire down by department. Pass only if each figure is within 0.1. Fail if the breakdown is absent. (31.2 overall = Carol Alvarez's negative 43 days counted; different figures = dates read in one format only.)

21. [Rule] Applications move through the stages in order: an application at Applied cannot jump straight to Offer or to Hired.
    How to check: As admin, create candidate QA Alex Stone (qa.alex.stone@example.com) with an application to REQ-0161 at Applied. Try to move it to Offer, then to Hired (expect a visible rejection each time and, after reload, still Applied). Move it to Screen (expect success). Fail if either jump saves.

22. (CORE) [Automation] Scheduling an interview moves the application to Interview and puts it on the interviewer's schedule, with no separate stage change.
    How to check: As admin, schedule an interview for QA Alex Stone's REQ-0161 application with interviewer Ken Okafor on the next weekday at 10:00 for 60 minutes, and do nothing else. Reload. Pass only if the application is now at Interview and, signed in as restricted, Ken's interviews, schedule, or calendar shows it at that date and time.

23. [Rule] An interviewer cannot be booked into two interviews that overlap.
    How to check: As admin, create candidate QA Blair Stone (qa.blair.stone@example.com) on REQ-0161 at Screen. Schedule an interview for her with Ken Okafor on the item-22 date at 10:30 for 60 minutes (expect a visible rejection and no interview after reload), then at 11:00 for 60 minutes (expect success). Fail if the 10:30 interview saves or the 11:00 one is refused.

24. (CORE) [Rule] An offer cannot go out until the admin approves it, and a hiring manager cannot approve one.
    How to check: Signed in as restricted, create an offer of 180,000 for QA Alex Stone on REQ-0161 and try to mark it sent or extended. Pass only if that is refused with a visible message and Ken has no working approve control. As admin, approve the offer; as restricted, mark it sent (expect success). Fail if the offer is sent before approval or Ken can approve it.

25. [Rule] No offer can exceed the role's salary maximum: REQ-0161 Senior Backend Engineer has a range of 150,000 to 185,000 (file values `150k` and `$185,000`); an offer of 190,000 is refused and one of 185,000 saves.
    How to check: As restricted, move QA Blair Stone to Offer and create an offer of 190,000 (expect a visible rejection and no offer after reload); change it to 185,000 (expect it to save). Fail if 190,000 saves or 185,000 is refused.

26. [Automation] An accepted offer makes the candidate Hired, and a role whose openings are all taken becomes Filled: after QA Alex Stone's offer is marked accepted, her application is Hired with today's hire date, REQ-0161 (1 opening) shows Filled, and the dashboard's open roles figure is one lower.
    How to check: As admin, read the dashboard's open roles; mark QA Alex Stone's offer accepted and do nothing else; reload her record, REQ-0161, and the dashboard. Pass only if all three hold. Then delete QA Alex Stone and QA Blair Stone and set REQ-0161 back to Open with no hires.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 2 (5, 6), API 1 (7), Dashboard 2 (8, 9), Exact 8 (10, 11, 15 to 20), Audit 1 (12), Rule 5 (13, 21, 23, 24, 25), Automation 2 (22, 26), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 16, 22, 24.
