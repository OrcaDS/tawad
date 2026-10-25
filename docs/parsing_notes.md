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

## Page types (checked 2026-10-26 on all 2,877 files)

`ingestion/da_prices/classify.py` gives every page one type. It was checked against the first lines of every page in the lake, as pdfplumber reads them. Every page gets a known type; none is left `unknown`.

| Page type | Years | Title or header that identifies it |
|---|---|---|
| `market_matrix` | 2018-02 → 2020-04 | Header repeats "Prevailing Low High" once per market |
| `ncr_summary` | 2018 → 2021-08 | Header "Prevailing Low High Average" (2019) or "High Low Prevailing" (2020-06 on) |
| `ncr_compare` | 2021-09 → 2022 | "TODAY'S PREVAILING PRICE YESTERDAY'S PREVAILING PRICE" (also "last week" / "this week") |
| `market_range` | 2021-09 → now | "… per Market" (2021 posters: "Prevailing Retail Prices of Selected Commodities (PHP/KG) per Market") |
| `pork_by_market` | 2021-09 → 2024 | "… Fresh and Frozen Pork Products in NCR Markets" |
| `chicken_by_market` | 2022 → 2024 | "… Whole Chicken in NCR Markets" |
| `ncr_range` | 2021-10 → now | "… Commodities at NCR Markets", or header "COMMODITIES LOW HIGH" |
| `daily_index` | 2025 → now | "DAILY PRICE INDEX", "(DPI)", "… in the National Capital Region", or a header starting "COMMODITY SPECIFICATION" |
| `weekly_avg` | 2023-08 → now | "Weekly Average Retail Price …" |

Skipped page types: `infographic`, `stall_count`, `notes`, `image_only`, `unreadable`, `blank`.

- **One title, several layouts.** From 2018 to 2020, "Retail Prices of Selected Agri-fishery Commodities in Selected Markets in Metro Manila" (and "DAILY PRICE MONITORING [REPORT]") heads the NCR summary, the per-market matrix and the poster. Under those titles, the header row decides: two "prevailing" on one line means the matrix, and 20 or more images means the poster.
- **Matrix headers are garbled.** pdfplumber reads "PrevailingLow High" (2018) and mixes market names into the header letters (Dec 2019: "Prevailing 1. L C o o w mmonw H e ig a h lth Average"). Two "prevailing" on one line is the reliable test.
- **The NCR summary of 2019–2021 has no text title** in some files. The title is part of a picture, so the page starts at the header row.
- **Late-2021 posters** ("BANTAY PRESYO … AS OF OCTOBER 26, 2021"): page 1 lists NCR prices, but the prices are part of the image, so only the titles are text. Page 2 is a real per-market table. Pages 3–4 are pork maps (images only).
- **Continuation pages** with no title or header (weekly pages 2 on, 2018 matrix overflow pages) inherit the previous page's type. Footnote-only pages ("Source: …", "Note(s): …", "(A) - In the absence of raw data …", the DPI list of covered markets) are `notes`.
- DPI headers wrap differently in almost every file ("PREVAILING RETAIL / COMMODITY SPECIFICATION PRICE PER UNIT", "… RETAIL PRICE PER / UNIT (P/UNIT)"), and the 2025 DPI title wraps across two lines.

## Reports without extractable text (124 of 2,877)

- **123 files are image-only** (no text layer): 99 of the 163 weekly reports (2023-08 → 2026) and 24 daily range reports (mostly 2024–2025). They are clean pictures of the usual tables, so OCR could read them; without OCR they are marked failed with reason `image_only`.
- **1 file has text with no character map**: `Retail-Price-Monitoring-December-28-2019.pdf` extracts as `(cid:39)(cid:36)…`.
- Other image-only pages sit inside files that also have text pages (posters, pork maps), so they cost nothing.
