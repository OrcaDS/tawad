-- One row per place a price comes from: each DA market, and DA's NCR-wide figure
-- (is_aggregate). Kurt's own stores join here at milestone 6.
with markets as (
    select distinct market, city from {{ ref('markets') }}
),

seen as (
    select market, min(report_date) as first_date, max(report_date) as last_date
    from {{ ref('stg_da_prices') }}
    where price is not null
    group by all
)

select
    {{ location_id("'DA'", 'm.market') }} as location_id,
    m.market as location_name,
    m.city,
    'DA' as source,
    m.market = 'NCR (all markets)' as is_aggregate,
    s.first_date as first_price_date,
    s.last_date as last_price_date
from markets as m
left join seen as s on s.market = m.market
