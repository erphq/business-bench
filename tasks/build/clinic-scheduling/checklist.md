# Acceptance checklist: clinic-scheduling

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items 1 to 14 are the enterprise baseline (`docs/build-baseline.md`); 15 to 26 are this app's. Items
marked (CORE) define "first usable". Reference numbers come from `reference/counts.json` (seed 0). All
patients are fictional.

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names), and `notes`. Use two browsers or a private window for the second session. Invitations
need no email delivery: the app must show the invite link to the admin.

Here "restricted" is Lena Fischer, one of six therapists (with Sam Okafor, Priya Nair, Marcus Bell, Hana
Sato, and Diego Ramos). Dashboard terms: "Booked appointments" counts appointments at status Booked;
"Utilization, August 2026" is minutes in Completed appointments dated in August divided by rostered
minutes in August (tolerance 0.05 points); "No-shows, August 2026" counts No-show appointments dated in
August; "Recall list" counts patients who are not discharged, have at least one Completed appointment,
and have no Booked appointment. A patient is flagged at two or more no-shows. In item 8, book the new
appointment with Priya Nair on 2026-09-15 at 09:30 for 45 minutes (a free slot), for any patient with
nothing else that day, and delete it once item 9 is checked; item 12 may reuse the slot. Dates in this
list are absolute: the seed's statuses do not depend on the test date. Do items 22 to 25 in order.

Wrong readings the baseline values rule out: the `Jones` search matches Ingrid Jones's A-30172, A-30224,
and A-30242; the No-show filter returns 15 when the row written `NO-SHOW` is not matched; a text sort on
the Date column puts A-30285 (`September 26, 2026`, `9:00 AM`) first; matching the Therapist field as
written (`LENA FISCHER`) gives Lena 61 appointments instead of 65.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Therapist creates and edits records in its scope and has no user management or settings; Viewer (the practice accountant) is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a appointment and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only appointments where Lena Fischer is the therapist, exactly 65 appointments, and cannot open another scope's record by URL.
   How to check: As restricted, read the appointments total and open five records to confirm scope. As admin, copy the URL of appointment A-30235 (Amy Lindqvist with Sam Okafor, 2026-09-14 15:15); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute appointment A-30235 (Amy Lindqvist with Sam Okafor, 2026-09-14 15:15)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Booked appointments = 49, Utilization, August 2026 = 58.5%, No-shows, August 2026 = 15, Recall list = 57; after the tester creates one appointment, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a appointment in scope of Booked appointments, reload, confirm Booked appointments moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Booked appointments = 9.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `Jones` returns exactly 3 row(s); filtering on Status = No-show returns 16; sorting by date and start time descending puts A-30287 (Susan Young with Hana Sato, 2026-09-26 at 10:45, file values `09/26/2026` and `10:45`) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 287 data rows and includes the columns Date, Start Time, Patient, Therapist, Status.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a appointment, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a appointment without a patient through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. (CORE) [Exact] The patient register holds exactly **150** patients: 159 file rows minus 5 exact duplicates and 4 patients re-registered under a second record number (for example Carlos Nelson, line 123 as `003686` with birth date `11-Sep-1990` and line 118 as `006058`, `NELSON`, `1990-09-11`); the three pairs of different patients who share a name, Donna Morris, Ronald Edwards, and Jessica Nelson, stay six patients.
    How to check: As admin, read the patients total, then search each shared name (expect two patients with different birth dates) and "Carlos Nelson" (expect one). Pass only at 150 and all four searches as stated. (159 or 154 = duplicates kept; 147 = patients matched on name alone.)

16. [Exact] Therapists come from the roster once each, with shift times read correctly: exactly **6** therapists, and Lena Fischer's rostered time in August 2026 is **39** hours (13 three-hour shifts, written `08:00`-`11:00`, `1:00 PM`-`4:00 PM`, `8am`-`11am`, and so on).
    How to check: As admin, open the therapists list and Lena Fischer's August roster or availability. Fail if the count is not 6 (for example `priya nair` and `Priya Nair` as two therapists) or Lena's August hours differ.

17. [Exact] Appointments are imported once, with durations in minutes and each patient linked whatever record number was used: exactly **287** appointments (293 file rows minus 6 duplicated rows); A-30004 (duration `1:00`) lasts 60 minutes and A-30018 (duration `0:30`) lasts 30; Carlos Nelson's history lists both A-30047 (filed under `003686`) and A-30095 (filed under `006058` as `Carlos NELSON`).
    How to check: As admin, read the appointments total, open A-30004 and A-30018, and open Carlos Nelson's appointment history. Fail if the total, either duration, or either linked appointment differs.

