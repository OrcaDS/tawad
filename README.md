# Palengke Price Tracker (tawad)

A medallion-architecture data pipeline (bronze → silver → gold) tracking Metro Manila retail food prices from DA Bantay Presyo reports and PSA OpenSTAT. Gold tables are served from BigQuery to a Looker Studio dashboard.

> Work in progress. The full portfolio write-up arrives in milestone 11. See `project.md` for the brief and `docs/recon.md` for source research.

## Run locally

```sh
uv sync
uv run pytest
uv run tawad show-config
```

With Docker:

```sh
docker build -t tawad-pipeline .
docker run --rm --env-file .env tawad-pipeline show-config
```

## Load gold to BigQuery

`tawad export-bq` exports each gold table to Parquet and loads it into the BigQuery sandbox dataset `palengke_gold` (set `GCP_PROJECT_ID`, and point `GOOGLE_APPLICATION_CREDENTIALS` at a service account key; the account needs BigQuery Job User on the project and BigQuery Data Owner on the dataset, since it keeps a running byte total in a dataset label). The sandbox's 10 GiB storage is a lifetime quota, so a table is reloaded only when its data changed and its last load is at least four weeks old, or when it is about to hit the sandbox's 60-day expiry. `--force` reloads everything. Each load is checked against DuckDB's row count.

Example queries are in [`warehouse/queries/`](warehouse/queries/): foods that outpaced inflation, how often prices break the government cap, the Christmas-season premium, and how DA and PSA prices compare.

## Data sources

- Department of Agriculture, Agribusiness and Marketing Assistance Service (DA-AMAS), Bantay Presyo price monitoring.
- Philippine Statistics Authority (PSA), OpenSTAT.
