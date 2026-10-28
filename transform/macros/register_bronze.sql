{#
  Run at the start of every dbt run: expose the bronze Parquet under LAKE_ROOT as views in
  schema `bronze`, so sources are real relations (unit tests need their columns).
  `file_row_number` is the row's position in its Parquet file, i.e. the order the
  extractor wrote the rows in.
#}
{% macro register_bronze() -%}
create schema if not exists bronze;
create or replace view bronze.da_prices as
select * from read_parquet(
    '{{ var("lake_root") }}/bronze/tables/da_prices/**/*.parquet',
    hive_partitioning = true, union_by_name = true, file_row_number = true
);
create or replace view bronze.psa_cpi as
select * from read_parquet('{{ var("lake_root") }}/bronze/tables/psa_cpi/*.parquet');
create or replace view bronze.psa_retail as
select * from read_parquet('{{ var("lake_root") }}/bronze/tables/psa_retail/*.parquet');
{%- endmacro %}
