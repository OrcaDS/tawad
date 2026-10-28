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

## Data sources

- Department of Agriculture, Agribusiness and Marketing Assistance Service (DA-AMAS), Bantay Presyo price monitoring.
- Philippine Statistics Authority (PSA), OpenSTAT.
