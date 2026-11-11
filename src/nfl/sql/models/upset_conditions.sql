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
-- The five conditions, each from this team's view, with the values under them:
--   turnovers:  takeaways - giveaways >= +1 (interceptions + lost fumbles, any play with a posteam)
--   early_down: own offense EPA/play on downs 1-2 (pass or rush, epa not null, win probability 0.2-0.8
--               so garbage time is out, the repo's neutral-script rule) > the opponent's
--   explosives: more plays of pass >= 20 yards or rush >= 10 yards than the opponent (strictly more)
--   sacks:      the opponent was sacked >= 2 more times than this team (sacks taken by each offense)
--   special_teams: own ST EPA - opponent ST EPA >= +3 (EPA on special_teams_play = 1 plays is from the
--                  kicking or returning posteam's view, so each team's sum is over its own posteam plays)
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
        coalesce(sum(case when p.special_teams_play = 1 then p.epa end), 0) as st_epa
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
    (me.st_epa - o.st_epa) >= 3 as special_teams
from sides s
join t me on me.game_id = s.game_id and me.team = s.team
join t o on o.game_id = s.game_id and o.team = s.opponent
order by s.season, s.week, s.game_id, s.team
