# Milestone 1 — Recon findings

Checked 2026-10-24. Every claim cites where it came from. Section 2 (PDF layouts) is pending sample PDFs.

## 1. DA price monitoring site

The page `https://www.da.gov.ph/price-monitoring/` is one ~800 KB page that links all 3,386 PDFs directly (no pagination), so link discovery is a single request.

**Download approach:** the pipeline downloads DA PDFs automatically: sequentially, with a 5 s delay, using a descriptive User-Agent. This project is non-commercial. PSA OpenSTAT stays in for CPI and as a second official monthly price series.

### Report series on the page

The page groups links under four headings: *Daily Retail Price Range*, *Daily Price Index*, *Weekly Average Retail Prices*, *Daily Cigarette Price Monitoring*.

| Series (filename pattern) | Files | First → last upload | Likely content |
|---|---|---|---|
| `Price-Watch-<Month>-<D>-<YYYY>.pdf` | 197 | 2018-02 → 2019-10 | Older daily report |
| `RETAIL-Price-Monitoring-Sum-Market_<DDMONYY>.pdf`, `RETAIL...Report_...`, `Retail-Price-Monitoring-...` | ~18 | 2019-09 → 2020-01 | Transitional format |
| `Price-Monitoring-<Month>-<D>-<YYYY>.pdf` | ~1,900 | 2019-10 → 2026-10 | Daily retail price **range** (low–high) |
| `Daily-Price-Index-<Month>-<D>-<YYYY>.pdf` | ~570 | 2025-04 → 2026-10 | Daily **prevailing** price |
| `Weekly-Average-Prices-<range>.pdf` | ~160 | 2023-08 → 2026-10 | Weekly averages |
| `Daily-Cigarette-Price-Monitoring-...` | ~500 | 2025-03 → 2026-10 | Out of scope |

Uploads per year: 2018: 54 · 2019: 219 · 2020: 219 · 2021: 251 · 2022: 255 · 2023: 274 · 2024: 337 · 2025: 872 · 2026: 905.

### Quirks that affect the design

- **Revisions.** About 70 files are `Revised-…`, `…-Revised`, `2nd-Revision-…`, `Updated-…`, `Final-Version`. A revised report replaces the original for the same date and series. The manifest needs `series`, `report_date` and `revision_rank`, and parsed output keeps only the latest revision per (series, date).
- **The report date must come from the filename, not the upload folder.** For example, December 2018 reports are in `uploads/2019/02/`.
- **Filenames are inconsistent:** typos (`Price-Monitrong`, `Octermber`, `Weeky`), suffixes like `-1`, `_2`, and several date formats (`March-01-2021`, `04SEPT19`, `DailyApril042018`). Date parsing needs tests for each pattern.
- **Low/high and prevailing come from different documents** since 2025 (Price-Monitoring vs Daily-Price-Index). Before 2025, prevailing may not exist at all. To confirm with samples.
- The project.md target `landing/da/YYYY/MM/` should use the report date, with the source URL kept in the manifest.

## 2. DA PDF layouts

Inspected 2026-10-24: 13 samples in `recon_samples/` (git-ignored), covering 2018-02 → 2026-10. Tool: pdfplumber 0.11.10.

**Bottom line: automated extraction works for every era.** All 13 files are text PDFs from Excel or Word, so no OCR is needed, and `extract_tables()` returns usable grids. The work is in handling **about 5 layouts** and spotting the right page types inside multi-page packets. The exact dates when one layout changes to the next are still unknown (see the bisection step in §6).

### Layout eras (dates are from the samples; boundaries not yet pinned down)

