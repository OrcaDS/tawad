-- One row per month x PSA item mapped to a DA commodity (psa_commodity_map): PSA's NCR
-- retail price next to DA's NCR-wide monthly price for the same commodity. DA's variants
-- (sizes, brands, colours) are averaged with equal weight, narrowed to one origin only where
-- PSA names it; frozen items are left out because PSA prices fresh meat and fish. Months
-- only one source covers are kept, with the other side NULL.
with psa as (
    select p.month, p.psa_commodity, p.price as psa_price
    from {{ ref('stg_psa_retail') }} as p
    where p.geo = 'NCR' and p.price is not null
),

da as (
    select
        r.month,
        m.psa_commodity,
        avg(r.price_nominal) as da_price,
        max(r.days_priced) as da_days_priced
    from {{ ref('mart_real_prices') }} as r
    inner join {{ ref('dim_commodity') }} as c on c.commodity_id = r.commodity_id
    inner join {{ ref('psa_commodity_map') }} as m
        on m.commodity = c.commodity
        and (m.origin is null or m.origin = c.origin)
    where c.variant is distinct from 'frozen'
    group by all
)

select
    coalesce(p.month, d.month) as month,
    m.psa_commodity,
    m.commodity,
    m.origin,
    round(d.da_price, 2) as da_price,
    d.da_days_priced,
    p.psa_price,
    round(d.da_price - p.psa_price, 2) as da_minus_psa,
    round((d.da_price - p.psa_price) / p.psa_price, 4) as da_minus_psa_pct
from psa as p
full join da as d on d.month = p.month and d.psa_commodity = p.psa_commodity
inner join {{ ref('psa_commodity_map') }} as m
    on m.psa_commodity = coalesce(p.psa_commodity, d.psa_commodity)
