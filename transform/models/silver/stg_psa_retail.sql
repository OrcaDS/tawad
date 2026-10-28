-- PSA monthly retail prices for the Philippines and NCR. PSA's yearly figures ("2018
-- Annual") are dropped; "." and ".." (no data) -> NULL. psa_commodity is PSA's own name
-- (e.g. "FRESH PORK, KASIM, 1 KG"); psa_commodity_map links some of them to DA's.
select
    {{ psa_geo('geolocation_raw') }} as geo,
    item_raw as psa_commodity,
    strptime(period_raw, '%Y %B')::date as month,
    {{ parse_price('value_raw') }} as price,
    table_id,
    value_raw,
    source_url,
    pulled_at
from {{ source('bronze', 'psa_retail') }}
where not period_raw like '% Annual'
