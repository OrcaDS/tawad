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

Skipped page types: `infographic`, `stall_count`, `notes`, `image_only`, `unreadable`, `blank`, `overflow`.

- **Text off the page.** Some PDFs place one wide sheet over two pages, shifted, so a page also carries text beyond its edges. `classify.page_text` reads only the text inside the page box, and drops the on-page rest of any run of words that crosses the edge (words under 15 pt apart): on Nov 28, 2022 the chicken page carries the pork page's title past its left edge (its last word crosses the edge; the chicken title starts 42 pt further on), and on Mar 13–15, 2018 a clipped footnote would read `…dents per market)`, a per-market title. Those 2018 pages are now `blank`.
- **`overflow`:** a page with most of its characters off the page is the cut-off edge of the previous page's sheet. On Oct 4–6, 2021, page 2 is the NCR poster's right strip: prices of "OTHER COMMODITIES" whose names are pictures. It used to read as an `ncr_range` page (11 rows a day without commodity names).

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

## Daily Price Index tables (checked 2026-10-26 on all 595 files)

`ingestion/da_prices/extract/daily_index.py` reads every DPI report into about 113,000 bronze rows (80 to 210 items per report). Every page gives rows, every row gets a category, and every report gets a market count.

- **Header variants.** `COMMODITY | SPECIFICATION | [UNIT |] PREVAILING RETAIL PRICE …`, wrapped differently over time. Sept 2025 splits the price header over two table rows (`RETAIL PRICE` / `PER UNIT (P/UNIT)`). July 25, 2025 ("Annex A") leaves the COMMODITY header blank. Columns are mapped by header text; `layout` records the header as read.
- **Split cells (2025).** pdfplumber splits each column into several cells (12 cells for 4 columns), and text can sit in any of them. A column is every cell from its header to the next header.
- **Row numbers and category letters (mid-2025).** Rows are numbered (`1`, `2` …) and categories lettered (`A IMPORTED COMMERCIAL RICE`) in cells of their own. They are dropped. In 81 rows DA typed `n/a` into the row-number cell, so `commodity_raw` reads `n/a\nImported Beef Forequarter`; silver strips the leading `n/a`.
- **Wrapped text.** Long names and specifications (2025 beef and pork cut descriptions run 5 to 8 lines) sometimes continue in a row of their own with no price, also across page breaks. DPI always writes a missing price as `n/a`, so a row with no price text is joined to the item above with a newline. Category names wrap the same way (`LIVESTOCK & POULTRY` / `PRODUCTS`).
- **Categories carry over page breaks.** A page often starts mid-category.
- **Price cells that aren't prices** (kept raw; silver makes them NULL): `#DIV/0!` (66 rows, an Excel error in DA's sheet), `n/a!`, `n/as`, `+n/a`, `n/a n/a`. One row (July 8, 2026, page 5) has a price and no item name.
- **Covered markets.** The footnote lists the markets numbered, sometimes in two columns ("Covered market", "Covered markets:", "Covered wet markets and supermarkets:"). `markets_covered` is the highest number in that list. It ranges from 4 to 36: **weekend reports cover far fewer markets** (5 to 7 on Sundays in May 2025), and April 2025 includes supermarkets.

## Weekly Average Price tables (checked 2026-10-26 on all 163 files)

`ingestion/da_prices/extract/weekly_avg.py` reads the 64 weekly reports that have a text layer (late Dec 2023 → now) into 5,503 bronze rows (57 to 100 items per report). The other 99 are image-only. Every page gives rows, every row gets a category, and every report gets a market count.

