-- One row per fct_prices price that had a government cap in force on its date (from
-- srp_history.csv). A cap with a blank variant or origin covers all of them.
-- is_above_cap compares the headline price; is_high_above_cap the top of DA's range,
-- i.e. at least some stalls charged more than the cap.
select
    f.price_date,
    f.source,
    f.series,
    f.location_id,
    f.commodity_id,
    f.price,
    f.price_low,
    f.price_high,
    s.cap_type,
    s.cap_price,
    s.legal_basis,
    f.price > s.cap_price as is_above_cap,
    coalesce(f.price_high, f.price) > s.cap_price as is_high_above_cap,
    round(f.price - s.cap_price, 2) as amount_above_cap,
    round((f.price - s.cap_price) / s.cap_price, 4) as pct_above_cap,
    f.is_outlier
from {{ ref('fct_prices') }} as f
join {{ ref('dim_commodity') }} as c on c.commodity_id = f.commodity_id
join {{ ref('srp_history') }} as s
    on s.commodity = c.commodity
    and (s.variant is null or s.variant = c.variant)
    and (s.origin is null or s.origin = c.origin)
    and f.price_date between s.effective_from and coalesce(s.effective_to, date '9999-12-31')
where f.price is not null
