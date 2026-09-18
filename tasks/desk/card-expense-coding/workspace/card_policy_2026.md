# Hollowell Electric - company card policy (revised March 2026)

Every posted charge on a company card is coded to one account below, or sent to review. We code by **what kind of
purchase it is** - the merchant category (MCC) the card network reports - together with the cardholder's memo.
Do not code from the merchant's name: the same store sells job materials, shop supplies and equipment.

## Accounts

| Account | Name |
|---|---|
| 1350 | Due from employee |
| 1520 | Tools & equipment (capitalised) |
| 5100 | Job materials (billable) |
| 6120 | Shop supplies & small tools |
| 6210 | Vehicle fuel |
| 6220 | Vehicle repairs & parts |
| 6310 | Travel - lodging, air, car rental |
| 6320 | Travel meals (per diem) |
| 6400 | Meals - team & client |
| 6510 | Software & subscriptions |
| 6610 | Permits & licences |

## Item types

| Merchant categories (MCC) | How to code |
|---|---|
| 5065 Electrical parts & equipment, 5251 Hardware stores, 5200 Home supply warehouse, 5085 Industrial supplies | If the memo carries a job number (J- and four digits), 5100 whatever the amount. Otherwise it is for the shop: 6120, except that a single charge of $2,500.00 or more is equipment and goes to 1520. |
| 5541 Service stations, 5542 Automated fuel dispensers | 6210 |
| 5533 Automotive parts, 7538 Automotive service shops | 6220 |
| 7011 Hotels, 4511 Airlines, 7512 Car rental | 6310 |
| 5812 Restaurants, 5814 Fast food | On an approved trip day: 6320, subject to the per diem below. Any other day: 6400. |
| 5734 Software stores, 5817 Digital goods: applications, 7372 Computer programming / data processing | 6510 |
| 9399 Government services | 6610 |
| 5399 Misc. general merchandise, 5300 Wholesale clubs, 5310 Discount stores, 5311 Department stores | These stores sell everything, so the category tells us nothing. 5100 if the memo carries a job number; otherwise send it to review with no account. |
| 5813 Drinking places, 5921 Package stores (beer, wine, liquor), 4899 Cable / streaming TV, 7832 Movie theatres | Never company expenses. Personal - see below. |

A merchant category that is not in this table goes to review with no account.

## Travel meal per diem

On an approved trip (see the travel approvals file; only trips with status Approved count) meals are covered up
to **$70.00 per person per day**, all meals that day added together. On the day you leave and the day you come
back the limit is 75%, **$52.50**. Code the meals to 6320 and record anything above the day's limit as owed by the
cardholder (take it off that day's largest meal). Trip days run from the departure date to the return date, both
included.

## Personal charges

Anything in a personal category above, and any charge whose memo says it was personal, is coded 1350 Due from
employee and the cardholder owes the full amount back.

## For the import and the review list

coded.csv follows coding_import_template.csv: one row per posted charge. gl_account is the four-digit account, or
blank when the charge goes to review without one. employee_owes is what the cardholder has to pay back (0.00 when
nothing). Declined authorisations are not charges.

review.csv lists every charge you could not code and every charge where the cardholder owes money back - one row per
transaction with its txn_id, cardholder, amount and a short reason.
