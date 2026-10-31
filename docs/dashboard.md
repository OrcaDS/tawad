# Building the Looker Studio dashboard

Every page reads one **custom query** data source over the BigQuery dataset `palengke_gold`. The queries are in [`warehouse/dashboard/`](../warehouse/dashboard/). They join the ids in the fact tables to readable names, so no blends or calculated fields are needed. CI runs each one against the gold tables (`tests/test_queries.py`).

To add one: **Add data → BigQuery → Custom query →** pick the project → paste the file's SQL → **Add**. Name the data source after the file. Peso amounts are plain numbers: set their type to *Currency (PHP)* in the data source. Set `*_pct` columns to *Percent*.

Column meanings are in [`data_dictionary.md`](data_dictionary.md).

## Pages

| Page | Data source | Charts |
|---|---|---|
| Overview | `overview_latest.sql` | Table of `commodity_label`, `price`, `price_change_wow_pct` (heatmap or arrows), with a `category` filter control. A scorecard of `price_date` (Max) as "Prices as of". |
| Trends | `ncr_trends.sql` | Time series: dimension `price_date`, breakdown `season`, metric `price` (Average), a drop-down control on `commodity_label`. Each season gets its own colour on the same line, which stands in for shading (Looker Studio can't shade date ranges). Next to it, a bar chart of `price` (Average) by `season`, broken down by `year`. Use `commodity` instead of `commodity_label` for the longest unbroken series. |
| Market vs NCR | `market_vs_ncr.sql` | Bar chart: dimension `location_name`, metric `market_minus_ncr_pct` (Average), sorted descending, with controls on `commodity_label` and `month` (date range). Time series of `market_price` and `ncr_price` by `month` for one market (control on `location_name`, e.g. Bicutan Market). |
| SRP compliance | `srp_compliance.sql` | Scorecard of `above_cap` (Average) = share of prices above the cap. Time series of `above_cap` (Average) by `month_start`. Table by `commodity_label` and `cap_type` with `above_cap` (Average) and `amount_above_cap` (Average). Filter `is_aggregate` = true for the NCR-wide figure only, or leave it off for every market. |
| Real prices | `real_prices.sql` | Time series of `price_nominal` and `price_real_2018` by `month`, with a control on `commodity_label`. For a "fastest risers" table, add a data source from [`warehouse/queries/real_price_change.sql`](../warehouse/queries/real_price_change.sql). `cpi_food` can go on a second axis. |
| About / sources | the table `meta_last_refresh` (add it as a plain BigQuery table, not a custom query) | Table of `table_name`, `loaded_at`. A text box with the source attribution from [`data_dictionary.md`](data_dictionary.md#source-attribution-show-on-the-dashboard), and a link to the open-data release. |

The other example queries in [`warehouse/queries/`](../warehouse/queries/) (Christmas premium, DA vs PSA, cap compliance) also work as custom queries, for single charts.

## Cost

Custom queries run in BigQuery each time a chart refreshes; Looker Studio caches results for 12 hours by default. The biggest one (`ncr_trends.sql`) reads under 100 MB, against the sandbox's free 1 TB of queries a month.