- **One header for the whole report.** Only page 1 has `COMMODITY | SPECIFICATION | UNIT | WEEKLY AVERAGE PRICE`, with an empty cell in front. Later tables (the rest of page 1 in some 2024 files, and pages 2 and 3) have no header. They either keep that empty first cell or drop it (2026 page 3), so they are read with the page-1 columns aligned from the right. The 3 files whose header reads `WEEKLY AVERAGE\nPRICE` give the same `layout`.
- **Explicit units.** `kg`, `pc` (eggs), `ml` and `L` (cooking oil).
- **Missing prices.** `-` means not sold (mostly 2025 on), `n/a` not available (mostly 2023–2024). Both are kept raw. Odd price cells: `#DIV/0!` (5 rows, Sept 2026) and an asterisk on brown eggs (`8.00*`, July–Aug 2024).
- **Categories** are one ALL-CAPS cell (`KADIWA RICE-FOR-ALL`, `IMPORTED COMMERCIAL RICE`, `BEEF PRODUCTS` …). Names change over time (`FISH` / `FISH PRODUCTS`, `CORN` / `CORN PRODUCTS`, `PORK AND BEEF PRODUCTS` / `BEEF AND PORK PRODUCTS`), and pork still sits under `BEEF PRODUCTS`, so silver takes categories from `commodity_map.csv`. Twice DA left a stray `x` in the unlabeled first cell of a category row, so that cell is ignored.
- **Wrapped text** stays inside one cell (`Medium (301-450 cm diameter/bunch\nhd)`). No row continues the one above. One row (Dec 8–13, 2025) has a price and no item name; it is kept.
- **Covered markets** are one paragraph, not a numbered list: `Markets Covered (29): Agora, Bicutan, …, Taguig & Trabajo` (2024, with the count) or `Markets Covered: … and Trabajo Market` (without it). `markets_covered` takes the stated count, or else counts the names between commas, "and" and "&". Where both exist they agree in all 18 files. The count ranges from 25 to 36.
- **Superscript markers** stay in names (`P20 Benteng Bigas Meron Naᵃ`); the footnote explains them ("available only in 5 markets").

## Daily range reports: `market_range` and `ncr_range` (checked 2026-10-26 on all 1,900 `price_monitoring` files)

`ingestion/da_prices/extract/market_range.py` and `ncr_range.py` read the daily report packets from **Jan 16, 2025 on**: 553 reports, 296,142 bronze rows (248,451 per market, 47,691 NCR-wide). The same packets from Dec 2022 to Jan 2025 have NCR posters instead of tables (below), and until Apr 2024 pork and chicken pages by market (below). From Sep 2021 to Dec 2022 the NCR page compares today's prevailing prices with the last report's (`ncr_compare`, below); their per-market grids and pork/chicken pages are read too (below). A report lands once any of its price page types can be read; the unread types are listed in the manifest (`status_reason = "partial: ncr_range"`) and `extract-da --redo` fills them in later. 46 late-2021 reports wait (posters on both page types, so nothing is readable).

**pdfplumber's tables and words can't be trusted on these pages.** Below the header, rows often lose their cell borders and land in one cell, sometimes two markets in one cell. pdfplumber also glues neighbouring cells into one word (`100.00100.00`, `NOT AVAILABLE160.00`). Characters inside a word sit 0.0–0.1 pt apart, separate words at least 1.1 pt, so both extractors place single characters into columns and only then join them into text, with a space at every gap over 0.5 pt (`extract/layout.py`).

### Per market (`market_range`, Dec 28, 2022 → now)

- **Header.** The row starting with `MARKET` (after an empty column in some files) names one commodity per column, under `COMMODITY (PHP/KG)`. Each commodity's column runs from its header cell to the next one; only these header boxes come from pdfplumber's table. Header text is kept as pdfplumber reads it, including line breaks and a few garbled names where two lines overlap (`(WCohirtne)` for `Corn (White)`).
- **Cells.** Until 2025: ranges (`40.00 -44.00`, `150.00-150.00`, sometimes no dash: `360.00 360.00`) or one value when low and high agree. 2026: single prevailing prices. A two-part cell is split into `price_low_raw` / `price_high_raw`; anything else goes to `price_prevailing_raw`.
- **Wrapped cells.** `NOT` / `AVAILABLE` can wrap onto a line of its own, above or below the market's line. Such a line has no market name and joins the nearest market's line.
- **Footnote inside the table box** (`Source: …`, Aug 19, 2025) ends the table.
- **DA typos kept raw:** `NOT AVAILABKE`, `NOT AVAILBLE`, `NOT AVAILANBLE`, `NOT AVAILABLE]`, and `#####` (an Excel column too narrow, Feb 2024).
- **Markets per page** range from 10 to 36: the number of markets grew from 13 (2023) to about 30–36 (2025–2026). 45 market names appear, with renames (`Mandaluyong Public Market` → `… I` and `… II`).
- **Not read yet (late 2021):** posters (no `MARKET` header). These pages raise `Unsupported`: their reports land partial if another page type reads, else wait.

