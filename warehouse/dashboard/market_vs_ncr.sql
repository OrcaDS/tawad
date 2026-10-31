-- Market vs NCR page: each DA market's monthly price next to DA's NCR-wide price.
SELECT
  m.month,
  l.location_name,
  l.city,
  c.commodity_label,
  c.category,
  c.unit,
  m.market_price,
  m.ncr_price,
  m.market_minus_ncr,
  m.market_minus_ncr_pct,
  m.days_compared
FROM palengke_gold.mart_market_vs_ncr AS m
JOIN palengke_gold.dim_location AS l USING (location_id)
JOIN palengke_gold.dim_commodity AS c USING (commodity_id)
