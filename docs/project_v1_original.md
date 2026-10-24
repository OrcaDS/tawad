# Project: Palengke Price Tracker

> Brief for Claude. Read this fully before writing code. When something here conflicts with what you find in the actual data or services, trust what you find, tell me, and propose an update to this file.

## 1. What this is

A batch ETL pipeline and dashboard that tracks retail food prices in the Philippines by combining:

1. **Official data:** Department of Agriculture (DA) Bantay Presyo daily price monitoring reports for Metro Manila markets, published as PDFs at `https://www.da.gov.ph/price-monitoring/`.
2. **Primary data:** prices I collect myself every week at my local palengke and sari-sari store, entered through a Google Form that writes to a Google Sheet.
3. **Enrichment:** PSA OpenSTAT (CPI and regional inflation), used to deflate prices and compare them against official inflation.

This is a **portfolio project** for data engineering and analytics roles. Code quality, reproducibility, documentation, and a clear analytical story matter as much as the pipeline working. The project should demonstrate habits used in professional data teams: a lake-style raw layer, a tested transformation layer, a cloud warehouse, containerized runs, and CI.

## 2. Questions the dashboard must answer

- How have prices of key commodities (rice, pork, chicken, eggs, fish, vegetables) moved over time in Metro Manila markets?
- Do prices at my local market track the DA-monitored markets, or diverge? By how much, and for which commodities?
- How large are seasonal spikes (Holy Week, Christmas, typhoon season)?
- How often do monitored prices exceed the suggested retail price (SRP), when one exists?
- In real (CPI-deflated) terms, which commodities got more expensive fastest?

## 3. Architecture

```
 DA website (PDFs)     Google Sheet (my form)     PSA OpenSTAT API
        │                      │                         │
        ▼                      ▼                         ▼
 ┌──────────────────────────────────────────────────────────────┐
 │  Ingestion (Python, runs in Docker)                          │
 │  download → parse → validate                                 │
 └──────────────────────────────────────────────────────────────┘
        │
        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │  Object storage (data lake)                                  │
 │  landing/  original PDFs, JSON, CSV (immutable)              │
 │  parsed/   Parquet, Hive-partitioned by year=/month=         │
 └──────────────────────────────────────────────────────────────┘
        │
        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │  dbt + DuckDB: staging → intermediate → marts                │
 └──────────────────────────────────────────────────────────────┘
        │                                   │
        ▼                                   ▼
 marts exported as Parquet ──load job──▶ BigQuery (cloud warehouse)
        │
        ▼
 Dashboard (reads DuckDB file; BigQuery used for SQL access/demo)
```

DuckDB is the primary compute engine. BigQuery is a **serving copy** of the marts, so the project demonstrates loading to and querying a cloud warehouse without duplicating transformation logic in two SQL dialects.

## 4. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Use `uv` for dependency management |
| PDF extraction | `pdfplumber` first; fall back to `camelot` if tables need it | Decide after inspecting real PDFs |
| Raw / lake layer | Parquet via `pyarrow`, Hive-partitioned | Stored in object storage |
| Object storage | Google Cloud Storage (default) or Cloudflare R2 | Decide in recon (see §6.2); ask me before creating anything |
| Transformations | dbt Core with `dbt-duckdb` | Reads Parquet from object storage via DuckDB `httpfs` |
| Cloud warehouse | BigQuery (free tier / sandbox) | Marts only, loaded via load jobs |
| Orchestration | GitHub Actions cron (daily) | Runs the pipeline inside the Docker image |
| Containers | Docker; image published to GitHub Container Registry (GHCR) | |
| CI | GitHub Actions on every pull request | Lint, tests, dbt build on fixtures, image build |
| Primary data ingest | Google Sheets API (service account) or published CSV export | Prefer the simplest option that works |
| Dashboard | Streamlit (default) or Evidence | Must be publicly deployable for free |
| Testing | `pytest` for Python, dbt tests for models | |
| Lint / format | `ruff` | |

Do not add infrastructure beyond this list (Airflow, Terraform, Kafka, Spark, paid services) without asking me first.

## 5. Repository layout

