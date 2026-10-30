# Project: Palengke Price Tracker

> Brief for Claude. Read this fully before writing code. When something here conflicts with what you find in the actual data or services, trust what you find, tell me, and propose an update to this file.
>
> v2 (2026-10-24): revised after Milestone 1 recon. Evidence for every change is in `docs/recon.md`; the original brief is in `docs/project_v1_original.md`.

## 1. What this is

A batch ETL pipeline built as a **medallion architecture** (bronze → silver → gold) that tracks retail food prices in the Philippines by combining:

1. **Official data:** Department of Agriculture (DA) Bantay Presyo price monitoring reports for Metro Manila markets, published as PDFs at `https://www.da.gov.ph/price-monitoring/` (daily since 2018).
2. **Enrichment:** PSA OpenSTAT. CPI is used to deflate prices and compare them against official inflation. PSA's monthly retail prices are used as a cross-check against DA.

The goal is **open data**. DA's prices are scattered across PDFs in many layouts, so this project turns them into one clean, standardized dataset that anyone can download. Gold tables are published as CSV and Parquet, with the data dictionary, on **GitHub Releases** (free, public, versioned), and are also loaded to **BigQuery**. My **Looker Studio** dashboard is a demo showing that the data is usable. It is not part of this repo.

It is also a **portfolio project** for data engineering and analytics roles. Code quality, reproducibility, documentation, and a clear analytical story matter as much as the pipeline working. It should show habits used in professional data teams: medallion layering, a tested transformation layer, a cloud warehouse, containerized runs, and CI.

## 2. Questions the gold layer must answer

- How have prices of key commodities (rice, pork, chicken, eggs, fish, vegetables) moved over time in Metro Manila markets (2018 → now)?
- Do individual DA markets track the NCR average, or diverge? By how much, and for which commodities? (For example **Bicutan Market, Taguig**, which DA monitors from 2021-10 on.)
- How large are seasonal spikes (Holy Week, Christmas, typhoon season)?
- How often do monitored prices exceed the suggested retail price (SRP/MSRP) in force on that date?
- In real (CPI-deflated) terms, which commodities got more expensive fastest?
- Do DA's daily figures agree with PSA's monthly retail survey?

## 3. Architecture

```
 DA website (PDFs)                                PSA OpenSTAT API
        │                                                │
        ▼                                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │  Ingestion (Python, runs in Docker)                          │
 │  discover → download → extract                               │
 └──────────────────────────────────────────────────────────────┘
        │
        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │  BRONZE  (local lake, kept in a GitHub Release)              │
 │  bronze/files/   original PDFs, CSV, JSON (immutable)        │
 │  bronze/tables/  extracted rows as text, + lineage, Parquet  │
 └──────────────────────────────────────────────────────────────┘
        │
        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │  dbt + DuckDB                                                │
 │  SILVER  typed, nulls handled, canonical commodities,        │
 │          units normalized, deduplicated, revisions resolved  │
 │  GOLD    facts, dimensions, analysis marts                   │
 └──────────────────────────────────────────────────────────────┘
        │
        ▼
 gold exported as Parquet ──load job──▶ BigQuery (palengke_gold)
                                              │
                                              ▼
                                   Looker Studio (built by me)
```

DuckDB is the only compute engine. BigQuery serves the gold layer only, so transformation logic is never duplicated in two SQL dialects. DuckDB is not persisted between runs: dbt rebuilds silver and gold from bronze each run (the data is small).

## 4. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Use `uv` for dependency management |
| PDF extraction | `pdfplumber` | Recon showed every era is text-based with extractable tables; no OCR, no camelot needed so far |
| Bronze storage format | Parquet via `pyarrow`, Hive-partitioned | |
| Lake storage | Local lake, copied to and from the `lake` GitHub Release (`tawad lake-push` / `lake-pull`) | Decided at milestone 5: GCS and R2 both need a card on file; Releases are free with no card. Daily runs pull only `bronze.tar` (~30 MB); PDFs are one `pdfs-YYYY-MM.tar` per report month |
| Transformations | dbt Core with `dbt-duckdb` | Reads bronze Parquet from the local lake |
| Cloud warehouse | BigQuery **sandbox** | Gold only, loaded via load jobs; see §6.7 for sandbox rules |
| Orchestration | GitHub Actions cron (daily) | Runs the pipeline inside the Docker image |
| Containers | Docker; image published to GitHub Container Registry (GHCR) | |
| CI | GitHub Actions on every pull request | Lint, tests, dbt build on fixtures, image build |
| Dashboard | Looker Studio, connected to BigQuery | Built by me, outside this repo |
| Testing | `pytest` for Python, dbt tests for models | |
| Lint / format | `ruff` | |