18. [Exact] The double booking in the import is flagged, and a cancelled overlap is not: A-30241 (16:00, duration `1h`) and A-30242 (16:30, 45 minutes), both Booked with Marcus Bell on 2026-09-15, show a conflict warning or appear on a conflicts list; A-30236 (Cancelled, 16:00) and A-30237 (Booked, 16:15) with Diego Ramos on 2026-09-14 do not.
    How to check: As admin, open the four appointments and any import summary or conflicts screen. Fail if the Marcus Bell pair has no warning anywhere in the app, or the Diego Ramos pair is flagged. A mention only in `RESULT.json` notes does not count.

19. [Exact] No-shows are counted per patient across record numbers: Carlos Nelson shows **2** no-shows (A-30047 under `003686`, A-30095 under `006058`) and is flagged, and he is the only flagged patient.
    How to check: As admin, open Carlos Nelson and the flagged patients list or filter. Fail if Carlos Nelson shows 1 no-show, is not flagged, or any other patient is flagged.

20. [Exact] The recall list holds exactly **57** patients: it includes Christopher Ward (his only future appointment, A-30230, is Cancelled) and excludes Kathleen Patel (discharged) and Jeffrey Nelson (booked as A-30234 under his second record number `008734`).
    How to check: As admin, open the recall list. Fail if the count differs or any of the three is wrongly placed. (59 = record numbers not merged; 82 = discharged patients included.)

21. [Exact] Utilization for August 2026 reads **58.5%** for the clinic (5,790 completed minutes of 9,900 rostered) and **57.1%** on the restricted dashboard (Lena Fischer, 1,335 of 2,340).
    How to check: As admin, read the dashboard; as restricted, read it again. Fail if either figure differs by more than 0.05 points.

22. (CORE) [Rule] A therapist cannot be double-booked, while back-to-back bookings and cancelled slots are fine: Lena Fischer has A-30247 booked 13:00-13:45 and A-30250 cancelled 15:00-15:45 on 2026-09-16; booking Kathleen Ross with Lena at 13:30 is refused, booking her at 13:45 for 45 minutes is accepted, and booking Paul Young at 15:00 for 45 minutes is accepted.
    How to check: As admin, attempt the three bookings in that order and reload the day. Fail if the 13:30 booking saves, or either of the other two is refused.

23. [Rule] A patient cannot be in two appointments at once: Jessica Castillo is booked with Priya Nair on 2026-09-16 at 14:30 for 45 minutes (A-30249); booking her with Lena Fischer at 14:30 for 30 minutes is refused.
    How to check: As admin, attempt the booking (Lena is free from 14:30 after item 22) and reload. Fail if it saves.

24. [Automation] Marking no-shows updates the patient with no other step: after the tester books Kathleen Ross with Lena Fischer on 2026-09-11 at 09:00 and 09:45 (45 minutes each, a free stretch that day) and marks the first No-show, she shows 1 no-show and no flag; marking the second No-show gives 2, a flag, and **2** flagged patients.
    How to check: As admin, create both appointments, set each to No-show in turn, and reload Kathleen Ross and the flagged list after each. Fail on any other reading or if a recount had to be triggered.

25. [Automation] The recall list follows bookings: Christopher Ward is on the list; booking him with Priya Nair on 2026-09-15 at 10:15 for 45 minutes removes him and lowers the Recall list figure by exactly one; cancelling that appointment puts him back and restores the figure.
    How to check: As admin, note the figure, book, reload the list and dashboard, cancel, reload again. Fail if he stays on the list while booked, is missing after the cancellation, or the figure does not move both times.

26. [Permission] A therapist works only in her own schedule: signed in as restricted, the schedule for 2026-09-14 shows exactly **3** appointments (2 Booked, 1 Cancelled), none with another therapist, and creating an appointment for Sam Okafor is refused or not offered.
    How to check: As restricted, open 2026-09-14 in the schedule or filter the list to that date, then try to book any patient with Sam Okafor (expect no such option, or a refusal and nothing saved after reload). Fail on any other count or if the Sam Okafor booking saves.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 3 (5, 6, 26), API 1 (7), Dashboard 2 (8, 9), Exact 9 (10, 11, 15 to 21), Audit 1 (12), Rule 3 (13, 22, 23), Automation 2 (24, 25), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 15, 22.