```
palengke-price-tracker/
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
├── ingestion/
│   ├── da_prices/
│   │   ├── discover.py           # find new report URLs
│   │   ├── download.py           # fetch PDFs to landing/, skip known hashes
│   │   └── parse.py              # PDF → tidy rows → partitioned Parquet
│   ├── primary/
│   │   └── sheets.py             # my Google Form responses → Parquet
│   ├── psa/
│   │   └── openstat.py           # CPI tables → Parquet
│   └── common/
│       ├── storage.py            # read/write abstraction: local dir or bucket
│       └── manifest.py           # file manifest, hashes, parse status
├── warehouse/
│   └── export_to_bigquery.py     # marts → Parquet → BigQuery load jobs
├── transform/                    # dbt project
│   ├── profiles.yml              # uses env vars, no secrets
│   ├── models/
│   │   ├── sources.yml           # external Parquet sources
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   ├── seeds/
│   │   └── commodity_map.csv     # raw name → canonical commodity
│   └── tests/
├── dashboard/
│   └── app.py
├── tests/
│   ├── fixtures/
│   │   ├── pdfs/                 # small sample PDFs for parser tests
│   │   └── parquet/              # tiny sample lake for CI dbt runs
│   ├── test_parse.py
│   └── test_storage.py
└── docs/
    ├── architecture.png
    └── parsing_notes.md          # format quirks, changes over time
```

## 6. Pipeline stages

### 6.1 Discover and download (DA)
- Scrape the price monitoring page(s) for links to daily report PDFs.
- Write each PDF untouched to `landing/da/YYYY/MM/<original_filename>`, and record its source URL, download timestamp, file hash, and status in a manifest (a Parquet file or small table in the lake).
- Downloads must be idempotent: skip files whose hash is already in the manifest.
- Be polite: set a descriptive User-Agent, sleep between requests, and never run parallel requests against government servers.
- Backfill: support a `--since YYYY-MM-DD` flag to fetch historical reports.

### 6.2 Data lake layout (Parquet)
- Two zones in the bucket:
  - `landing/`: original source files, never modified or deleted by the pipeline.
  - `parsed/`: cleaned, typed rows as Parquet.
- Partition `parsed/` Hive-style so DuckDB and BigQuery can prune partitions:
  ```
  parsed/da_prices/year=2026/month=10/part-<report_date>.parquet
  parsed/primary_prices/year=2026/month=10/part-<run_id>.parquet
  parsed/psa_cpi/year=2026/month=10/part-<run_id>.parquet
  ```
- Writes must be idempotent: re-parsing a report overwrites its own file, never appends duplicates.
- Define an explicit `pyarrow` schema per dataset (no schema inference). Use snappy compression.
- `ingestion/common/storage.py` must work against either a local directory or the bucket, switched by env var, so tests and local dev never need cloud credentials.
- **Storage choice (decide in recon, then ask me):** GCS integrates directly with BigQuery load jobs; R2 has no egress fees. Both free tiers require a payment method on file. Before creating a bucket, confirm the current free-tier limits and remind me to set a budget alert.

### 6.3 Parse (DA)
- **Before writing the parser, download 5–10 PDFs spanning different dates (including older years) and inspect them.** Report back on the layout, how it varies, and edge cases before building. Do not assume a layout.
- Output one tidy row per observation: `report_date`, `market` (if given), `commodity_raw`, `specification` (e.g. size or variety), `unit`, `price_low`, `price_high`, `price_prevailing`, `source_file`, `page`, `parser_version`, `ingested_at`.
- Handle missing values (dashes, "n/a", blank cells) explicitly as NULL, never as 0.
- If a PDF can't be parsed, mark it `failed` in the manifest with the reason and continue. Never silently drop a file.
- Record every format change discovered in `docs/parsing_notes.md`.

### 6.4 Primary data (my own collection)
The Google Form fields are:
`timestamp, collection_date, store_name, store_type (palengke | sari-sari | supermarket), barangay, city, commodity, specification, unit, price, notes`.
- Pull all responses on each run and rewrite the dataset (the volume is small), partitioned by `collection_date`.
- Map `commodity` through the same `commodity_map.csv` seed as the DA data so the two sources are comparable.
- No personal data about vendors. Store names only.