Do not add infrastructure beyond this list (Airflow, Terraform, Kafka, Spark, paid services) without asking me first.

## 5. Repository layout

```
tawad/                            # github.com/OrcaDS/tawad
├── project.md                    # this file
├── README.md                     # portfolio-facing write-up (see §12)
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── .dockerignore
├── docker-compose.yml            # local dev convenience (optional)
├── .env.example                  # every env var, with dummy values
├── config/
│   └── settings.py               # single source of config, reads env vars
├── .github/workflows/
│   ├── ci.yml                    # on pull_request
│   ├── daily_pipeline.yml        # on schedule
│   └── publish_image.yml         # on push to main: build + push to GHCR
├── pipeline/
│   └── cli.py                    # `tawad <subcommand>` entry point (Docker ENTRYPOINT)
├── ingestion/                    # everything that writes BRONZE
│   ├── da_prices/
│   │   ├── discover.py           # read price-monitoring page, list report URLs + series
│   │   ├── download.py           # fetch PDFs to bronze/files/, skip known hashes
│   │   ├── classify.py           # identify page type from title text
│   │   └── extract/              # one small extractor per layout (see §6.3)
│   ├── psa/
│   │   └── openstat.py           # CPI + retail price tables → bronze
│   └── common/
│       ├── storage.py            # read/write abstraction over the local lake
│       ├── lake_release.py       # push/pull the lake to the `lake` GitHub Release
│       └── manifest.py           # file manifest, hashes, revisions, extract status
├── warehouse/
│   ├── export_to_bigquery.py     # gold → Parquet → BigQuery load jobs
│   └── queries/                  # example analytical queries for the README
├── transform/                    # dbt project (SILVER + GOLD)
│   ├── profiles.yml              # uses env vars, no secrets
│   ├── models/
│   │   ├── sources.yml           # bronze Parquet as external sources
│   │   ├── silver/
│   │   └── gold/
│   ├── macros/                   # e.g. parse_price(), parse_range()
│   ├── seeds/
│   │   ├── commodity_map.csv     # raw name (+ category header, spec) → canonical commodity
│   │   ├── markets.csv           # DA market names/aliases → canonical market, city
│   │   └── srp_history.csv       # SRP/MSRP with valid_from / valid_to
│   └── tests/
├── tests/
│   ├── fixtures/
│   │   ├── pdfs/                 # one small sample PDF per layout era
│   │   └── parquet/              # tiny sample bronze for CI dbt runs
│   ├── test_extract.py
│   ├── test_settings.py
│   └── test_storage.py
└── docs/
    ├── architecture.png
    ├── recon.md                  # milestone 1 findings
    ├── parsing_notes.md          # layout eras, format quirks, changes over time
    └── data_dictionary.md        # every gold table and column, for Looker Studio
```

## 6. Pipeline stages

