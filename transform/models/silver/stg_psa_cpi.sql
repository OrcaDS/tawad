-- PSA consumer price index (2018 = 100) by commodity group, monthly, for the Philippines
-- and NCR. PSA's yearly averages ("2018 Ave") are dropped; "." and ".." (no data) -> NULL.
select
    {{ psa_geo('geolocation_raw') }} as geo,
    split_part(item_raw, ' - ', 1) as cpi_group_code,
    substr(item_raw, strpos(item_raw, ' - ') + 3) as cpi_group,
    strptime(period_raw, '%Y %b')::date as month,
    {{ parse_price('value_raw') }} as cpi,
    value_raw,
    source_url,
    pulled_at
from {{ source('bronze', 'psa_cpi') }}
where not period_raw like '% Ave'
