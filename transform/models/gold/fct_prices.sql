-- One row per date x source x series x location x item (commodity, variant, origin).
-- A NULL price means DA listed the item but had no price that day ("not available").
--
-- About 0.7% of silver rows repeat the grain. Which one is kept, in order:
--   1. a row with a price over one without;
--   2. the report's main table over its detail pages (market_range over the 2021-24 pork
--      and chicken by-market pages; ncr_summary over the matrix's NCR columns, which
--      carry the same prices);
--   3. the row DA printed first (DA sometimes lists an item twice on one page).
--
-- is_outlier flags, never drops: a price under half or over double the median for that
-- item in that month (all locations), or a range with low > high. Mostly DA's own typos
-- or columns DA shifted (e.g. 2025-11-04 lists eggs at 180 per piece).
with deduped as (
    select
        report_date as price_date,
        'DA' as source,
        series,
        {{ location_id("'DA'", 'market') }} as location_id,
        {{ commodity_id('commodity', 'variant', 'origin') }} as commodity_id,
        price,
        price_basis,
        price_low,
        price_high
    from {{ ref('stg_da_prices') }}
    qualify row_number() over (
        partition by report_date, series, market, commodity, variant, origin
        order by
            price is null,
            page_type in ('pork_by_market', 'chicken_by_market', 'market_matrix'),
            page,
            file_row_number
    ) = 1
),

priced as (
    select * from deduped where price is not null
),

with_week_ago as (
    -- Latest price from 7 to 13 days earlier: the same weekday last week, or the closest
    -- report before it when DA skipped that day.
    select
        d.*,
        case when w.price_date > d.price_date - 14 then w.price end as price_week_ago
    from deduped as d
    asof left join priced as w
        on d.series = w.series
        and d.location_id = w.location_id
        and d.commodity_id = w.commodity_id
        and d.price_date - 7 >= w.price_date
)

select
    price_date,
    source,
    series,
    location_id,
    commodity_id,
    price,
    price_basis,
    price_low,
    price_high,
    price_week_ago,
    round(price - price_week_ago, 2) as price_change_wow,
    round((price - price_week_ago) / price_week_ago, 4) as price_change_wow_pct,
    coalesce(
        price_low > price_high
        or price < monthly_median / 2
        or price > monthly_median * 2,
        false
    ) as is_outlier
from (
    select
        *,
        median(price) over (partition by commodity_id, date_trunc('month', price_date)) as monthly_median
    from with_week_ago
)