### 6.1 Discover and download (DA) → bronze/files
- One request to `https://www.da.gov.ph/price-monitoring/` lists every report PDF (~3,400 links, no pagination).
- Classify each link into a series from its page section and filename family: `price_watch` (2018–2019), `retail_monitoring` (2019-09 → 2020-01) and `price_monitoring` (2019-10 → now) under Daily Retail Price Range, plus `daily_index` and `weekly_avg`. Skip cigarette reports. Weekly reports use the week's last day as the report date. Filenames are inconsistent (typos, `-DPI-AFC` variants, several date formats), so confirm the series and report date from the PDF's title text after download.
- **Take the report date from the filename and the title, never from the upload folder** (e.g. Dec 2018 reports sit in `uploads/2019/02/`).
- Write each PDF untouched to `bronze/files/da/<series>/year=YYYY/month=MM/<original_filename>`, and record source URL, download timestamp, file hash, series, report date, revision rank, and status in the manifest.
- **Revisions:** `Revised-…`, `2nd-Revision-…`, `Updated-…`, `Final-Version` files replace the original for the same series and date. DA swaps the link on the page rather than listing both, so the manifest keeps every file ever seen and ranks revisions across all of them. Keep all files in bronze; silver keeps only the latest revision.
- Downloads must be idempotent: skip files whose hash is already in the manifest.
- Be polite: descriptive User-Agent (no personal email), 5 s between requests, never parallel requests.
- Backfill: support a `--since YYYY-MM-DD` flag. Target: everything back to 2018-02.

### 6.2 Bronze layout
- `bronze/files/`: original source files, never modified or deleted by the pipeline.
- `bronze/tables/`: extracted rows **as text, exactly as they appear**, plus lineage. No type conversion and no cleaning here.
  ```
  bronze/tables/da_prices/year=2026/month=10/part-<series>-<report_date>-r<revision>.parquet
  bronze/tables/psa_cpi/<table_id>.parquet        # e.g. 0012M4ACP22
  bronze/tables/psa_retail/<table_id>.parquet     # 0042M4ARN01 … 0042M4ARN11
  ```
  Each PSA pull returns a table's whole history, so each table is one file, overwritten by the next pull (Philippines and NCR rows only, one row per cell).
- Writes must be idempotent: re-extracting a report overwrites its own file, never appends duplicates.
- Define an explicit `pyarrow` schema per dataset (no schema inference). Use snappy compression.
- `ingestion/common/storage.py` works on the local lake only, so tests and local dev never need credentials. `ingestion/common/lake_release.py` copies the lake to and from the `lake` GitHub Release (deterministic tars, re-uploaded only when their sha256 changes; every PDF is checked against its manifest hash before upload).

### 6.3 Extract (DA PDFs → bronze/tables)
Recon (`docs/recon.md` §2) mapped the layout eras by quarterly sampling. There are about 8 page types, each recognizable from its title line:

| Era | Dates (approx.) | Shape | Prices |
|---|---|---|---|
| A. Per-market matrix | 2018-02 → 2019-07 | commodities × named markets × (prevailing, low, high) + NCR columns | per market + NCR |
| B. NCR summary | 2019-10 → 2021-07 | one row per commodity, unit column; column order changes; 2020-01..04 also has a per-market page | NCR (+ per market early 2020) |
| C1–C4. Report packets | 2021-10 → now | several page types per file: NCR summary (often two tables side by side), per-market matrix (ranges, later single values), pork / whole chicken by market (2021–2024), stall-count pages (skip), infographics (skip) | per market + NCR |
| D. Daily Price Index | 2025-04 → now | commodity, specification, (unit), prevailing | NCR |
| E. Weekly average | 2023-08 → now | commodity, specification, unit, weekly average | NCR |

Known gaps in DA's archive: 2018-04 → 2018-09 and 2020-05. No date has reports from more than one daily-range series (checked 2026-10-24), so no series priority rule is needed.

- `classify.py` picks the extractor for each **page** from its title text. Each extractor returns rows of raw cell text.
- Bronze row: `report_date`, `series`, `layout`, `page_type`, `market_raw` (NULL for NCR rows), `category_header_raw`, `commodity_raw`, `specification_raw`, `unit_raw`, `price_low_raw`, `price_high_raw`, `price_prevailing_raw`, `price_average_raw`, `markets_covered`, `source_file`, `page`, `revision_rank`, `extractor_version`, `ingested_at`.
- Map columns **by header text**, not position, wherever headers are readable (era B swaps column order between 2019 and 2021).
- If a PDF or page can't be extracted, mark it `failed` in the manifest with the reason and continue. Never silently drop a file.
- Record every format change discovered in `docs/parsing_notes.md`.

### 6.4 Primary data (dropped 2026-10-28)
My own weekly prices were dropped: DA already monitors Bicutan Market, so they would mostly repeat DA, as a tiny sample, at a weekly cost. Section number kept so references stay valid.

