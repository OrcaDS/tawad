{#
  Surrogate keys for gold: a short md5 of the natural key, so facts and dimensions build
  the same id without a join, and fct_prices stores 16 characters instead of the names
  (BigQuery sandbox storage is limited).
#}
{% macro commodity_id(commodity, variant, origin) -%}
left(md5(concat_ws('|', {{ commodity }}, coalesce({{ variant }}, ''), coalesce({{ origin }}, ''))), 16)
{%- endmacro %}

{% macro location_id(source, location) -%}
left(md5(concat_ws('|', {{ source }}, {{ location }})), 16)
{%- endmacro %}
