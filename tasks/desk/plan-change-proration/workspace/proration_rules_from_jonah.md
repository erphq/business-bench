# Catch-up prorations - how billing works

The billing sync stopped posting prorations on February 1, so none of the plan changes since then were charged or
credited. We are fixing it on the May invoices.

**How a mid-month change is prorated**

- Monthly plans bill on the 1st for the whole month, in advance.
- A change takes effect on the day it is made, and that day is on the new plan. The proration covers the days from
  the change date to the last day of that month, counting both.
- Use the real number of days in that month.
- The studio gets back the unused part of the old plan and pays for the same days on the new plan:
  credit = old monthly price x days / days in month, charge = new monthly price x days / days in month, each rounded to
  the cent; the proration is charge minus credit. A downgrade gives a negative number (a credit on the next invoice).
- Nonprofit studios have 20% off their plan, so both prices are 20% lower for them.
- If a studio changes plan twice in a month, each change is prorated on its own from its own date.

**What to leave out**

- A change that is undone on the same day (someone clicks the wrong plan and support switches it back) is not a
  change. Leave both events out.
- Annual-billed studios are prorated at renewal by the account team. Leave them out of this.

**Dates**

The event log is in UTC. Our billing day is Pacific time, so convert before you decide which day a change happened.

**What I need**

prorations.csv with one line per change: change_id (the event id), account_id, effective_date, days (the days
prorated) and proration.

- Jonah