### Per-market grids (`market_range`, Sep 1, 2021 → Dec 27, 2022; checked on all 282 pages of 286 reports)

"Prevailing Retail Prices of Selected Agri-fishery Commodities per Market": 10 commodities, 8 to 13 markets, one prevailing price per cell. Most column lines are missing, so pdfplumber's header has 4–5 cells, the last naming up to seven commodities, and each name wraps over up to three lines. `market_grid.py` rebuilds the header from word positions: words of one column overlap or sit ≤ 2 pt apart, neighbouring columns ≥ 15 pt apart (merge gap: 6 pt). Names are read top-down (`Well-milled Rice (Local)`, `Whole Chicken`, `*Egg (Medium)`; `*` = price per piece). Prices can be wider than their name, so each column starts halfway into the gap before it. 34,862 rows; on every market line but one the prices in reading order equal the row's cells.

- **Columns:** `Whole Chicken` until mid-2022, then `Sugar (Washed)` as the last column. `Galunggong (Local)` on Jan 4–5, 2022 (DA's heading, kept).
- **`NO MONITORING ACTIVITY CONDUCTED`** across a whole row (40 cells): kept raw for every commodity of that market.
- **A wrapped `NOT`** of the first market can sit level with the header's last line (30 pages, 2022); `NOT` / `AVAILABLE` never count as header words.
- **Known losses (7 cells):** on Jan 10 and 12, 2022 Marikina's `NOT AVAILABLE` is printed on one line touching its neighbours (`145.00NOT AVAILABLE160.00`), so three cells read `145.00N`, `OT AVAILABL`, `E160.00`; on Jul 13, 2022 one `NOT AVAILABL` loses its last letter. Kept raw.
- **Overflow page (Feb 7 and Feb 25, 2022):** page 3 holds only the Pechay and Red Onion columns, with no market names. Raises `Unsupported`; those 2 reports stay partial.

### NCR ranges (`ncr_range`, Jan 16, 2025 → now)

- **Two tables per page**, side by side, each under `COMMODITIES LOW HIGH [PREVAILING] AVERAGE` (`PREVALING` in some files, a point above the line; PREVAILING appears from Feb 2025). A table can restart lower down with a new header, and since Dec 2025 pages have up to four headers. Once (Nov 17, 2025) the header reads `HIGHPREVALING` as one word; it is split in proportion to its letters.
- **Rows** are clusters of price words at about the same height. Names are centred in their cells and often wrap onto two lines around the prices, so each name line joins the nearest row (`Imported Round Scad\n(Galunggong)`).
- **Merged LOW–HIGH cells.** When low equals high, DA writes one value centred across both columns; it fills both fields.
- **Separators.** The range dash is either glued to the low price (`160.00-`) or a word of its own between LOW and HIGH; it is dropped.
- **Categories.** ALL-CAPS name lines without prices (`KADIWA RICE-FOR-ALL`, `IMPORTED COMMERCIAL RICE`, `LOCAL COMMERCIAL RICE`) become `category_header_raw` for the rows below. The labels spanning several rows in the far-left column (`RICE (per kg)`, `LIVESTOCK AND POULTRY PRODUCTS`) can't be tied to rows reliably and are not kept; silver takes categories from `commodity_map.csv`. The name column is found as the commonest left edge of the words left of LOW, which keeps those labels out of names.
- **Footnote markers** stay in names, with or without a space (`Local Garlic (Bawang) b`, `Broccolic`, `Premium (RFA5)ᵃ`).
- **`NOT AVAILABLE`** spanning a whole row (Jan 2025, 54 rows) is kept in the one column it falls under.
- **Rows run together.** If a row would get two values for one column, the extractor raises `RowMerge` and the report fails with that reason rather than guessing. This does not happen in any current file.
- **Covered markets.** The footnote is a paragraph (`Markets Covered: …`), counted as for weekly reports. One report (Mar 24, 2025) has no list, so its `markets_covered` is NULL.

### NCR posters (`ncr_range`, Dec 28, 2022 → Jan 15, 2025; checked on all 534 pages)

"Retail Price Range of Selected Agri-fishery Commodities at NCR Markets" posters: one page, 47–88 items in panels (rice, corn, livestock, fish, vegetables, fruits, spices, other), each item `name  low - high` with no column headers. `ncr_range.py` reads them when a page has no `COMMODITIES … LOW HIGH` header. Rows get `layout = "poster"` and only `price_low_raw` / `price_high_raw`.

- **Price groups** are prices side by side at about the same height: `low - high`, one value (low = high, both fields), or `NOT AVAILABLE` (also DA's `NOT AVALABLE`). Not by text line: a high price or a dash can sit up to 2.5 pt off its low and fall into another line (Apr 2023), which first gave 400 nameless half-rows.
- **Columns.** Group starts line up into 5 (2023) to 7 (2024) price columns across the page; a word belongs to the column whose prices end right of it. Names wrap above and below their price (`Local Round Scad\nGalunggong`), so each name line joins the nearest group in its column within 10 pt.
- **Categories.** Lines that join no group are panel titles and sub-headings (`IMPORTED COMMERCIAL RICE`, mixed-case `Feed Grade`, `Cabbage Repolyo` over its varieties). A heading covers the rows below it until the next heading or a gap of more than 29 pt (a new panel). Some panels share a price column with a panel whose heading sits in another column (2024: eggs under CORN); their rows get no category (6,600 of about 33,600 rows) rather than a wrong one. Every rice row has `IMPORTED` / `LOCAL` in its category (4,208 rows) except the Dec 2024 `KADIWA RICE-FOR-ALL` panel (23) and 25 rows without one. When DA prints an item with no price at all (Imported Red Onion, Local Garlic on some days), its name can't be told from a sub-heading and becomes the category of the next rows (43 rows).
- **Footnote marks** stay raw on both sides: in names (`Alumahan b`, `Large)d`) and in prices (`250.00*`, `**35.00`, `100*`, `90.00g`). Missing glyphs show as `(cid:10)` (`IMPORTED C(cid:10)OMMERCIAL RICE`).
- **Hidden text.** Some 2024 pages carry stray words behind the panels (`Glutinous`, `Japanese` near the corn rows); they join the nearest name (`Corn (White)\nGlutinous`).
- **Not read:** the title and date above the panels, DA's contact block at the top right (phone, email, address), and the footnote.

### NCR today vs yesterday (`ncr_compare`, Sep 2021 → Dec 2022; checked on all 287 pages)

"Prevailing Retail Prices of Selected Agri-fishery Commodities at NCR Markets" posters: the same panels as the 2023–24 NCR posters, but each item has two prevailing prices, today's and the last report's (`Today` / `Yesterday`, `Last Friday`, `This Monday`, `Previous Monitoring`; the legend at the top names both dates). `ncr_compare.py` hands the page to the poster reader after three changes, and keeps only today's price, in `price_prevailing_raw` (the other is the earlier report's own price). Rows get `layout = "compare"`. 14,613 rows, 51 items on 283 of 287 pages.

- **Page sizes** run from 792 to 1257 pt wide (June 2022), so positions are scaled to 792 pt first. Today and yesterday sit up to ~30 pt apart after scaling, so price groups may be 35 pt apart (posters: 25).
- **Dropped:** the legend box and the dates under it, and the column labels over each panel (also glued, `TodayPrevious`).
- **`NOT` over `AVAILABLE`** is one cell on two lines; it becomes one price at the cell's middle height, so it pairs with the other column's price.
- **A lone price is today's.** That's true of all 16 cases: a panel with only a `Today` column (Oct 4, 2021) and DA's overprinted cells, where a price is drawn on top of `NOT AVAILABLE` (`NOT AVAILA3B0L0E.00`, kept raw).
- **Panels without prices.** On Oct 5–6, 2021 the OTHER COMMODITIES panel has names but no prices, so it gives no rows (and, since the poster reader now ends the last column at its prices, its names don't join the FRUITS rows).
- **Known losses:** on Feb 22 and Mar 8, 2022 one price is overprinted inside its row's name (`Imported Round Scad 18N0O.0T0AVAILABLE`), so that item has no price and its name becomes a category (2 rows lost). The `RICE (per kg)` panel title sometimes chains into the rice sub-headings (`(per\nIMPORTED COMMERCIAL RICE`, 48 rows); `IMPORTED` / `LOCAL` stays in the category.

### Pork and chicken by market (`pork_by_market`, `chicken_by_market`, Dec 28, 2022 → Apr 18, 2024; checked on all 942 range pages of 314 reports)

One commodity per page: two pork pages (`FRESH & FROZEN PORK KASIM/PIGUE`, `… LIEMPO`) and one chicken page (`FRESH WHOLE CHICKEN`). Under `PRICE PER KILOGRAM (P/kg)` the header row starts with `MARKET` and names the columns: `Fresh` | `Frozen` for pork, `Fully-dressed, whole chicken` for chicken. The body reads like a `market_range` page, so `by_market.py` reuses that reader; the page heading becomes `commodity_raw` and the column header `specification_raw`. 36,730 rows, 13 to 35 markets per page.

- **Row numbers.** Markets are a numbered list (`1 New Las Piñas City Public Market`); the number is dropped so names match the `market_range` pages. A lone `#` (the number column's header, misplaced) under the last row of some 2024 pages gives no row.
- **Off-page text.** Seven pages carry another page's heading beyond the right edge of the page (`FRESH WHOLE CHICKEN` next to `… LIEMPO`). The table box ends inside the page, so it is left out.
- **Cells** are ranges (`320.00 - 340.00`, sometimes without the dash) or one marker in `price_prevailing_raw`: `N/A` (7,274), `n/m` / `N/M` (1,228, probably "not monitored"), `n/A`, `n/a`. Old-style `0.00` means missing (Jan 2023).
- **DA typos kept raw:** `3,700.00` for `370.00` (Dec 30, 2022), `N/A q`, and `0.00n/m0.00` (Dec 8, 2023).
- **Off-page titles.** On Nov 28, 2022 the chicken page also carries the pork page's title beyond its left edge, which used to type it `pork_by_market` (see "Text off the page" above).

### Prevailing pork and chicken by market (Sep 1, 2021 → Dec 27, 2022; checked on all 767 pages of 286 reports)

"Prevailing Retail Prices of Fresh and Frozen Pork Products / Whole Chicken in NCR Markets". Same table as above, but under `MARKET` each column splits into `Today` and the last report (`Yesterday`, `Last Friday`, `This Monday`, rarely `Last Monday`), with a row of dates below: `(Sept. 7, 2021)` until Aug 2022, then `September 01, 2022`. The two values are today's price and the last report's own price, not a range, so only today's is kept, in `price_prevailing_raw`, with `layout = "compare"`. `by_market.py` drops the characters of the sub-header rows and of the non-`Today` sub-columns, then reads the page like a range page. 28,535 rows; every page's values match pdfplumber's own text of its `Today` cells.

- **Markers:** `N/A` (6,009), `n/m` (395), `(-)` (358, "Closed due to disinfection"; kept raw, not split as a range), `#N/A` (13), `N/I` (5).
- **Header** is `MARKET*` on four Sep 2022 pages.
- Heading `FRESH & FROZEN LIEMPO` (without `PORK`) on 42 pages.
