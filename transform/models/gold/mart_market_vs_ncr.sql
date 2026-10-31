-- One row per month x DA market x item: the market's average price next to DA's NCR-wide
-- price over the same days. Only days where both are priced (same report series, no
-- outliers) count, so a gap is never a mix of different days or report formats.
with daily as (
    select
        f.price_date,
        f.location_id,
        f.commodity_id,
        f.price as market_price,
        n.price as ncr_price
    from {{ ref('fct_prices') }} as f
    inner join {{ ref('dim_location') }} as l on l.location_id = f.location_id
    inner join {{ ref('fct_prices') }} as n
        on n.price_date = f.price_date
        and n.series = f.series
        and n.commodity_id = f.commodity_id
    inner join {{ ref('dim_location') }} as nl on nl.location_id = n.location_id
    where not l.is_aggregate and nl.is_aggregate
        and f.price is not null and not f.is_outlier
        and n.price is not null and not n.is_outlier
)

select
    date_trunc('month', price_date)::date as month,
    location_id,
    commodity_id,
    round(avg(market_price), 2) as market_price,
    round(avg(ncr_price), 2) as ncr_price,
    count(distinct price_date) as days_compared,
    round(avg(market_price) - avg(ncr_price), 2) as market_minus_ncr,
    round((avg(market_price) - avg(ncr_price)) / avg(ncr_price), 4) as market_minus_ncr_pct
from daily
group by all
