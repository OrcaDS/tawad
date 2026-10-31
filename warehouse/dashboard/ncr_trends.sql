-- Trends page: DA's NCR-wide daily price per item since 2018, tagged with the season of
-- its date. price_watch ends 2019-10-09 and price_monitoring starts 2019-10-10, so together
-- they are one unbroken series. The seasons never overlap, so one column holds them all.
SELECT
  f.price_date,
  d.month_start,
  d.year,
  c.commodity,
  c.commodity_label,
  c.category,
  c.unit,
  f.price,
  f.price_low,
  f.price_high,
  CASE
    WHEN d.is_christmas_season THEN 'Christmas season'
    WHEN d.is_holy_week THEN 'Holy Week'
    WHEN d.is_typhoon_season THEN 'Typhoon season'
    ELSE 'Rest of year'
  END AS season,
  d.holiday_name
FROM palengke_gold.fct_prices AS f
JOIN palengke_gold.dim_commodity AS c USING (commodity_id)
JOIN palengke_gold.dim_location AS l USING (location_id)
JOIN palengke_gold.dim_date AS d ON d.calendar_date = f.price_date
WHERE l.is_aggregate
  AND f.series IN ('price_watch', 'price_monitoring')
  AND f.price IS NOT NULL
  AND NOT f.is_outlier