### 6.5 PSA OpenSTAT
- API: PXWeb v1 at `https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/...`. **Request `"format":"csv"`** (json-stat2 returns broken output). `.` = missing. Read value codes from table metadata; they are not always positional.
- Tables: CPI `2M/PI/CPI/2018NEW/0012M4ACP22.px` (2018=100, monthly, NCR + national; all items, food, rice, meat, eggs, …) and retail prices `2M/2018NEW/0042M4ARN01–11.px` (monthly, NCR). Exclude the `Ave`/`Annual` periods. Pull weekly; data lags about one month.
- Attribute PSA as the source in the README and the data dictionary (to show in Looker Studio), as its license requires.

### 6.6 Transform (dbt + DuckDB): silver and gold
- Declare bronze Parquet as dbt sources using `read_parquet(..., hive_partitioning = true)` through `dbt-duckdb` external sources.
- **silver:**
  - One `stg_` model per source: typed, renamed. All missing-value tokens (`n/a`, `N/A`, `#N/A`, `#DIV/0!`, `-`, `NONE`, `NOT AVAILABLE`, `0`/`0.00` in eras A and C, `0.00 -0.00`, blank) → NULL, never 0. Ranges like `50.00 -68.00` split into low/high; spaces inside numbers removed (`5 0.00` → 50.00); footnote markers stripped. Done in tested macros.
  - Keep only the latest revision per (series, report date).
  - Canonical commodity via `commodity_map.csv`, keyed on (category header, commodity, specification), because imported vs local rice is only in the header and names drift even within one era. **Category comes from the seed, never from PDF headers** (weekly reports file pork under "BEEF PRODUCTS").
  - Canonical market via `markets.csv` (names get truncated or vary).
  - Unit normalization to per kg where possible; otherwise keep the native unit (eggs per piece, cooking oil per bottle: recon shows oil is priced per bottle despite the footnote). Columns `unit_normalized`, `is_per_kg`.
  - Headline price: `price` = prevailing; if NULL, the midpoint of low/high. `price_basis` ∈ {`prevailing`, `midpoint`, `average`, `single`}. Keep low/high for range bands.
- **gold** (designed for Looker Studio: friendly column names, one clear grain per table, pre-computed metrics):
  - `fct_prices`: one row per date × source × series × location × commodity × specification. Includes `price`, `price_basis`, `price_low`, `price_high`, week-over-week change.
  - `dim_commodity`: canonical name, category, origin (local/imported).
  - `dim_location`: DA markets and the "NCR (aggregate)" location. City and source type (DA / PSA).
  - `dim_date`: calendar with PH holiday and season flags (Holy Week, Christmas season, typhoon season).
  - `fct_srp_compliance`: each observation joined to the SRP in force **on that date** from `srp_history.csv`. SRP is never a static column (pork MSRP started Mar 2025, was suspended May 2025, and came back Dec 2025 at new levels).
  - `mart_real_prices`: **monthly** grain. Real price = nominal ÷ all-items CPI (NCR). Also compare each commodity against food CPI.
  - `mart_da_vs_psa`: monthly DA average vs PSA retail price for matching commodities.
- `docs/data_dictionary.md` documents every gold table and column, including the source attribution text to show in Looker Studio.

### 6.7 Load gold to BigQuery (sandbox)
- `warehouse/export_to_bigquery.py`:
  1. Exports each gold model from DuckDB to Parquet (`COPY ... TO ... (FORMAT parquet)`).
  2. Hashes each export (rows in a fixed order). **Loads a table only when it is missing, its hash changed and its last load is ≥ 28 days old (monthly, decided 2026-10-28), or it expires within 10 days.** `--force` reloads all. The hash is kept in the table description and cumulative bytes loaded in a dataset label, so no state file is needed.
  3. Load job with `WRITE_TRUNCATE` into dataset `palengke_gold`.
