-- Raw price text that contains a non-zero digit but did not parse to a number: a new
-- shape here may mean parse_price needs a rule. Cells that also say "not available" are
-- left out (DA printed both on top of each other, e.g. "NOT AVAILA4B00LE.00"; NULL is
-- right). Warns, never fails: such cells stay NULL.
{{ config(severity='warn') }}

with cells as (
    select price_low_raw as raw, price_low as parsed from {{ ref('stg_da_prices') }}
    union all
    select price_high_raw, price_high from {{ ref('stg_da_prices') }}
    union all
    select price_prevailing_raw, price_prevailing from {{ ref('stg_da_prices') }}
    union all
    select price_average_raw, price_average from {{ ref('stg_da_prices') }}
)

select raw, count(*) as cells
from cells
where parsed is null and regexp_matches(raw, '[1-9]') and not regexp_matches(raw, '(?i)avail')
group by raw
