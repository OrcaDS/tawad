-- SRP compliance page: each priced observation under a government cap. above_cap is 1 or
-- 0, so its average in Looker Studio is the share of prices above the cap.
SELECT
  s.price_date,
  d.month_start,
  l.location_name,
  l.is_aggregate,
  c.commodity_label,
  c.category,
  s.cap_type,
  s.cap_price,
  s.price,
  CASE WHEN s.is_above_cap THEN 1 ELSE 0 END AS above_cap,
  s.amount_above_cap,
  s.pct_above_cap,
  s.legal_basis
FROM palengke_gold.fct_srp_compliance AS s
JOIN palengke_gold.dim_commodity AS c USING (commodity_id)
JOIN palengke_gold.dim_location AS l USING (location_id)
JOIN palengke_gold.dim_date AS d ON d.calendar_date = s.price_date
WHERE NOT s.is_outlier