- Sandbox rules (verified 2026-10-24, see recon §4):
  - Storage is a **lifetime** 10 GiB that deletions don't give back, so every reload uses up part of it. Keep gold small and log the cumulative bytes loaded.
  - Tables and partitions expire after 60 days, hence the forced reload.
  - **No time partitioning on `fct_prices`**: the 60-day partition expiry would delete history. `fct_prices` and `fct_srp_compliance` are clustered by `commodity_id` (no partitioning). Each load sets the table to expire in 59 days.
  - No DML or streaming. Load jobs only.
  - Load gold from local files (no bucket).
- Use a dedicated service account with only the roles it needs.
- After loading, run a row-count check comparing DuckDB gold against each table loaded in that run and fail the run on mismatch (skipped tables are behind on purpose).
- Add 3–4 example analytical queries in `warehouse/queries/` for the README.

### 6.8 Data quality
Required dbt tests: `not_null` and `unique` on keys, accepted values for categories, and relationships between facts and dimensions. Custom checks:
- Prices fall within plausible bounds per commodity, so the pipeline flags outliers (e.g. ₱5/kg pork) rather than dropping them.
- Every commodity in bronze maps to a canonical commodity; an unmapped name fails the run and prints the name so I can add it to the seed. Same for markets.
- A freshness check warns if no new DA report has arrived in more than 7 days.
- The DuckDB-vs-BigQuery row-count reconciliation from §6.7.

## 7. Containerization

- One `Dockerfile` for the pipeline (ingestion, dbt, export).
- Multi-stage build: install dependencies with `uv` in a builder stage; copy only what's needed into a slim Python runtime stage.
- Run as a non-root user. No secrets baked into the image; everything comes from env vars at runtime.
- Pin the base image to a specific version tag.
- Single entrypoint with subcommands, e.g.:
  ```
  docker run --env-file .env ghcr.io/<me>/tawad-pipeline:latest run-all
  docker run ... ingest-da --since 2018-02-01
  docker run ... transform
  docker run ... export-bq
  ```
- `docker-compose.yml` (optional) mounts a local `./lake` directory so the full pipeline runs offline against local storage.
- `.dockerignore` excludes the lake, DuckDB files, `.env`, caches, `recon_samples/`, and fixtures not needed at runtime.

## 8. CI/CD and orchestration

### 8.1 `ci.yml` (on every pull request)
1. `ruff check` and `ruff format --check`.
2. `pytest` (extractor tests run against `tests/fixtures/pdfs/`, one per layout era).
3. `dbt build` against the tiny fixture bronze in `tests/fixtures/parquet/` using local storage, with no cloud credentials.
4. `docker build` to confirm the image still builds.

The PR must not be mergeable if any step fails. CI must never touch the `lake` release or BigQuery.

### 8.2 `publish_image.yml` (on push to `main`)
Build the image and push to GHCR, tagged with the commit SHA and `latest`.

### 8.3 `daily_pipeline.yml` (scheduled)
- Runs daily at about 10:00 PHT (02:00 UTC), plus manual `workflow_dispatch`.
- Pulls the GHCR image and runs `run-all`: discover → download → extract → PSA (weekly) → `dbt build` → export gold to BigQuery (if changed) → publish gold to a GitHub Release (if changed) → reconciliation.
- No DuckDB file is persisted between runs; the `lake` release is the only state (`tawad lake-pull` at the start, `tawad lake-push` after a successful build). The release is never marked latest, so "latest" stays the open data.
- Secrets (service account JSON) live in GitHub Actions secrets, never in the repo. Release uploads use the workflow's `GITHUB_TOKEN` (`contents: write`).
- GitHub disables scheduled workflows in public repos after 60 days without repo activity. Document this in the README; re-enable as needed.

## 9. Dashboard (Looker Studio — built by me)

I build the dashboard in Looker Studio, connected directly to `palengke_gold` in BigQuery. Claude's job is to make the gold layer easy to chart:
- Every gold table has one documented grain, readable column names, and pre-computed metrics, so Looker Studio needs no complex calculated fields.
- Peso amounts stored as numbers (formatting ₱ happens in Looker Studio); dates as `DATE`.
- `docs/data_dictionary.md` lists each table, column, meaning, and the DA/PSA attribution text.
- A `meta_last_refresh` table records when each gold table was last loaded, for an "as of" note on the dashboard.