### 6.5 PSA OpenSTAT
- Pull the CPI for food (NCR and national) via the OpenSTAT API.
- Inspect the API response structure first and document the table IDs used in the README.
- Attribute PSA as the source in the dashboard and README, as its license requires.

### 6.6 Transform (dbt + DuckDB)
- Declare the Parquet datasets as dbt sources using DuckDB's `read_parquet(..., hive_partitioning = true)` through `dbt-duckdb` external sources.
- **staging:** one model per source with renamed, typed, and lightly cleaned columns. No joins.
- **intermediate:** canonical commodities via the seed, unit normalization (e.g. everything per kg where possible), and deduplication.
- **marts:**
  - `fct_prices`: grain is one row per date × source × location × commodity × specification.
  - `dim_commodity`: canonical name, category (rice, meat, fish, vegetables, etc.), and SRP where applicable.
  - `dim_location`: market or store, city, and source type (DA vs. primary).
  - `dim_date`: calendar with PH holiday flags (Holy Week, Christmas season, etc.).
  - `mart_local_vs_official`: weekly comparison of my prices against DA prices.
  - `mart_real_prices`: CPI-deflated price series.

### 6.7 Load marts to BigQuery
- `warehouse/export_to_bigquery.py`:
  1. Exports each mart from DuckDB to Parquet (`COPY ... TO ... (FORMAT parquet)`).
  2. Uploads to the bucket under `exports/marts/<mart_name>/` (or loads from local file if using R2).
  3. Runs a BigQuery **load job** (free) with `WRITE_TRUNCATE` into dataset `palengke_marts`.
- Partition `fct_prices` in BigQuery by `price_date` (monthly) and cluster by `commodity_id`.
- Use a dedicated service account with only the roles it needs (BigQuery Data Editor and Job User on this project; storage write on this bucket).
- Free-tier awareness: load jobs are free; keep table storage well under the free limit. If using the BigQuery sandbox, check whether tables get a default expiration and handle it (e.g. reload on each run). Verify current limits before building rather than relying on this file.
- After loading, run a row-count check comparing DuckDB marts against BigQuery tables and fail the run on mismatch.
- Add 3–4 example analytical queries in `warehouse/queries/` that run against BigQuery, for the README.

### 6.8 Data quality
Required dbt tests: `not_null` and `unique` on keys, accepted values for categories, and relationships between facts and dimensions. Custom checks:
- Prices fall within plausible bounds per commodity, so the pipeline flags outliers (e.g. ₱5/kg pork) rather than dropping them.
- Every commodity in the raw data maps to a canonical commodity; an unmapped name fails the run and prints the name so I can add it to the seed.
- A freshness check warns if no new DA report has arrived in more than 7 days.
- The DuckDB-vs-BigQuery row-count reconciliation from §6.7.

## 7. Containerization

- One `Dockerfile` for the pipeline (ingestion, dbt, export). The dashboard is deployed separately and does not need to share the image.
- Multi-stage build: install dependencies with `uv` in a builder stage; copy only what's needed into a slim Python runtime stage.
- Run as a non-root user. No secrets baked into the image; everything comes from env vars at runtime.
- Pin the base image to a specific version tag.
- Single entrypoint with subcommands, e.g.:
  ```
  docker run --env-file .env ghcr.io/<me>/palengke-pipeline:latest run-all
  docker run ... ingest-da --since 2025-01-01
  docker run ... transform
  docker run ... export-bq
  ```
- `docker-compose.yml` (optional) mounts a local `./lake` directory so the full pipeline runs offline against local storage.
- `.dockerignore` excludes the lake, DuckDB files, `.env`, caches, and fixtures not needed at runtime.

## 8. CI/CD and orchestration

### 8.1 `ci.yml` (on every pull request)
1. `ruff check` and `ruff format --check`.
2. `pytest` (parser tests run against `tests/fixtures/pdfs/`).
3. `dbt build` against the tiny fixture lake in `tests/fixtures/parquet/` using local storage, with no cloud credentials.
4. `docker build` to confirm the image still builds.

The PR must not be mergeable if any step fails. CI must never touch the real bucket or BigQuery.

### 8.2 `publish_image.yml` (on push to `main`)
Build the image and push to GHCR, tagged with the commit SHA and `latest`.