| Era | Seen in | Shape | Prices given | Parser notes |
|---|---|---|---|---|
| **A. Per-market matrix** | 2018-02-01, 2018-04-04, 2019-09-04 | 1–2 landscape pages. Rows = commodities; columns = **10 named markets** (5 by Sep 2019) × (prevailing, low, high), plus an NCR prevailing/low/high/average | Per market + NCR | Header words are split (`revailin`/`gLow`), so map columns by position under the market names. **`0` and `0.00` mean missing**, as do `N/A`, `#N/A`, `#DIV/0!`. Digits are split by spaces (`5 0.00` = 50.00), so strip spaces inside numbers. |
| **B. NCR summary** | 2019-10-09, 2019-10-10, 2021-03-01 | Portrait. One row per commodity with a `kg` unit column | NCR only: 2019 = prevailing/low/high/average; **2021 = high/low/prevailing (order changed)** | **Map columns by header text, not position.** `NOT AVAILABLE` / `NONE` → NULL. Page 2 (2021) is an infographic duplicating page 1, so skip it. "PRELIMINARY REPORT as of 6:00 AM" means revisions are likely. |
| **C. Range packet** | 2023-12-01, 2025-03-01, 2026-10-09 | 5–6 landscape pages of different page types: an infographic poster (skip); **per-market range matrix** (rows = 16–35 markets, columns = 4–12 key commodities); 2023 has a **per-market pork page** (fresh vs frozen kasim/pigue); 2025+ has an **NCR summary** with low, high, prevailing and average, laid out as two tables side by side | Per market (ranges or single values) + NCR | Classify each page by its title line. Ranges come as `50.00 -68.00` / `75.00- 100.00` / `320.00-360.00`. `0.00 -0.00` = missing. Footnote markers (`a`, `b`, `*`, `**`) are attached to names or values. The side-by-side tables must be split by column position. Market names are truncated in table cells, so read them from text or map them to a market seed. |
| **D. Daily Price Index** | 2025-04-10, 2026-10-07 (revised), 2026-10-24 | Word, portrait, 3–8 pages. NCR prevailing only, ~200 items | NCR prevailing | 2025-04 has a `UNIT` column and a different title format. In 2026 the table sometimes comes out with 9 columns of which most are empty, so collapse the empty ones. Details in the current-era notes below. |
| **E. Weekly average** | 2026-10-12..18 | Excel, 3 pages | NCR weekly average | Details below |

### Era boundaries (quarterly bisection, 2026-10-24)

