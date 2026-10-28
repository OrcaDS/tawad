-- Do the two government sources agree? Monthly DA average vs PSA retail price (NCR).
SELECT
  commodity,
  origin,
  COUNT(*) AS months,
  ROUND(AVG(da_price), 2) AS avg_da_price,
  ROUND(AVG(psa_price), 2) AS avg_psa_price,
  ROUND(100 * AVG(da_minus_psa_pct), 1) AS avg_gap_pct
FROM palengke_gold.mart_da_vs_psa
WHERE da_price IS NOT NULL AND psa_price IS NOT NULL
GROUP BY commodity, origin
ORDER BY ABS(AVG(da_minus_psa_pct)) DESC;
