{#
  Raw DA price text -> DOUBLE, or NULL when the cell holds no price.

  - Removes spaces the PDF puts inside numbers ("2 7.00", "5 .00"), thousands commas,
    footnote stars ("**35.00", "50.00***") and parentheses ("( 50.00)").
  - Removes one or two letters that bled in from a neighbouring cell when they touch a
    number ("g 60", "kg 60", "E160.00", "145.00N", "90.00g").
  - Every other text (n/a, #N/A, #DIV/0!, -, (-), NONE, NOT AVAILABLE and its typos, n/m,
    garbled overlaps like "0.00n/m0.00") is not plain digits afterwards and becomes NULL.
  - 0 means missing in DA's older layouts and is never a real price, so it is NULL too.
#}
{% macro parse_price(col) -%}
{%- set cleaned -%}
regexp_replace(
    regexp_replace(
        regexp_replace(trim({{ col }}), '^[A-Za-z]{1,2}\s*([0-9])', '\1'),
        '([0-9])[A-Za-z]$', '\1'
    ),
    '[\s,*()]', '', 'g'
)
{%- endset -%}
nullif(
    case when regexp_full_match({{ cleaned }}, '[0-9]+(\.[0-9]+)?') then cast({{ cleaned }} as double) end,
    0
)
{%- endmacro %}
