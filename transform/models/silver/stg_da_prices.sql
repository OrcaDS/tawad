-- DA bronze rows, renamed and lightly typed. Price parsing, revision filtering and
-- name mapping come next (milestone 4, steps 2-3).
select
    report_date,
    series,
    layout,
    page_type,
    market_raw,
    category_header_raw,
    commodity_raw,
    specification_raw,
    unit_raw,
    price_low_raw,
    price_high_raw,
    price_prevailing_raw,
    price_average_raw,
    markets_covered,
    source_file,
    page,
    revision_rank,
    extractor_version,
    ingested_at
from {{ source('bronze', 'da_prices') }}
