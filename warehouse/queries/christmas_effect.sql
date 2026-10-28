-- Do palengke prices rise in the Christmas season? Average price in the season vs the rest
-- of the same year, per commodity (NCR aggregate rows and market rows alike).
WITH by_season AS (
  SELECT
    p.commodity_id,
    d.year,
    AVG(CASE WHEN d.is_christmas_season THEN p.price END) AS christmas,
    AVG(CASE WHEN NOT d.is_christmas_season THEN p.price END) AS rest_of_year
  FROM palengke_gold.fct_prices AS p
  JOIN palengke_gold.dim_date AS d ON d.calendar_date = p.price_date
  WHERE p.price IS NOT NULL AND NOT p.is_outlier
  GROUP BY p.commodity_id, d.year
)
SELECT
  c.commodity_label,
  c.category,
  COUNT(*) AS years,
  ROUND(AVG(100 * (s.christmas / s.rest_of_year - 1)), 1) AS avg_christmas_premium_pct
FROM by_season AS s
JOIN palengke_gold.dim_commodity AS c USING (commodity_id)
WHERE s.christmas IS NOT NULL AND s.rest_of_year IS NOT NULL
GROUP BY c.commodity_label, c.category
HAVING COUNT(*) >= 5
ORDER BY avg_christmas_premium_pct DESC
LIMIT 15;
