-- Overview page: DA's NCR-wide prices on the latest report day, with the week-on-week change.
SELECT
  f.price_date,
  c.commodity_label,
  c.category,
  c.unit,
  f.price,
  f.price_week_ago,
  f.price_change_wow_pct
FROM palengke_gold.fct_prices AS f
JOIN palengke_gold.dim_commodity AS c USING (commodity_id)
JOIN palengke_gold.dim_location AS l USING (location_id)
WHERE l.is_aggregate
  AND f.series = 'price_monitoring'
  AND f.price IS NOT NULL
  AND f.price_date = (
    SELECT MAX(price_date) FROM palengke_gold.fct_prices WHERE series = 'price_monitoring'
  )