Sampled the first daily range report of every quarter, 2018-Q1 → 2026-Q4: 34 files in `recon_samples/quarterly/`. Fingerprints (page count, producer, each page's title and table shape) are in scratchpad `recon/fingerprints.txt`. Boundaries are accurate to about one quarter.

| Era | Dates (approx.) | Page types inside each file (by title) |
|---|---|---|
| A. Per-market matrix | 2018-02 → 2019-07 | "DAILY PRICE MONITORING REPORT": one matrix of commodities × markets × (prevailing, low, high). Number of market columns varies (15–36 table columns). |
| B. NCR summary | 2019-10 → 2021-07 | "DAILY PRICE MONITORING" / "Retail Prices … in Selected Markets": NCR summary (6 columns). **2020-01 to 2020-04 also have a per-market matrix page** (63×42). Last page is an infographic (skip). |
| C1. Prevailing packet | 2021-10 → 2022-10 | "Prevailing Retail Prices … at NCR Markets" (side-by-side tables), "… per Market" (small matrix), "… Fresh and Frozen Pork … in NCR Markets", from 2022 "… Whole Chicken in NCR Markets", and **stall-count/percentage pages** ("*Percentage excludes stalls…") that hold counts, not prices (skip). |
| C2. Range packet | 2023-01 → 2025-01 | "Retail Price Range … at NCR Markets" (poster layout), "… per Market" (range matrix), pork and whole chicken pages until 2024-04. From 2024-07 just 2 pages. |
| C3. Per-market + NCR summary | 2025-04 → 2026-07 | 3 × "Retail Price Range … per Market" + 3 × "Retail Price of … at NCR Markets" (low, high, prevailing, average). |
| C4. Prevailing per market | 2026-09/10 → now | "Prevailing Retail Price Range … per Market": single values, 10–11 commodity columns, 3 pages + 3 NCR summary pages. |
| D. Daily Price Index | 2025-04 → now | Separate file series (see current-era notes). |
| E. Weekly average | 2023-08 → now | Separate file series. |

About **8 distinct page types**. Each one is recognizable from its title line, so a title-based classifier is reliable.

### Coverage (distinct report dates per month, range series)

```
      Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec
2018    0  18  15   0   0   0   0   0   0  14  13  10
2019   12  11  13  12  13  11  16  18  22  27  23  22
2020   26  23  23   7   0  20  22  19  21  21  18  17
2021   20  20  23  20  20  22  21  22  22  21  21  21
2022   21  19  23  19  21  22  21  23  21  21  21  22
2023   22  20  23  17  23  22  21  23  21  22  21  20
2024   22  21  19  22  27  25  27  27  25  27  25  25
2025   26  24  26  23  27  25  27  26  26  27  25  27
2026   27  24  25  26  26  26  30  31  30  23   –   –
```

- **Gaps:** 2018-04 → 2018-09 (nothing published) and 2020-05 (none, likely COVID lockdown; April is thin too). Holy Week 2018 (late March) is covered. The dashboard should show gaps as gaps, not interpolate across them.
- Reports came roughly every other day in 2018–2019, on weekdays from 2021, and daily including weekends from 2024.
- Late 2019 has **overlapping series for the same dates** (Price-Watch, RETAIL-…, Price-Monitoring). Silver needs a priority rule for duplicate (date, commodity, location) rows across series.

### Bicutan Market (Kurt's palengke, Taguig)

- In DA's DPI and weekly market lists (2025–2026).
- In per-market pages **from 2021-10**: pork and whole chicken pages 2021-10 → 2024-04, then the main per-market commodity matrix from 2024 (rice, fish, eggs, vegetables). It's absent from the 2018–2021 matrices.
- → `mart_local_vs_official` can compare Kurt's prices with **DA's own Bicutan Market numbers** for the commodities DA lists there, and use the NCR aggregate for the rest.
- Data quality example from the source itself: 2023-04-03 shows Bicutan `32.00` beside `330.00` for pork, almost certainly a typo for 320.00. That's why §6.8 flags outliers instead of dropping them.

### What this means for the design

- **Per-market DA data exists after all**, for 2018–2019 (10 markets, broad commodity list) and from about 2023 on (16–35 markets, ~10–20 key commodities). So `dim_location` should have real DA markets *plus* an "NCR (aggregate)" row. If your palengke is close to a monitored market, `mart_local_vs_official` can compare against that market, not only the NCR average.
- The NCR summary with low/high/prevailing runs through every era. That's the backbone series for long-run trends and seasonality back to 2018.
- The parser should be a set of small page parsers (`matrix_2018`, `ncr_summary`, `market_range`, `dpi`, `weekly`) with a classifier that picks one by title text. Each one gets a fixture PDF and tests.
- Missing values are messy in older eras (`0`, `#N/A`, `NONE`, `NOT AVAILABLE`, `0.00 -0.00`). One shared `to_price()` function with exhaustive tests turns them all into NULL, never 0.
- Grain for `fct_prices`: date × source × series × location (market or NCR) × commodity × spec, plus `price_low` / `price_high` / `price_prevailing` / `price_average`.

### Current era in detail (DPI + weekly, 2025–2026)

Notes from the first two files Kurt downloaded: `October-24-2026-DPI-AFC.pdf` and `Weekly-Average-Prices-October-12-18-2026.pdf`. Prototype output: scratchpad `recon/proto_output.txt`.

### Daily Price Index (2025-04 → now)

- **Text PDF** made in Microsoft Word: 8 pages, A4, no images. No OCR needed.
- Title: `DAILY PRICE INDEX / National Capital Region (NCR) / (Saturday, October 24, 2026) / Prevailing Retail Price of Agri-fishery Commodities in Selected Wet Markets`. Take the report date from this title line and cross-check it against the filename.
- **One NCR-wide price per item, not per market.** "Prevailing price … computed as the average price using arithmetic mean formula" across the **33 covered markets** listed in the footnote. There is no low/high and no SRP column.
- Columns: `COMMODITY | SPECIFICATION | PREVAILING RETAIL PRICE PER UNIT`. `page.extract_tables()` returns a clean 3-column table on every page. Each page also has a second junk "table" (header fragment) that is discarded.
- Category header rows are ALL CAPS with an empty price (`IMPORTED COMMERCIAL RICE`, `PORK MEAT PRODUCTS`, …, 14 categories). Rice is split into **imported vs local** by these headers, and the item names don't say which, so the parser must carry the header into each row.
- 208 item rows; 48 (23%) are `n/a` ("not available in the market") → NULL.
- Origin is often inside the name (`Pork Belly (Liempo), Local` / `, Imported`) and brand sometimes in the spec (`Chicken Breast, Local | Magnolia`).
- Wrapped specs arrive as `"Medium (8-10 cm diameter/bunch\nhd)"` → join with a space.
- Footnote units: per kg, except **eggs per piece**. It says cooking oil is "Peso per Liter", **but the weekly report shows the 350 ml bottle at ₱40 (unit `ml`) next to the 1 L bottle at ₱102**. So the oil prices are per bottle; normalize by bottle size.
- Some characters are mis-encoded in extraction (`Pi�as`, `Mu�oz`) → normalize text and test for it.
- Filenames vary: usually `Daily-Price-Index-<Month>-<D>-<YYYY>.pdf`, sometimes `<Month>-<D>-<YYYY>-DPI-AFC.pdf` (4 so far). **Identify the series from the title text**, not only the filename.

### Weekly Average Prices (2023-08 → now)

- Text PDF made in Microsoft Excel: 3 pages, Letter size.
- Columns: `COMMODITY | SPECIFICATION | UNIT | WEEKLY AVERAGE PRICE`, plus an empty leading column. **It has an explicit unit column** (`kg`, `pc`, `ml`, `L`).
- 100 item rows (a subset of the daily items, plus 11 egg sizes and `P20 Benteng Bigas Meron Na` Kadiwa rice at ₱20). 7 are `-` ("not sold") → NULL.
- **Category headers are unreliable.** Pork, chicken and egg rows sit under `BEEF PRODUCTS`, and there are no pork/poultry headers. → Assign category from the `commodity_map.csv` seed, never from PDF headers. Headers are used only for imported/local rice.
- It covers **36 markets**, while the daily covers 33 (the weekly adds Cartimar, Guadalupe, Pasay). Coverage differs between series and over time, so record the market count per report.
- Footnote superscripts end up in names (`Meron Naᵃ`) → strip them.
- Notes say series start mid-stream: "monitoring of basmati, japonica, and glutinous rice varieties started on November 17, 2025", "mungbean started on December 11, 2025". Before those dates the item is simply absent, which is different from n/a.
- Source line: "DA Agribusiness and Marketing Assistance Service (DA-AMAS)". Use it for attribution.

### Naming drifts even within the current era

Daily `Basmati Rice` / `Glutinous Rice` / `Jasponica/Japonica Rice` vs weekly `Basmati` / `Glutinous` / `Japonica/Jasponica`. `commodity_map.csv` is keyed on (category header, commodity, specification) and has to absorb these differences even inside DA.

### What this means for the plan

- DPI and weekly rows go to the "NCR (aggregate)" location. (Per-market rows from eras A and C go to real markets; see above.)
- Add to the DA row schema in project.md §6.3: `series` (`daily_index` | `weekly_avg` | `ncr_summary` | `market_range`), `origin` (local/imported), `unit_raw`, `markets_covered`, `price_average`. Keep `market` (NULL for NCR aggregate rows).
- pdfplumber is enough for the current era; camelot isn't needed so far.

## 3. PSA OpenSTAT

`https://openstat.psa.gov.ph/robots.txt`: `User-agent: *` → `Allow: /`, with `Content-Signal: search=yes,ai-train=no,use=reference`. AI-training crawlers are blocked. A data pipeline is fine.

API: PXWeb v1, `https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/...`. GET a table for its metadata, POST a query to get data.

- **Use `"format":"csv"`.** `json-stat2` returned one bogus value (`[1.0]`) for a 40-cell query.
- Missing values come back as `.` and must become NULL.
- Value codes are not always positional. Geolocation uses PSGC-style codes (NCR = `130000000` in retail tables, `1` in the CPI table). Always read codes from the table metadata.

### Tables to use

| Purpose | Path | Coverage |
|---|---|---|
| CPI by commodity group, 2018=100 | `2M/PI/CPI/2018NEW/0012M4ACP22.px` | Monthly, Jan 2018 → Sep 2026. PH + NCR + regions/provinces. Includes `0 - ALL ITEMS`, `01.1 - FOOD`, `01.1.1.12 - Rice`, `01.1.2 - Meat`, `01.1.4.8 - Eggs`, … (354 groups). Has an `Ave` period to exclude. |
| CPI backcast 1994–2017 | `2M/PI/CPI/2018NEW/0012M4ACP28.px` | Not needed unless DA data before 2018 is used |
| Retail prices of agricultural commodities (11 tables: cereals, rootcrops, beans, condiments, fruit veg, leafy veg, fruits, commercial crops, livestock, poultry, fish) | `2M/2018NEW/0042M4ARN01.px` … `0042M4ARN11.px` | **Monthly**, 2018 → Sep 2026 (about 1-month lag). PH + NCR + regions/provinces. Clean specs, e.g. `RICE, WELL-MILLED, 1 KG`, `FRESH PORK, KASIM, 1 KG`. Has an `Annual` period to exclude. |

Sample check (NCR, `FRESH PORK, KASIM, 1 KG`): Jan 2018 ₱262.34 → Jun 2025 ₱395.83 → Sep 2026 ₱336.42; Oct 2026 = `.`.
Sample check (CPI, NCR all items): Jan 2025 124.9 → Sep 2026 133.0; NCR food Sep 2026 140.9.

"(ND)" in CPI group labels does **not** mean no data. Those rows have values. Meaning still unknown.

Attribution: responses carry `"source": "Philippine Statistics Authority (PSA)"`. Credit PSA in the README and the dashboard.

**Effect on the plan:** with automated downloads, DA daily data is the main official series. PSA monthly retail prices are a cross-check and a fallback for gaps in DA coverage. They also offer a nice analysis: does DA's daily average agree with PSA's monthly survey?

## 4. Free tiers (pages checked 2026-10-24)

| Service | Free allowance | Catch |
|---|---|---|
| GCS ([source](https://docs.cloud.google.com/free/docs/free-cloud-features), updated 2026-10-22) | 5 GB-month, 5,000 Class A ops, 50,000 Class B ops, 100 GB egress/month | Only `us-east1`, `us-west1`, `us-central1`. Needs a billing account. |
| Cloudflare R2 ([source](https://developers.cloudflare.com/r2/pricing/), updated 2026-10-01) | 10 GB-month, 1M Class A, 10M Class B, egress free | Standard storage only. No direct BigQuery load. |
| BigQuery free tier (same Google source) | 10 GiB storage/month, 1 TiB queries/month | Needs a billing account |
| **BigQuery sandbox** ([source](https://docs.cloud.google.com/bigquery/docs/sandbox), updated 2026-10-22) | No card. 1 TiB queries/month | **Lifetime 10 GiB storage, "not refunded upon data deletion."** Tables, views and partitions expire after 60 days. No DML, streaming or Data Transfer Service. The page doesn't say whether loads from GCS work. |
| GitHub Actions ([source](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow)) | — | "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." |

Streamlit Community Cloud limits: not checked yet. Check at milestone 10.

**Decision (2026-10-24): BigQuery sandbox, loading only when marts change.** Consequences for §6.7:

1. Hash each exported mart and run the load job only when the hash changes. Every reload uses up lifetime storage quota.
2. Tables expire 60 days after they're created or last loaded, so force a reload if the last load is more than ~50 days old.
3. **Don't time-partition `fct_prices` by `price_date` in the sandbox.** The 60-day partition expiration works off the partition date, so history older than 60 days would be dropped. Use clustering only, or integer-range partitioning on a `year_month` int (verify at milestone 8).
4. Estimate mart sizes once DA parsing works, and check that cumulative loads stay well under 10 GiB.

**Storage:** GCS is still recommended (direct BigQuery loads, same account). But whether sandbox BigQuery can load from a GCS bucket in a billing-enabled project needs checking before any bucket is created. If it can't, R2 plus loading from local files works just as well. **Decide at milestone 5.**

## 5. SRP / MSRP

DA price caps change over time. Examples found (search, 2026-10-24):

- Pork MSRP from March 2025: liempo ₱380, kasim/pigue ₱350 ([3tres3](https://www.3tres3.com/en/latest_swine_news/the-philippines-to-implement-a-maximum-suggested-retail-price-for-pork_21225/))
- Suspended in May 2025 ([Inquirer](https://business.inquirer.net/?p=525309))
- Reinstated on 2025-12-05 in Metro Manila wet markets: liempo ₱370, kasim/pigue ₱330 ([search summary of DA release](https://www.da.gov.ph/gallery/da-dti-doh-fda-pnp-special-joint-price-supply-monitoring-at-mega-q-mart-december-5-2025/))
- Imported rice MSRP changed several times, e.g. ₱49 → ₱45 ([Malaya](https://malaya.com.ph/business/corporate/da-to-restore-pork-maximum-retail-price-by-jul-aug))

This confirms SRP needs a dated `srp_history` seed (`valid_from`/`valid_to`), not a column on `dim_commodity`. Still to check: whether the daily PDFs print the SRP next to each item. If they do, take it from there.

## 6. Open questions

- What does "(ND)" mean in PSA CPI labels?
- Does the BigQuery sandbox allow load jobs from a GCS bucket?
- ~~Is DA data per market or NCR-wide?~~ Both, depending on the era (§2).
- ~~When did DA start reporting a prevailing price?~~ Every era has one.
- None of the samples print SRP, so `srp_history.csv` is maintained by hand from DA orders.
- ~~Era boundaries~~ Done (§2). They're accurate to about a quarter; exact switch dates will show up as classifier failures during the milestone 3 backfill.
- ~~Nearest DA market~~ Kurt's palengke *is* DA-monitored Bicutan Market (§2).
- Ambiguous mappings: rice grades (regular/well-milled/premium/special, local vs imported), pork cuts. PSA and DA names will both go into `commodity_map.csv`.

## 7. Sample PDFs inspected

All in `recon_samples/` (git-ignored). #11 and #13 were **not** downloaded. Kurt supplied `October-24-2026-DPI-AFC.pdf` and `Weekly-Average-Prices-October-12-18-2026.pdf` in their place. The rest were downloaded automatically:

1. http://www.da.gov.ph/wp-content/uploads/2018/02/Price-Watch-February-1-2018.pdf
2. http://www.da.gov.ph/wp-content/uploads/2018/04/DailyApril042018.pdf
3. http://www.da.gov.ph/wp-content/uploads/2019/09/RETAIL-Price-Monitoring-Sum-Market_04SEPT19.pdf
4. http://www.da.gov.ph/wp-content/uploads/2019/10/Price-Watch-October-9-2019.pdf
5. http://www.da.gov.ph/wp-content/uploads/2019/10/Price-Monitoring-October-10-2019.pdf
6. https://www.da.gov.ph/wp-content/uploads/2021/03/Price-Monitoring-March-01-2021.pdf
7. https://www.da.gov.ph/wp-content/uploads/2023/12/Price-Monitoring-December-1-2023.pdf
8. https://www.da.gov.ph/wp-content/uploads/2025/03/Price-Monitoring-March-1-2025.pdf
9. https://www.da.gov.ph/wp-content/uploads/2025/04/Daily-Price-Index-April-10-2025.pdf
10. https://www.da.gov.ph/wp-content/uploads/2026/10/Price-Monitoring-October-9-2026.pdf
11. https://www.da.gov.ph/wp-content/uploads/2026/10/Daily-Price-Index-October-9-2026.pdf
12. https://www.da.gov.ph/wp-content/uploads/2026/10/Revised-Daily-Price-Index-October-7-2026.pdf
13. https://www.da.gov.ph/wp-content/uploads/2026/10/Weekly-Average-Prices-September-28-October-4-2026.pdf
