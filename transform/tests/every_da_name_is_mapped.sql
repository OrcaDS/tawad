-- Every commodity and market name in bronze must have a row in its seed. Fails the run
-- and logs each missing name, so it can be added to transform/seeds/.
{% set unmapped %}
select distinct
    'commodity_map' as seed,
    {{ normalize_name('category_header_raw') }} as category_header_raw,
    {{ normalize_name('commodity_raw') }} as commodity_raw,
    {{ normalize_name('specification_raw') }} as specification_raw
from {{ source('bronze', 'da_prices') }} as b
where not exists (
    select 1 from {{ ref('commodity_map') }} as m
    where m.category_header_raw is not distinct from {{ normalize_name('b.category_header_raw') }}
        and m.commodity_raw is not distinct from {{ normalize_name('b.commodity_raw') }}
        and m.specification_raw is not distinct from {{ normalize_name('b.specification_raw') }}
)
union all
select distinct 'markets', null, market_raw, null
from {{ source('bronze', 'da_prices') }} as b
where not exists (
    select 1 from {{ ref('markets') }} as m where m.market_raw is not distinct from b.market_raw
)
{% endset %}

{{ log_rows(unmapped, 'Unmapped DA name (seed | header | name | spec)') }}
{{ unmapped }}
