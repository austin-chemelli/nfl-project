-- team_week: one row per (season, week, game_id, team, side). ADR 0026, M23.3.
--
-- side 'off' groups a team's own plays (posteam); side 'def' groups the plays it defended (defteam), so
-- every value on a 'def' row is what that defense allowed (takeaways, pressures: what it forced).
-- Plays: regular season and postseason, epa not null, pass or rush. Teams are the codes plays print
-- (current franchise codes: LA, LAC, LV for every season), so a consumer joining to games maps the
-- games' historical codes (STL, SD, OAK) through TEAM_ALIASES first.
--
-- Point in time: this table is per week and reads only that week's plays. A consumer building a
-- feature for a game in week w must sum rows with week < w (candidate_screen.asof_frame does).
--
-- Pressure and time to throw come from participation (2016 onward) and are null before it.
-- epa_noto_sum sums only plays with no interception and no lost fumble; its rate is over all plays.
with base as (
    select
        p.season, p.week, p.season_type, p.game_id, p.posteam, p.defteam,
        p.epa, p.wp, p.success, p.down, p.qtr, p.pass_oe,
        coalesce(p.interception, 0) as interception,
        coalesce(p.fumble, 0) as fumble,
        coalesce(p.fumble_lost, 0) as fumble_lost,
        coalesce(p.sack, 0) as sack,
        coalesce(p.qb_dropback, 0) as qb_dropback,
        pt.was_pressure, pt.time_to_throw
    from plays p
    left join participation pt on pt.game_id = p.game_id and pt.play_id = p.play_id
    where p.season_type in ('REG', 'POST')
        and p.epa is not null
        and (p.pass = 1 or p.rush = 1)
        and p.posteam is not null and p.defteam is not null
),
sides as (
    select *, posteam as team, 'off' as side from base
    union all
    select *, defteam as team, 'def' as side from base
)
select
    season, week, game_id, team, side, season_type,
    count(*) as plays,
    sum(epa) as epa_sum,
    sum(case when interception = 0 and fumble_lost = 0 then epa end) as epa_noto_sum,
    sum(coalesce(success, 0)) as success_sum,
    sum(qb_dropback) as dropbacks,
    sum(sack) as sacks,
    sum(interception) as interceptions,
    sum(fumble) as fumbles,
    sum(fumble_lost) as fumbles_lost,
    sum(interception + fumble_lost) as takeaways,
    sum(case when down in (1, 2) and wp between 0.2 and 0.8 and qtr <= 3 then pass_oe end) as proe_sum,
    count(case when down in (1, 2) and wp between 0.2 and 0.8 and qtr <= 3 and pass_oe is not null
        then 1 end) as proe_n,
    count(case when wp between 0.2 and 0.8 then 1 end) as neutral_plays,
    sum(epa * 4 * wp * (1 - wp)) as wepa_sum,
    sum(4 * wp * (1 - wp)) as wepa_w,
    sum(case when was_pressure then 1 else 0 end) filter (where was_pressure is not null) as pressures,
    sum(time_to_throw) as ttt_sum,
    count(time_to_throw) as ttt_n
from sides
group by season, week, game_id, team, side, season_type
order by season, week, game_id, team, side