Planned pages (for reference): Overview, Trends with seasons shaded, Market vs NCR average, SRP compliance, Real prices, About/sources.

## 10. Conventions

- Use type hints on all functions, and give each module a short docstring explaining its purpose.
- Write small, testable functions. Extractor logic must have tests against fixture PDFs.
- Use the `logging` module, never bare `print`, in pipeline code.
- All config (URLs, dataset names, date ranges) comes from `config/settings.py`, which reads env vars. Every variable is listed in `.env.example`.
- Commit messages should be short and imperative ("Add DA extractor for 2023 range packet").
- Work on feature branches and merge through pull requests so CI history is visible in the repo.
- Never commit data files (PDFs, Parquet, DuckDB) except the small fixtures. `recon_samples/` is git-ignored.

## 11. Milestones

Work through these in order. At the end of each, stop, summarize what was done, and wait for my review.

1. **Recon** (done 2026-10-24, see `docs/recon.md`): DA PDFs and layout eras, OpenSTAT, free tiers.
2. **Project skeleton:** repo layout, `uv` setup, config, storage abstraction (local mode only), Dockerfile, and `ci.yml` running on an empty test suite.
3. **DA ingestion → bronze:** discover, download, classify, extract into local partitioned Parquet, with tests per era. Backfill everything back to 2018 locally.
4. **Silver + gold dbt models** for the DA data reading the local bronze, with tests passing in CI against fixtures.
5. **Lake storage:** keep the lake in a GitHub Release (no card needed; chosen over GCS/R2 on 2026-10-28), migrate the local lake, and confirm dbt builds from a pulled copy.
6. ~~Primary data~~ (dropped 2026-10-28, see §6.4).
7. **PSA enrichment:** CPI and retail prices; real-price and DA-vs-PSA marts.
8. **BigQuery export** with sandbox rules, reconciliation, and example queries.
9. **Automation:** `publish_image.yml` and `daily_pipeline.yml` running end to end in the container, including publishing gold as open data (CSV + Parquet + data dictionary) to a GitHub Release.
10. **Looker Studio handoff:** data dictionary finalized, `meta_last_refresh`, a check that every planned dashboard page can be built from gold. I build the dashboard.
11. **Portfolio polish:** README, architecture diagram, and 3–5 written findings.

## 12. README (portfolio-facing) must include

- A one-paragraph summary of the project and why it matters.
- An architecture diagram showing bronze → silver → gold → BigQuery → Looker Studio.
- A link to the Looker Studio dashboard and a screenshot.
- Data sources with attribution and licenses.
- How to download the open data (latest GitHub Release), plus:
  - Attribution: "Source: Department of Agriculture Bantay Presyo reports. Cleaned and standardized by tawad. Not an official DA product." No DA logo or branding.
  - Disclaimer: provided as is; DA's own typos are kept and flagged (`is_outlier`), and parsing may contain errors.
  - Licenses: code MIT; DA-derived tables are Philippine government data (no copyright under RA 8293 §176; commercial users should check with DA); PSA data under PSA's terms.
- 3–5 concrete findings, each backed by a chart.
- Engineering challenges solved: PDF format drift across ~5 layout eras, messy missing-value tokens, report revisions, commodity and market name standardization, unit normalization, idempotent partitioned writes, keeping CI free of cloud credentials, working within BigQuery sandbox limits.
- Example BigQuery queries and what they show.
- CI and container badges (build status, image).
- Limitations: DA coverage is Metro Manila only, per-market DA data covers only some years and commodities, and some prices are ranges rather than single values.
- How to run it locally, both with `uv` and with Docker.
- A short "design decisions" section: why medallion layering, why DuckDB does the transformations and BigQuery only serves gold, why the sandbox.

## 13. Things to ask me about rather than assume

- Creating any cloud resource (BigQuery dataset, service account, GitHub Release) or anything that could cost money.
- Any new dependency beyond the stack above.
- Commodity mappings that are ambiguous (e.g. rice grades, local vs imported, pork cuts).
- Whether to drop or keep data from a PDF layout that only partially extracts.
- Series priority when two DA reports cover the same date and commodity.
