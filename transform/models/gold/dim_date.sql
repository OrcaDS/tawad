-- Calendar from DA's first report year to the end of next year, with PH holidays and the
-- seasons the dashboard shades. Holy Week runs Palm Sunday to Easter Sunday, found from
-- Maundy Thursday in the holiday seed. ph_holidays.csv needs a new year added each year.
with days as (
    select unnest(generate_series(
        date '2018-01-01',
        make_date(year(current_date) + 1, 12, 31),
        interval 1 day
    ))::date as calendar_date
),

holy_week as (
    select
        holiday_date - 4 as palm_sunday,
        holiday_date + 3 as easter_sunday
    from {{ ref('ph_holidays') }}
    where holiday_name = 'Maundy Thursday'
)

select
    d.calendar_date,
    year(d.calendar_date) as year,
    month(d.calendar_date) as month,
    strftime(d.calendar_date, '%B') as month_name,
    date_trunc('month', d.calendar_date)::date as month_start,
    date_trunc('week', d.calendar_date)::date as week_start,
    isodow(d.calendar_date) as day_of_week,
    strftime(d.calendar_date, '%A') as day_name,
    isodow(d.calendar_date) >= 6 as is_weekend,
    h.holiday_name,
    h.holiday_name is not null as is_holiday,
    hw.palm_sunday is not null as is_holy_week,
    (month(d.calendar_date) = 12 or (month(d.calendar_date) = 1 and day(d.calendar_date) <= 6))
        as is_christmas_season,
    month(d.calendar_date) between 6 and 11 as is_typhoon_season
from days as d
left join {{ ref('ph_holidays') }} as h on h.holiday_date = d.calendar_date
left join holy_week as hw on d.calendar_date between hw.palm_sunday and hw.easter_sunday
