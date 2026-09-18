# Revenue by region, January-June 2026: three things to know

1. **North has no March data.** The export contains no rows at all for the North region in
   March 2026 - it is missing from the file, not a month of zero sales. The report shows
   "no data" for that cell and North's half-year total (513,542.32) covers five months only.
   Please have the March North rows re-exported before this goes anywhere.
2. **12 duplicate rows were removed.** 12 orders appear twice in the export with the same
   order_id, date and amount. Each is counted once in the report.
3. **Refunds are netted.** 14 refund rows (negative amounts shown in parentheses, ids ending in
   "-R") total -62,781.81 and are subtracted in the month they were issued. Region totals
   in the report are net of these refunds.

Half-year net revenue: North 513,542.32 (5 months) · South 626,670.12 ·
East 583,367.78 · West 607,705.30 · All regions 2,331,285.52.

Report.xlsx: the Report sheet is driven by SUMIFS formulas over the cleaned Data sheet
(deduplicated, dates normalised, amounts parsed to numbers).
