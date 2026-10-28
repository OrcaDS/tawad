-- How often are prices above the government cap (SRP / MSRP / price ceiling) in force that day?
SELECT
  c.commodity_label,
  s.cap_type,
  COUNT(*) AS observations,
  ROUND(100 * AVG(CASE WHEN s.is_above_cap THEN 1 ELSE 0 END), 1) AS pct_above_cap,
  ROUND(AVG(CASE WHEN s.is_above_cap THEN s.amount_above_cap END), 2) AS avg_pesos_over_cap
FROM palengke_gold.fct_srp_compliance AS s
JOIN palengke_gold.dim_commodity AS c USING (commodity_id)
WHERE NOT s.is_outlier
GROUP BY c.commodity_label, s.cap_type
HAVING COUNT(*) >= 100
ORDER BY pct_above_cap DESC;
