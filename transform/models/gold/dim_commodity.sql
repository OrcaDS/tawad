-- One row per item DA prices: canonical commodity, plus DA's sub-item (variant) and origin
-- when it gives them. Built from the seed, so an item appears even before its first price.
with items as (
    select distinct commodity, variant, origin, category, unit
    from {{ ref('commodity_map') }}
    where exclude_reason is null
),

seen as (
    select commodity, variant, origin, min(report_date) as first_date, max(report_date) as last_date
    from {{ ref('stg_da_prices') }}
    where price is not null
    group by all
)

select
    {{ commodity_id('i.commodity', 'i.variant', 'i.origin') }} as commodity_id,
    i.commodity,
    i.variant,
    i.origin,
    concat_ws(', ', i.commodity, i.variant, i.origin) as commodity_label,
    i.category,
    i.unit,
    i.unit = 'kg' as is_per_kg,
    s.first_date as first_price_date,
    s.last_date as last_price_date
from items as i
left join seen as s
    on s.commodity = i.commodity
    and s.variant is not distinct from i.variant
    and s.origin is not distinct from i.origin