### 8.3 `daily_pipeline.yml` (scheduled)
- Runs daily at about 10:00 PHT (02:00 UTC), plus manual `workflow_dispatch`.
- Pulls the GHCR image and runs `run-all`: discover → download → parse → primary → PSA (weekly is fine) → `dbt build` → export to BigQuery → reconciliation.
- Persists the DuckDB file between runs (upload to the bucket at the end, download at the start) so the dashboard can read it.
- Secrets (service account JSON, bucket keys) live in GitHub Actions secrets, never in the repo.

## 9. Dashboard

Pages:
1. **Overview:** latest prices for the key commodities and their week-over-week change.
2. **Trends:** pick a commodity to see its price over time with seasonal periods shaded.
3. **My market vs. DA:** the gap over time per commodity.
4. **SRP compliance:** the share of observations above the SRP.
5. **Real prices:** nominal vs. CPI-deflated prices.
6. **About:** sources, method, limitations, and last refresh time.

The dashboard reads the latest DuckDB file (or mart Parquet files) from the bucket. Keep it fast and readable on mobile. Use peso formatting (₱).

## 10. Conventions

- Use type hints on all functions, and give each module a short docstring explaining its purpose.
- Write small, testable functions. Parser logic must have tests against fixture PDFs.
- Use the `logging` module, never bare `print`, in pipeline code.
- All config (URLs, bucket names, dataset names, date ranges) comes from `config/settings.py`, which reads env vars. Every variable is listed in `.env.example`.
- Commit messages should be short and imperative ("Add DA PDF parser for 2023 layout").
- Work on feature branches and merge through pull requests so CI history is visible in the repo.
- Never commit data files (PDFs, Parquet, DuckDB) except the small fixtures.

## 11. Milestones

Work through these in order. At the end of each, stop, summarize what was done, and wait for my review.

1. **Recon:** inspect DA PDFs, the OpenSTAT API, and current GCS/R2 and BigQuery free-tier limits. Write up findings and any changes needed to this plan.
2. **Project skeleton:** repo layout, `uv` setup, config, storage abstraction (local mode only), Dockerfile, and `ci.yml` running on an empty test suite.
3. **DA ingestion:** discover, download, and parse into local partitioned Parquet, with tests. Backfill at least 6 months locally.
4. **dbt models** for the DA data reading the local Parquet lake, with tests passing in CI against fixtures.
5. **Object storage:** switch storage to the bucket (after my approval), migrate the local lake, and confirm dbt reads from it.
6. **Primary data ingestion** from Google Sheets, merged into the models.
7. **PSA enrichment** and real-price marts.
8. **BigQuery export** with partitioning, reconciliation, and example queries.
9. **Automation:** `publish_image.yml` and `daily_pipeline.yml` running end to end in the container.
10. **Dashboard** running locally, then deployed.
11. **Portfolio polish:** README, architecture diagram, and 3–5 written findings.

## 12. README (portfolio-facing) must include

- A one-paragraph summary of the project and why it matters.
- An architecture diagram showing landing → Parquet lake → dbt/DuckDB → BigQuery and dashboard.
- A live dashboard link and a screenshot.
- Data sources with attribution and licenses.
- 3–5 concrete findings, each backed by a chart.
- Engineering challenges solved: PDF format drift, commodity name standardization, unit normalization, idempotent partitioned writes, keeping CI free of cloud credentials.
- Example BigQuery queries and what they show.
- CI and container badges (build status, image).
- Limitations: DA coverage is Metro Manila only, my own sample is small, and some prices are ranges rather than single values.
- How to run it locally, both with `uv` and with Docker.
- A short "design decisions" section explaining why DuckDB does the transformations and BigQuery only serves the marts.

## 13. Things to ask me about rather than assume

- Creating any cloud resource (bucket, BigQuery dataset, service account) or anything that could cost money.
- GCS vs. R2 for object storage.
- Any new dependency beyond the stack above.
- How to treat price ranges (low/high) vs. a single prevailing price in analysis.
- Commodity mappings that are ambiguous (e.g. different rice varieties).
- Whether to drop or keep data from a PDF layout that only partially parses.
