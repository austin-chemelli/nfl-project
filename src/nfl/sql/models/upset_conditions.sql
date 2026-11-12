-- upset_conditions: one row per (game, team) for every regular-season game since 2006 with a schedule
-- spread and plays for both teams. ADR 0028, M25.4. It is a game-level fact table of what happened, read
-- by nfl.paths (point in time there: the aggregate and the team rates filter by season and week).
--
-- Teams are the codes plays print (current franchise codes: LA, LAC, LV for every season; the games'
-- historical STL, SD, OAK are mapped, as in team_week). `spread` is from this team's view: > 0 means this
-- team is favored (games.spread_line > 0 means home favored). role: 'dog' (spread < 0), 'fav', 'pick'
-- (spread = 0). size_bucket is of |spread|: 0-2.5, 3-6.5, 7-9.5, 10+. `won` is margin > 0; a tie is not a
-- win (and not a loss either: 'margin' says it).
--
-- The original five conditions, each from this team's view, with the values under them:
--   turnovers:  takeaways - giveaways >= +1 (interceptions + lost fumbles, any play with a posteam)
--   early_down: own offense EPA/play on downs 1-2 (pass or rush, epa not null, win probability 0.2-0.8
--               so garbage time is out, the repo's neutral-script rule) > the opponent's
--   explosives: more plays of pass >= 20 yards or rush >= 10 yards than the opponent (strictly more)
--   sacks:      the opponent was sacked >= 2 more times than this team (sacks taken by each offense)
--   special_teams: own ST EPA - opponent ST EPA >= +3 (EPA on special_teams_play = 1 plays is from the
--                  kicking or returning posteam's view, so each team's sum is over its own posteam plays)
-- Six more (Austin, 2026-11-12), each "this team's offense beat the opponent's" (strictly; a null rate
-- on either side is false):
--   pass_game:   EPA per dropback (pass = 1, so sacks and scrambles count; win probability 0.2-0.8)
--   big_runs:    more rushes of 10+ yards
--   third_down:  higher third-down conversion rate (third_down_converted / (converted + failed))
--   run_game:    higher rush success rate (win probability 0.2-0.8)
--   deep_passes: more completions of 20+ yards (pass = 1 and yards_gained >= 20)
--   red_zone:    higher touchdown rate on drives that reached the opponent's 20
-- Not point in time on its own: the whole game is in the row. A consumer predicting a game must not
-- read that game or later ones (nfl.paths filters on season and week).
with g as (
    select
        game_id, season, week, spread_line, result,
        case home_team when 'OAK' then 'LV' when 'SD' then 'LAC' when 'STL' then 'LA' else home_team end as home,
        case away_team when 'OAK' then 'LV' when 'SD' then 'LAC' when 'STL' then 'LA' else away_team end as away
    from games
    where game_type = 'REG' and season >= 2006 and spread_line is not null and result is not null
),
t as (
    select
        p.game_id, p.posteam as team,
        sum(coalesce(p.interception, 0) + coalesce(p.fumble_lost, 0)) as giveaways,
        avg(case when p.down in (1, 2) and p.epa is not null and (p."pass" = 1 or p.rush = 1)
            and p.wp between 0.2 and 0.8 then p.epa end) as early_down_epa,
        count(case when p.down in (1, 2) and p.epa is not null and (p."pass" = 1 or p.rush = 1)
            and p.wp between 0.2 and 0.8 then 1 end) as early_down_plays,
        count(case when (p."pass" = 1 and p.yards_gained >= 20) or (p.rush = 1 and p.yards_gained >= 10)
            then 1 end) as explosives,
        sum(case when p.sack = 1 then 1 else 0 end) as sacks_taken,
        coalesce(sum(case when p.special_teams_play = 1 then p.epa end), 0) as st_epa,
        avg(case when p."pass" = 1 and p.epa is not null and p.wp between 0.2 and 0.8 then p.epa end)
            as pass_epa,
        count(case when p.rush = 1 and p.yards_gained >= 10 then 1 end) as big_runs,
        count(case when p."pass" = 1 and p.yards_gained >= 20 then 1 end) as deep_passes,
        sum(coalesce(p.third_down_converted, 0))::double
            / nullif(sum(coalesce(p.third_down_converted, 0) + coalesce(p.third_down_failed, 0)), 0)
            as third_down_rate,
        avg(case when p.rush = 1 and p.wp between 0.2 and 0.8 then p.success end) as rush_sr,
        count(distinct case when p.yardline_100 <= 20 and p.touchdown = 1 and p.td_team = p.posteam
            then p.drive end)::double
            / nullif(count(distinct case when p.yardline_100 <= 20 then p.drive end), 0) as rz_td_rate
    from plays p
    where p.season_type = 'REG' and p.posteam is not null
    group by p.game_id, p.posteam
),
sides as (
    select game_id, season, week, home as team, away as opponent, true as is_home,
        spread_line as spread, result as margin from g
    union all
    select game_id, season, week, away, home, false, -spread_line, -result from g
)
select
    s.season, s.week, s.game_id, s.team, s.opponent, s.is_home, s.spread,
    case when s.spread < 0 then 'dog' when s.spread > 0 then 'fav' else 'pick' end as role,
    case when abs(s.spread) < 3 then '0-2.5' when abs(s.spread) < 7 then '3-6.5'
         when abs(s.spread) < 10 then '7-9.5' else '10+' end as size_bucket,
    s.margin,
    s.margin > 0 as won,
    o.giveaways as takeaways, me.giveaways as giveaways,
    o.giveaways - me.giveaways as turnover_margin,
    (o.giveaways - me.giveaways) >= 1 as turnovers,
    me.early_down_epa as early_down_epa, o.early_down_epa as early_down_epa_opp,
    me.early_down_epa > o.early_down_epa as early_down,
    me.explosives as explosives, o.explosives as explosives_opp,
    me.explosives > o.explosives as explosives_more,
    o.sacks_taken as sacks_made, me.sacks_taken as sacks_taken,
    o.sacks_taken - me.sacks_taken as sack_margin,
    (o.sacks_taken - me.sacks_taken) >= 2 as sacks,
    me.st_epa as st_epa, o.st_epa as st_epa_opp, me.st_epa - o.st_epa as st_epa_net,
    (me.st_epa - o.st_epa) >= 3 as special_teams,
    me.pass_epa as pass_epa, o.pass_epa as pass_epa_opp,
    coalesce(me.pass_epa > o.pass_epa, false) as pass_game,
    me.big_runs as big_runs, o.big_runs as big_runs_opp, me.big_runs > o.big_runs as big_runs_more,
    me.deep_passes as deep_passes, o.deep_passes as deep_passes_opp,
    me.deep_passes > o.deep_passes as deep_passes_more,
    me.third_down_rate as third_down_rate, o.third_down_rate as third_down_rate_opp,
    coalesce(me.third_down_rate > o.third_down_rate, false) as third_down,
    me.rush_sr as rush_sr, o.rush_sr as rush_sr_opp, coalesce(me.rush_sr > o.rush_sr, false) as run_game,
    me.rz_td_rate as rz_td_rate, o.rz_td_rate as rz_td_rate_opp,
    coalesce(me.rz_td_rate > o.rz_td_rate, false) as red_zone
from sides s
join t me on me.game_id = s.game_id and me.team = s.team
join t o on o.game_id = s.game_id and o.team = s.opponent
order by s.season, s.week, s.game_id, s.team
