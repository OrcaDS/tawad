-- One row per month x DA item: DA's NCR-wide monthly average price, in pesos of that month
-- and in 2018 pesos (deflated by PSA's NCR all-items CPI, 2018 = 100). NCR food CPI sits
-- alongside, so an item's price can be compared with food inflation. Outliers and the
-- weekly series (it repeats the daily reports) are left out of the average. CPI lags about
-- a month, so the latest months have no real price yet.
with da_monthly as (
    select
        date_trunc('month', f.price_date)::date as month,
        f.commodity_id,
        avg(f.price) as price_nominal,
        count(distinct f.price_date) as days_priced
    from {{ ref('fct_prices') }} as f
    inner join {{ ref('dim_location') }} as l on l.location_id = f.location_id
    where l.is_aggregate and f.series != 'weekly_avg' and f.price is not null and not f.is_outlier
    group by all
),

cpi as (
    select
        month,
        max(cpi) filter (where cpi_group_code = '0') as cpi_all_items,
        max(cpi) filter (where cpi_group_code = '01.1') as cpi_food
    from {{ ref('stg_psa_cpi') }}
    where geo = 'NCR'
    group by month
)

select
    d.month,
    d.commodity_id,
    round(d.price_nominal, 2) as price_nominal,
    d.days_priced,
    c.cpi_all_items,
    c.cpi_food,
    round(d.price_nominal * 100 / c.cpi_all_items, 2) as price_real_2018
from da_monthly as d
left join cpi as c on c.month = d.month
