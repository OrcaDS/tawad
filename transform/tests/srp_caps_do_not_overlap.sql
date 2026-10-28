-- Two caps that cover the same item on the same day would give a price two caps in
-- fct_srp_compliance. Fails with the overlapping pairs from srp_history.csv.
with caps as (
    select *, row_number() over (order by effective_from, commodity, cap_price) as cap_no
    from {{ ref('srp_history') }}
)

select a.commodity, a.variant, a.origin, a.effective_from, b.effective_from as other_from
from caps as a
join caps as b
    on a.cap_no < b.cap_no
    and a.commodity = b.commodity
    and (a.variant is null or b.variant is null or a.variant = b.variant)
    and (a.origin is null or b.origin is null or a.origin = b.origin)
    and a.effective_from <= coalesce(b.effective_to, date '9999-12-31')
    and b.effective_from <= coalesce(a.effective_to, date '9999-12-31')
