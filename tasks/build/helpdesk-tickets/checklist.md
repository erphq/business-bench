# Acceptance checklist: helpdesk-tickets

Twenty-six binary items. Each passes only if every stated condition holds; anything else is a fail.
Items marked (CORE) define "first usable". Reference numbers come from `reference/counts.json`
(seed 0). They hold for any test date from 2026-09-01: every imported first-reply deadline falls
before it, and the August figures are fixed.

**Setup.** `RESULT.json` gives `url`, `admin` (full access), `restricted` (the scoped staff login the
task names: agent Sam Delgado), and `notes`. Use two browsers or a private window for the second
session. Invitations need no email delivery: the app must show the invite link to the admin. "Reject"
means a visible message and no change after reload. First-reply promises are 1 hour for P1, 4 for P2, 8
for P3, and 24 for P4, in clock hours from the ticket's creation. Open means any status other than
Resolved or Closed. When an item has you create a ticket without naming one, create a P3 ticket for
Vantage Point Media (contact ywood@vantagepointmedia.com, subject `Checklist test`) assigned to Sam
Delgado, and delete it once the item is judged, so later counts hold. At the start of item 15, also
create the ticket item 21 needs: the same test ticket with priority P1, left unanswered. A rerun after
a change request works on the same app: where an earlier pass already performed an item's action on a
named ticket (resolved), judge the item on the ticket as that pass left it instead of repeating the
action.

---

1. (CORE) [Delivery] `RESULT.json` has `url`, `admin.user`, `admin.password`, `restricted.user`, `restricted.password`, `notes`; the URL loads a login page in a desktop browser on the tester's machine; both logins sign in.
   How to check: Open the URL; log in as admin, log out, log in as restricted. Fail if a field is missing, the page does not load, or either login is rejected.

2. [Delivery] The URL is reachable from a phone on a different network than the build machine.
   How to check: On a phone with Wi-Fi off, open the URL; the login page renders and the admin login succeeds. Fail if it does not load, or the address is localhost, 127.0.0.1, or a private LAN IP.

3. (CORE) [Sharing] Admin can invite a person by email address and choose their role at invite time; the app shows an invitation link the admin can copy; opening that link in a private window lets the invitee set a password and lands them signed in with the chosen role; the invitee then appears in the app's users or team list with that role.
   How to check: As admin, invite `tester.viewer@example.com` as the read-only role, copy the link, open it in a private window, set a password, confirm the session is signed in as that person and that the users list shows them with the read-only role. Fail if no invite exists, the link is not shown, the link asks for anything other than a password, or the role differs.

4. [Sharing] Invitation links are single-use and invitations and users are revocable: opening an accepted link again does not sign anyone in; admin can revoke a pending invitation; admin can remove or deactivate a user, after which that user's login is rejected.
   How to check: Reopen the item-3 link in a fresh private window (expect a clear failure). Invite `tester.pending@example.com`, revoke it, open its link (expect failure). Invite `tester.remove@example.com` as the read-only role, accept that invitation in a private window, then remove or deactivate that user and try to log in as them (expect rejection). Keep the item-3 viewer for item 5. Fail on any of the three.

5. (CORE) [Permission] At least these three roles exist and hold: Admin manages users and settings and sees every record; Agent creates and edits records in its scope and has no user management or settings; Read-only is read-only, every create, edit, and delete control is absent or rejected.
   How to check: As the item-3 viewer, try to create a ticket and to edit an existing one (expect no control, or a rejection and no change on reload). As restricted, confirm the users and settings areas are absent or refused. Fail if the viewer can change anything or the staff login can manage users.

6. (CORE) [Permission] Row-level scope: the restricted login sees only tickets assigned to Sam Delgado, exactly 28 tickets, and cannot open another scope's record by URL.
   How to check: As restricted, read the tickets total and open five records to confirm scope. As admin, copy the URL of ticket HD-11243 (assigned to Priya Nair); paste it in the restricted session. Pass only on the exact count and an error, not-found, or redirect without rendering that record's details.

7. [API] Authorization is enforced by the server, not the page: replaying a data request from the restricted session with another scope's record id, or with any scope or role filter removed, returns 401, 403, or 404 or contains no foreign record; replaying a create or edit request from the viewer session is rejected the same way.
   How to check: In the restricted session open devtools > Network, load the list and one record, copy the data requests as cURL, substitute ticket HD-11243 (assigned to Priya Nair)'s id and remove filter parameters, re-issue. In the viewer session copy any write request the UI would send (or craft one against the same endpoint) and re-issue. Fail if any response carries foreign data or any write succeeds. Server-rendered apps with no separate data requests pass this item when items 5 and 6 pass.

