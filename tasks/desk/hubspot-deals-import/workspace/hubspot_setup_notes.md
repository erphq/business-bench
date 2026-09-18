# HubSpot deals import

From Marcus. Companies are already in HubSpot (export attached). Now the deals, using the template columns in that order.
Import both tabs of the pipeline workbook, one deal per bid or job number. The Archive 2025 tab is last year's work;
leave it out.

**Bid Number** is a custom deal property so we can match things later: the Bid # / Job # as written.

**Deal Name** is the job description (the Job column on Commercial, the Work column on Residential).

**Pipeline and Deal Stage** have to match HubSpot's labels exactly. The Commercial tab goes in the *Commercial Bids*
pipeline, the Residential tab in *Residential Jobs*.

Commercial Bids stages:

- Lead In: a new request we have not visited yet
- Site Walk Scheduled: a site walk or visit is booked
- Proposal Sent: our bid is with the client, including bids they have put on hold
- Negotiation: we are revising price or scope with them (value engineering counts)
- Closed Won: awarded or signed
- Closed Lost: they went with someone else, or we decided not to bid

Residential Jobs stages:

- New Inquiry: a call or web lead
- Inspection Booked: the roof inspection is booked or done but no estimate has gone out yet
- Estimate Sent: the homeowner has our estimate or quote
- Closed Won: sold
- Closed Lost: lost, too expensive, or they stopped answering

**Amount** is a plain number (no $ or commas). If the bid was revised, use the latest number. TBD stays blank.

**Close Date** is YYYY-MM-DD. For won and lost deals it is the date in Closed On (ignore whatever the old Expected
Close says). For open deals it is Expected Close; where we only wrote a month, use the last day of that month, and
for a quarter use the last day of the quarter (Q4 means Q4 2026).

**Company Domain Name** is how HubSpot links the deal to the company, so copy the domain from the companies export.
The Client column is typed loosely. Where the name alone is ambiguous, the contact's email domain tells you which
company it is. Residential jobs for private homeowners have no company: leave it blank.
