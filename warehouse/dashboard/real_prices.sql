-- Real prices page: monthly NCR price per item, in pesos of the day and in 2018 pesos.
SELECT
  r.month,
  c.commodity_label,
  c.category,
  c.unit,
  r.price_nominal,
  r.price_real_2018,
  r.cpi_all_items,
  r.cpi_food
FROM palengke_gold.mart_real_prices AS r
JOIN palengke_gold.dim_commodity AS c USING (commodity_id)