8. (CORE) [Dashboard] A dashboard page shows at least four figures computed live from the data: Open tickets = 36, Escalated tickets = 11, First replies within promise for tickets created in August 2026 = 76.0% (92 of 121), Tickets resolved in August 2026 = 94; after the tester creates one ticket, the affected figure changes accordingly on reload.
   How to check: As admin, open the dashboard and read the four figures (exact values, tolerance 0.01 on money). Create a ticket in scope of Open tickets, reload, confirm Open tickets moved by one (or by the amount). Fail if a figure is missing, wrong, or static.

9. [Dashboard] The dashboard respects scope: signed in as restricted it shows the same figures for that scope only: Open tickets = 5.
   How to check: As restricted, open the dashboard. Fail if it shows company-wide figures or is absent.

10. [Exact] The main list has working search, at least one filter, and column sort: searching `VPN` returns exactly 25 row(s); filtering on Priority = P1 returns 15; sorting by Created descending puts HD-12268 (Silverline Logistics, `8/31/2026 11:52 AM`) first.
    How to check: As admin, perform the three operations. Fail on any count or order that differs, or if an operation is missing.

11. [Exact] Export of the main list to CSV produces exactly 250 data rows and includes the columns Ticket #, Client, Priority, Status, Assigned To, Created.
    How to check: As admin, export with no filter applied and open the file. Fail if rows or columns differ or export is absent.

12. [Audit] Records show who created and who last changed them and when, and an activity or audit log lists the tester's own create, edit, and delete actions with user and timestamp.
    How to check: As admin, create a ticket, edit it, delete it; open the record's history or the audit log. Pass only if all three actions appear attributed to the admin user with timestamps, and an existing imported record shows created-by and updated-at fields.

13. [Rule] Required fields are validated by the server: submitting a ticket without Subject through the form is rejected, and replaying the create request without that field (devtools > copy as cURL, remove the field) is also rejected.
    How to check: Perform both. Fail if either creates a record (check the list after reload).

14. (CORE) [Persistence] Data survives a restart of the app and lives on the server, not in the tester's browser.
    How to check: After the items above, ask the operator to restart the app (or wait 10 minutes), then log in as admin in a different browser. Pass only if the counts and the tester's remaining changes are present. Fail if anything reverted to import values.

15. [Exact] The clients list holds exactly 60 clients (64 file rows minus 2 exact duplicate rows and 2 rows that repeat a client with its web domain written differently, `LLC` added to the name, and no account number): Uptown Fitness (line 21; `Uptown Fitness LLC` with `UPTOWNFIT.COM` on line 5) and Ridgeview Animal Hospital (lines 36 and 55) each appear once.
    How to check: As admin, create the item-21 P1 ticket first (see Setup). Then read the clients total and search `Uptown` and `Ridgeview`. Pass only at exactly 60 and one result for each search. (64 = no dedupe; 62 = only exact duplicates removed.)

16. [Exact] The contacts list holds exactly 150 contacts (160 file rows minus 4 exact duplicates and 6 rows repeating an email in other letter case): Linda Wright (`lwright@quarryroad.com` on line 121, `LWRIGHT@QUARRYROAD.COM` on line 64) appears once, linked to Quarry Road Nursery; Luis Murphy (Pinewood Property Group), Kenneth Rivera (Dorsey Freight), and Rahul Nelson (Redwood Property Mgmt), who have no email, each exist as a contact of their company.
    How to check: As admin, read the contacts total, search `Linda Wright`, and search the three names without email. Fail if the total differs, Linda Wright appears twice or without her company, or any of the three is missing or merged into one.

17. (CORE) [Exact] The tickets list holds exactly 250 tickets (260 file rows minus 5 exact duplicates and 5 rows repeating a ticket number written `#10374`, `10374`, or `hd-10374`): HD-10374 (`HD-10374` on line 39, `#10374` on line 70) appears once; the 8 tickets with a blank Client belong to their contact's company, including HD-12326 (contact dmoore@glassworksoptical.com) under Glassworks Optical, HD-10579 (kallen@ironwoodfab.com) under Ironwood Fabrication, and HD-12466 (dlindqvist@riverbendphysio.com) under Riverbend Physio.
    How to check: As admin, read the tickets total, search `10374`, and open the three tickets. Fail if the total differs, HD-10374 appears twice, or any of the three has no client or the wrong one.

18. [Exact] Priorities were read from their spellings (`P1`, `p1`, `1 - Critical`, `P1 (Critical)` and the same for P2 to P4): tickets per priority are exactly P1 15, P2 57, P3 118, P4 60.
    How to check: As admin, filter tickets by each priority and read the counts. Fail if a fifth priority value exists or any count differs.

19. (CORE) [Rule] Each new ticket gets its first-reply deadline from its priority: a new P2 ticket shows a deadline 4 hours after its creation time; changing it to P1 moves the deadline to 1 hour after creation, and to P4 moves it to 24 hours after creation.
    How to check: As admin, create a ticket per Setup but with priority P2, read its deadline or due time, change the priority to P1 and then to P4, reading the deadline after each save; delete it afterwards. Fail if no deadline is shown or any of the three differs from creation plus 4, 1, or 24 hours (one minute either way is accepted).

