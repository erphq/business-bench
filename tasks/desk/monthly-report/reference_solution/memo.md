# Revenue by region, January-June 2026: three things to know

1. **North has no March data.** The export contains no rows at all for the North region in
   March 2026 - it is missing from the file, not a month of zero sales. The report shows
   "no data" for that cell and North's half-year total (457,426.09) covers five months only.
   Please have the March North rows re-exported before this goes anywhere.
2. **12 duplicate rows were removed.** 12 orders appear twice in the export with the same
   order_id, date and amount. Each is counted once in the report.
3. **Refunds are netted.** 14 refund rows (negative amounts shown in parentheses, ids ending in
   "-R") total -63,996.23 and are subtracted in the month they were issued. Region totals
   in the report are net of these refunds.

Half-year net revenue: North 457,426.09 (5 months) · South 612,698.71 ·
East 580,434.78 · West 612,903.61 · All regions 2,263,463.19.

Report.xlsx: the Report sheet is driven by SUMIFS formulas over the cleaned Data sheet
(deduplicated, dates normalised, amounts parsed to numbers).
