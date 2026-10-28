-- Which foods got more expensive than inflation since 2019?
-- Yearly average price, nominal and in 2018 pesos (deflated by the NCR all-items CPI).
WITH yearly AS (
  SELECT
    commodity_id,
    EXTRACT(YEAR FROM month) AS year,
    AVG(price_nominal) AS nominal,
    AVG(price_real_2018) AS real_2018
  FROM palengke_gold.mart_real_prices
  WHERE EXTRACT(YEAR FROM month) IN (2019, 2025)
  GROUP BY commodity_id, year
)
SELECT
  c.commodity_label,
  c.category,
  ROUND(MAX(CASE WHEN y.year = 2019 THEN y.nominal END), 2) AS avg_price_2019,
  ROUND(MAX(CASE WHEN y.year = 2025 THEN y.nominal END), 2) AS avg_price_2025,
  ROUND(100 * (MAX(CASE WHEN y.year = 2025 THEN y.real_2018 END)
             / MAX(CASE WHEN y.year = 2019 THEN y.real_2018 END) - 1), 1) AS real_change_pct
FROM yearly AS y
JOIN palengke_gold.dim_commodity AS c USING (commodity_id)
GROUP BY c.commodity_label, c.category
HAVING COUNT(DISTINCT y.year) = 2
ORDER BY real_change_pct DESC
LIMIT 15;