20. [Exact] Each imported ticket shows whether its first reply kept the promise: HD-11797 (P2, created `8/5/2026 5:27 PM`, first reply 10 h 2 min later) shows missed; HD-10531 (P4, first reply 20 h 50 min after creation) shows met; HD-12030 (P4, created `25-Aug-2026 15:32`, never answered) shows missed or breached; and the August 2026 figure counts unanswered tickets as missed (76.0%, not 83.6%).
    How to check: As admin, open the three tickets and read their promise or SLA status; read the dashboard figure from item 8. Fail if any status differs, a ticket shows no status, or the figure is 83.6%.

21. [Automation] Tickets still waiting for a first reply past their deadline are escalated with no manual step: exactly 11 imported tickets are escalated, including HD-12030 (P4, New, never answered) and excluding HD-11838 (P2, In Progress, answered after its deadline); the P1 ticket created at the start of item 15 and left unanswered shows as escalated once more than an hour has passed.
    How to check: As admin, open the escalated list or filter and read its total (not counting the new P1 ticket); look for HD-12030 and HD-11838. At least 61 minutes after creating the P1 ticket, reload it and the escalated list, then delete it. Fail if the imported total differs, HD-12030 is missing, HD-11838 appears, or the new ticket is not escalated.

22. [Exact] The impossible ticket was flagged, not silently imported: HD-11327 (Seaside Realty Partners, line 118) was created `2026-07-28 10:18` and resolved `2026-07-26 19:18`; the ticket exists and shows a visible warning, flag, or import-issue entry, or its dates are corrected with the original values recorded on the ticket or in an import report the admin can open.
    How to check: As admin, open HD-11327 and any import summary, log, or issues screen. Fail if the ticket is missing, or it shows a resolution before its creation with no warning, flag, note, or import-issue entry anywhere in the app. A mention only in `RESULT.json` notes does not count.

23. (CORE) [Rule] A ticket cannot be resolved or closed without a resolution note, and the server enforces it: signed in as restricted, resolving HD-11234 (Ivy Lane Florist, In Progress, Sam Delgado's) with an empty note is rejected, and replaying the resolve request without the note is rejected; with a note it resolves.
    How to check: As restricted, try to resolve HD-11234 with no note; send a resolve with a note on the Setup test ticket and copy that request as cURL, remove the note, change the id to HD-11234, and re-issue; reload; then resolve HD-11234 with a note. Fail if HD-11234 resolves without a note by either path, or cannot be resolved with one.

24. [Automation] The first reply is recorded by itself: signed in as restricted, posting a reply to the client on a new unanswered ticket assigned to Sam Delgado sets that ticket's first-reply time to the reply time and marks its promise as met, with no separate field to fill in.
    How to check: As admin, create a ticket per Setup; as restricted, reply to it; as admin, reload it and read the first-reply time and promise status; delete it afterwards. Fail if the first-reply time is blank, differs from the reply time by more than a minute, or the ticket shows as missed or escalated.

25. [Permission] Client users see only their own company's tickets: admin can invite `tester.client@example.com` as a client user of Glassworks Optical; signed in as that user, the tickets list shows exactly Glassworks Optical's 12 tickets, including HD-12326 (blank Client in the file), and opening HD-10374 (Saltmarsh Kayaks) by URL shows an error, not-found, or access-denied.
    How to check: As admin, invite the client user and accept the invite in a private window. As that user, read the tickets total, look for HD-12326, and paste the URL of HD-10374 copied from the admin session; re-issue the list request from devtools with any client filter removed. Fail if the total differs, HD-12326 is missing, or any other company's ticket renders or appears in a response.

26. [Permission] Client users raise tickets only for their own company and cannot assign agents: as the item-25 client user, a new ticket lands under Glassworks Optical; replaying its create request naming Saltmarsh Kayaks is rejected or saved under Glassworks Optical; the client user has no control to set or change the assigned agent, and a replayed assignment change is rejected.
    How to check: As the client user, raise a ticket and copy the request as cURL; re-issue it with the client changed to Saltmarsh Kayaks' id or name; look for an assignee control; replay an admin assignment request (from devtools in the admin session) with the client user's cookie or token; check each result as admin and delete the test tickets. Fail if a ticket lands under another company or the client user changes an assignment.

---

Tags: Delivery 2 (1, 2), Sharing 2 (3, 4), Permission 4 (5, 6, 25, 26), API 1 (7), Dashboard 2 (8, 9), Exact 8 (10, 11, 15 to 18, 20, 22), Audit 1 (12), Rule 3 (13, 19, 23), Automation 2 (21, 24), Persistence 1 (14). Core: 1, 3, 5, 6, 8, 14, 17, 19, 23.
