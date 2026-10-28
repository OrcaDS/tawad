-- DA price rows from bronze: prices parsed to numbers (missing -> NULL, never 0), one
-- headline price per row, and only the latest revision of each report. Commodity and
-- market names map to canonical ones through the seeds; rows the commodity seed marks
-- with an exclude_reason (e.g. a category header read as a name) are left out.
with parsed as (
    select
        *,
        {{ parse_price('price_low_raw') }} as price_low,
        {{ parse_price('price_high_raw') }} as price_high,
        {{ parse_price('price_prevailing_raw') }} as price_prevailing,
        {{ parse_price('price_average_raw') }} as price_average
    from {{ source('bronze', 'da_prices') }}
    -- A revised report replaces the original; if the revision could not be read, the
    -- latest version that did reach bronze stays.
    qualify revision_rank = max(revision_rank) over (partition by series, report_date)
)

select
    report_date,
    series,
    layout,
    page_type,
    mk.market,
    mk.city,
    cm.commodity,
    cm.variant,
    cm.origin,
    cm.category,
    cm.unit as unit_normalized,
    cm.unit = 'kg' as is_per_kg,
    p.market_raw,
    p.category_header_raw,
    p.commodity_raw,
    p.specification_raw,
    unit_raw,
    price_low,
    price_high,
    price_prevailing,
    price_average,
    case
        when price_prevailing is not null then price_prevailing
        when price_low is not null and price_high is not null then (price_low + price_high) / 2
        when price_average is not null then price_average
        else coalesce(price_low, price_high)
    end as price,
    case
        when price_prevailing is not null then 'prevailing'
        when price_low = price_high then 'single'
        when price_low is not null and price_high is not null then 'midpoint'
        when price_average is not null then 'average'
        when coalesce(price_low, price_high) is not null then 'single'
    end as price_basis,
    price_low_raw,
    price_high_raw,
    price_prevailing_raw,
    price_average_raw,
    markets_covered,
    source_file,
    page,
    file_row_number,
    revision_rank,
    extractor_version,
    ingested_at
from parsed as p
left join {{ ref('commodity_map') }} as cm
    on cm.category_header_raw is not distinct from {{ normalize_name('p.category_header_raw') }}
    and cm.commodity_raw is not distinct from {{ normalize_name('p.commodity_raw') }}
    and cm.specification_raw is not distinct from {{ normalize_name('p.specification_raw') }}
left join {{ ref('markets') }} as mk on mk.market_raw is not distinct from p.market_raw
where cm.exclude_reason is null
