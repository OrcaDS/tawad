# DA parsing notes

Format quirks found while building milestone 3, newest findings first within each section. Recon evidence is in `recon.md`.

## Listing page (checked 2026-10-24)

- Structure: each section is a plain `<h3>` heading ("Daily Retail Price Range", "Daily Price Index", "Weekly Average Retail Prices", "Daily Cigarette Price Monitoring"), followed by year accordions (`<h3 class="ea-header">`) holding tables of links. The link text is the report date ("October 9, 2026", "October 12-18, 2026", "December 29, 2025 - January 3, 2026").
- 3,381 PDF links: 2,876 in scope, 504 cigarette reports skipped, and one stray `DA-NPC-Registration-Certificate.pdf` under an "FPA Facebook Page" heading, also skipped.
- Older links (2018 to 2020-04) use `http://`, and one uses `https://da.gov.ph/` without `www`. Downloads upgrade to `https`, and the manifest keeps the original URL.
- **Filename date and link text agree for 2,875 of 2,876 reports.** The exception is `Price-Monitoring-December-23-2024.pdf`, labelled "December 21, 2024". The filename wins, the manifest flags it `date_check = mismatch`, and the PDF title settles it at extract time.
- Link text has its own typos ("Marhc", "JUne", "Augsut", "Janauary", "May 17 2019" without a comma). Months are matched on their first three letters, which absorbs these and the filename typos ("Octermber").
- **The page never lists two versions of the same report.** When DA posts a revised file, it replaces the original link. Revisions therefore only appear over time: the manifest keeps rows that drop off the page (`on_page = false`) and ranks revisions across all rows ever seen.
- **No date has reports from more than one daily-range series** (`price_watch`, `retail_monitoring`, `price_monitoring`), so no series-priority rule is needed for late 2019.

## Series

| Series | Files | Filename families |
|---|---|---|
| `price_watch` | 200 | `Price-Watch-<Month>-<D>-<YYYY>`, `Daily<Mon><DD><YYYY>` (2018) |
| `retail_monitoring` | 19 | `RETAIL-Price-Monitoring-Sum-Market_<DDMONYY>`, `RETAILPrice-Monitoring-Report_<DDMONYY>`, `Retail-Price-Monitoring-<Month>-<D>-<YYYY>` (2019-09 to 2020-01) |
| `price_monitoring` | 1,900 | `Price-Monitoring-…`, `Price_Monitoring_<MM>-<DD>-<YYYY>`, `Price-Monitrong-…`, plus revision prefixes and suffixes |
| `daily_index` | 594 | `Daily-Price-Index-…`, `<Month>-<D>-<YYYY>-DPI-AFC` |
| `weekly_avg` | 163 | `Weekly-Average-Prices-…`, `Weekly-Average-Price-…`, `Weeky-Average-Prices-…` |

Weekly reports use the week's last day as `report_date` and its first day as `period_start`.

## Downloads

- DA's server takes about 20 s to send each PDF (0.3 to 1.7 MB), on top of the 5 s gap between requests. A full backfill takes about 20 hours. It runs newest first and can be stopped and resumed at any point.

## Page titles

- Continuation pages often have no title. Daily Price Index pages 2 onward and weekly pages 2 onward start straight with the table header (or a category name), so a page's type has to carry forward from the last titled page, confirmed by its header row.
