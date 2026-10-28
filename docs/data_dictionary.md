# Data dictionary: gold tables

The gold tables are what the dashboard reads (BigQuery dataset `palengke_gold` from milestone 8). Each table has one grain, stated below. Amounts are Philippine pesos stored as plain numbers; dates are `DATE`.

Join facts to dimensions on the `_id` columns and on `price_date = calendar_date`. Ids are short hashes of the natural key: they stay the same across rebuilds as long as the names in the seeds don't change.

## Source attribution (show on the dashboard)

> Prices: Department of Agriculture (DA), Bantay Presyo price monitoring reports for Metro Manila markets, https://www.da.gov.ph/price-monitoring/. Compiled and processed by this project; DA is not responsible for the processing.
>
> Price caps: executive orders and DA announcements, as linked in `srp_history.csv`.
>
> Holidays: Philippine proclamations, via the `holidays` Python library.

PSA attribution is added with the PSA tables (milestone 7).

## fct_prices

**Grain:** one row per date × source × series × location × item. About 880,000 rows from 2018-02.

| Column | Type | Meaning |
|---|---|---|
| price_date | date | Date of the DA report (from its title, not its upload folder). |
| source | text | `DA` (Kurt's own prices are added at milestone 6). |
| series | text | DA report series: `price_watch` (2018–19), `retail_monitoring` (2019–20), `price_monitoring` (2019→), `daily_index` (2025→, DA's daily price index, NCR-wide), `weekly_avg` (2023→, weekly average). Series overlap for the NCR-wide figure, so filter on one series per chart. |
| location_id | text | → `dim_location`. |
| commodity_id | text | → `dim_commodity`. |
| price | number | Headline price per `dim_commodity.unit`: DA's prevailing price, else the midpoint of its low–high range, else the weekly average. NULL = DA listed the item but it was not available that day. Never 0. |
| price_basis | text | Where `price` came from: `prevailing`, `midpoint`, `single` (DA gave one number), `average`. |
| price_low, price_high | number | DA's price range, when it gives one. Use for range bands. |
| price_week_ago | number | Price for the same series, location and item 7–13 days earlier (latest one in that window). NULL if none. |
| price_change_wow | number | `price − price_week_ago`. |
| price_change_wow_pct | number | Same as a fraction (0.05 = +5%). |
| is_outlier | boolean | Price under half or over double the median for the item that month (all locations), or a range with low > high. Mostly DA typos or shifted columns in DA's own PDF. Kept, so filter them out in charts. |

When DA prints the same item twice for one market and day (about 0.7% of rows), one row is kept: a priced row over an unpriced one, the report's main table over its pork/chicken detail pages, then the row printed first.

## fct_srp_compliance

**Grain:** same as `fct_prices`, but only rows with a price and a government cap in force on that date (about 41,000 rows).

| Column | Type | Meaning |
|---|---|---|
| price_date, source, series, location_id, commodity_id | | As in `fct_prices`. |
| price, price_low, price_high | number | As in `fct_prices`. |
| cap_type | text | `price_ceiling` (mandatory, by executive order), `srp` or `msrp` (DA's suggested / maximum suggested retail price). |
| cap_price | number | Cap in force on `price_date`, pesos per kg. |
| legal_basis | text | The order or announcement that set it. |
| is_above_cap | boolean | Headline price above the cap. |
| is_high_above_cap | boolean | Top of DA's range above the cap: at least some stalls charged more. |
| amount_above_cap | number | `price − cap_price` (negative = under the cap). |
| pct_above_cap | number | Same as a fraction of the cap. |
| is_outlier | boolean | As in `fct_prices`. |

Caps covered (see `transform/seeds/srp_history.csv` for dates and source links): EO 124 pork and chicken ceilings (Feb–Apr 2021), red onion SRP (Dec 2022–Jan 2023), EO 39 rice ceilings (Sep–Oct 2023), imported rice MSRP (Jan 2025–May 2026), EO 118 imported rice ceiling (May–Jun 2026), pork MSRP (Mar–May 2025, and from Dec 2025), onion MSRP (from Dec 2025). Not covered yet: DA's April 2021 SRP on imported pork (end date unknown) and caps before 2021. A cap with a blank variant or origin applies to all of them (e.g. the pork MSRP is applied to frozen pork too).

## dim_commodity

**Grain:** one row per item: commodity × variant × origin (315 rows).

| Column | Type | Meaning |
|---|---|---|
| commodity_id | text | Key. |
| commodity | text | Canonical name, the same across DA's eras (e.g. `Pork kasim (shoulder)`). Chart a long-run trend on this. |
| variant | text | DA's sub-item when it splits one: fresh/frozen, brand, egg colour, variety, size. NULL when DA doesn't split. |
| origin | text | `local` or `imported` when DA says so, else NULL. |
| commodity_label | text | Commodity, variant and origin in one label. |
| category | text | Rice, Corn, Fish, Pork, Beef, Other meat, Poultry, Eggs, Lowland vegetables, Highland vegetables, Spices, Fruits, Legumes, Other basic commodities. |
| unit | text | What one price buys: `kg`, `piece` (eggs) or `bottle` (cooking oil; size is in the name). |
| is_per_kg | boolean | `unit = 'kg'`. |
| first_price_date, last_price_date | date | First and last date with a price. NULL if never priced. |

## dim_location

**Grain:** one row per place a price comes from (56 rows: 55 DA markets and the NCR-wide figure).

| Column | Type | Meaning |
|---|---|---|
| location_id | text | Key. |
| location_name | text | Market name, e.g. `Bicutan Market`. `NCR (all markets)` is DA's Metro Manila-wide figure. |
| city | text | City, when known (blank for 8 markets). |
| source | text | `DA`. |
| is_aggregate | boolean | True for the NCR-wide figure. |
| first_price_date, last_price_date | date | First and last date with a price. |

## dim_date

**Grain:** one row per day, 2018-01-01 to the end of next year.

| Column | Type | Meaning |
|---|---|---|
| calendar_date | date | Key. |
| year, month, month_name, day_of_week (1 = Monday), day_name | | Calendar parts. |
| month_start, week_start | date | First day of the month / of the ISO week (Monday). |
| is_weekend | boolean | Saturday or Sunday. |
| holiday_name, is_holiday | text, boolean | National holiday or special non-working day (2018–2026; add each new year to `ph_holidays.csv`). |
| is_holy_week | boolean | Palm Sunday to Easter Sunday. |
| is_christmas_season | boolean | 1 December to 6 January (Three Kings). |
| is_typhoon_season | boolean | June to November. |
