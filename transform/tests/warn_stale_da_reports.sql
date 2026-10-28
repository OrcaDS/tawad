-- Warns when the newest DA report in silver is more than 7 days old: the downloader may
-- have stopped, or DA stopped publishing. Always warns on the CI sample, whose rows are old.
{{ config(severity='warn') }}

select max(report_date) as latest_report, current_date - max(report_date) as days_old
from {{ ref('stg_da_prices') }}
having current_date - max(report_date) > 7
