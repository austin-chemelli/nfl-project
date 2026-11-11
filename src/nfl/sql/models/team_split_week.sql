-- team_split_week: one row per (season, week, game_id, team, side, split, flag). ADR 0028, M25.0.
--
-- Same universe and sides as team_week: regular season and postseason plays with epa not null, pass or
-- rush, posteam and defteam not null; side 'off' groups a team's own plays (posteam), 'def' the plays it
-- defended (defteam), so a 'def' row is what that defense allowed. Team codes are the plays' (current
-- franchise codes). Each split in src/nfl/splits.py has one block below; ids here and there must agree
-- (tests/test_team_split_week.py).
--
-- flag: true = the play was in the situation, false = in the split's universe but not in the situation,
-- so "with" and "without" are two rows over the same denominator universe. A play outside a split's
-- universe, or whose input column is null, produces no row for that split (never flag = false).
-- Per row: plays, epa_sum, success_sum (null success counts 0, as in team_week), explosive (pass play
-- gaining >= 20 yards, run >= 10; null yards count 0).
--
-- Universes (a "dropback" here is a pass = 1 play, sacks included):
--   blitz                      dropbacks with n_blitzers not null (FTN; 5+ rushers is not a separate split:
--                              in 2026 charting it equals blitz on every dropback but one)
--   play_action, screen        dropbacks with is_play_action / is_screen_pass not null (FTN)
--   motion, rpo                all plays with is_motion / is_rpo not null (FTN)
--   box_light, box_heavy       runs (rush = 1) with n_defense_box not null (FTN); two views of one
--                              split (light = box <= 6, heavy = box >= 7), flags mirror each other
--   shotgun, no_huddle         all plays (null counts as not in the situation)
--   early_down                 plays with down not null; flag = down in (1, 2)
--   third_down                 plays with down not null; flag = down = 3
--   red_zone, own_territory    plays with yardline_100 not null; flag = yardline_100 <= 20 / > 50
--   neutral_script             plays with wp not null; flag = wp between 0.2 and 0.8
--   deep_pass                  dropbacks with air_yards not null (sacks and throwaways drop out);
--                              flag = air_yards >= 15
--   vs_top10_def               offense rows only: plays against a top-ten defense (see below)
--   vs_top10_off               defense rows only: plays against a top-ten offense
--
-- FTN splits have no rows where the FTN column is null, which is every play before 2022 (coverage is 0
-- before 2022, about 84% in 2022 by the old join, ~97%+ since), so the share of FTN-split rows present
-- follows the plays table's own coverage and a season without charting has none.
--
-- Opponent tier: our opponent-adjusted EPA from the feature store (strength.epa_def_adj: EPA allowed,
-- lower is better; strength.epa_off_adj: EPA, higher is better). A game's feature row is stamped before
-- its kickoff, so only rows with known_as_of < kickoff_utc are read (a row without a kickoff is kept).
-- For week w each team's rating is its latest game row with week <= w in the season (a team on a bye
-- carries its last one), and the opponent is in the top ten when it ranks 1..10 among all teams on that
-- rating. Reading week <= w means the rating of a team's own week-w game, which is its pre-game value,
-- never anything after. No rows before Week 4 (ratings are mostly prior then). Games name historical
-- codes (STL, SD, OAK); they are mapped to the plays' current codes.
with ratings as (
    select
        f.season, f.week,
        case g.home_team when 'OAK' then 'LV' when 'SD' then 'LAC' when 'STL' then 'LA' else g.home_team end as h,
        case g.away_team when 'OAK' then 'LV' when 'SD' then 'LAC' when 'STL' then 'LA' else g.away_team end as a,
        f.game_id, f.side, f.feature, f.value, f.known_as_of,
        row_number() over (
            partition by f.game_id, f.side, f.feature order by f.known_as_of desc
        ) as rn
    from features f
    join games g on g.game_id = f.game_id
    where f.feature in ('strength.epa_def_adj', 'strength.epa_off_adj')
        and f.side in ('home', 'away')
        and (g.kickoff_utc is null or f.known_as_of < g.kickoff_utc)
),
game_ratings as (
    select
        season, week, case side when 'home' then h else a end as team,
        max(value) filter (where feature = 'strength.epa_def_adj') as def_adj,
        max(value) filter (where feature = 'strength.epa_off_adj') as off_adj
    from ratings
    where rn = 1
    group by season, week, side, h, a
),
weeks as (select distinct season, week from game_ratings where week >= 4),
team_weeks as (
    select w.season, w.week, r.team, r.def_adj, r.off_adj
    from weeks w
    join lateral (
        select * from game_ratings g
        where g.season = w.season and g.week <= w.week
        qualify row_number() over (partition by g.team order by g.week desc) = 1
    ) r on true
),
tier as (
    select
        season, week, team,
        rank() over (partition by season, week order by def_adj) <= 10 as top10_def,
        rank() over (partition by season, week order by off_adj desc) <= 10 as top10_off
    from team_weeks
    where def_adj is not null and off_adj is not null
),
base as (
    select
        p.season, p.week, p.season_type, p.game_id, p.posteam, p.defteam, p.epa,
        coalesce(p.success, 0) as success,
        case when p.pass = 1 then p.yards_gained >= 20 else p.yards_gained >= 10 end as is_explosive,
        p.pass = 1 as is_pass,
        -- split flags: null = outside the split's universe
        case when p.pass = 1 and p.n_blitzers is not null then p.n_blitzers >= 1 end as f_blitz,
        case when p.rush = 1 and p.n_defense_box is not null then p.n_defense_box <= 6 end as f_box_light,
        case when p.rush = 1 and p.n_defense_box is not null then p.n_defense_box >= 7 end as f_box_heavy,
        case when p.pass = 1 then p.is_play_action end as f_play_action,
        p.is_motion as f_motion,
        case when p.pass = 1 then p.is_screen_pass end as f_screen,
        p.is_rpo as f_rpo,
        coalesce(p.shotgun, 0) = 1 as f_shotgun,
        coalesce(p.no_huddle, 0) = 1 as f_no_huddle,
        p.down in (1, 2) as f_early_down,
        p.down = 3 as f_third_down,
        p.yardline_100 <= 20 as f_red_zone,
        p.yardline_100 > 50 as f_own_territory,
        p.wp between 0.2 and 0.8 as f_neutral_script,
        case when p.pass = 1 and p.air_yards is not null then p.air_yards >= 15 end as f_deep_pass,
        td.top10_def as f_vs_top10_def,
        "to".top10_off as f_vs_top10_off
    from plays p
    left join tier td on td.season = p.season and td.week = p.week and td.team = p.defteam
    left join tier "to" on "to".season = p.season and "to".week = p.week and "to".team = p.posteam
    where p.season_type in ('REG', 'POST')
        and p.epa is not null
        and (p.pass = 1 or p.rush = 1)
        and p.posteam is not null and p.defteam is not null
),
sides as (
    select *, posteam as team, 'off' as side from base
    union all
    select *, defteam as team, 'def' as side from base
),
long as (
    select season, week, game_id, team, side, epa, success, is_explosive, 'blitz' as split, f_blitz as flag from sides where f_blitz is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'box_light' as split, f_box_light from sides where f_box_light is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'box_heavy' as split, f_box_heavy from sides where f_box_heavy is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'play_action' as split, f_play_action from sides where f_play_action is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'motion' as split, f_motion from sides where f_motion is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'screen' as split, f_screen from sides where f_screen is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'rpo' as split, f_rpo from sides where f_rpo is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'shotgun' as split, f_shotgun from sides where f_shotgun is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'no_huddle' as split, f_no_huddle from sides where f_no_huddle is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'early_down' as split, f_early_down from sides where f_early_down is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'third_down' as split, f_third_down from sides where f_third_down is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'red_zone' as split, f_red_zone from sides where f_red_zone is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'own_territory' as split, f_own_territory from sides where f_own_territory is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'neutral_script' as split, f_neutral_script from sides where f_neutral_script is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'deep_pass' as split, f_deep_pass from sides where f_deep_pass is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'vs_top10_def' as split, f_vs_top10_def from sides where side = 'off' and f_vs_top10_def is not null
    union all select season, week, game_id, team, side, epa, success, is_explosive, 'vs_top10_off' as split, f_vs_top10_off from sides where side = 'def' and f_vs_top10_off is not null
)
select
    season, week, game_id, team, side, split, flag,
    count(*) as plays,
    sum(epa) as epa_sum,
    sum(success) as success_sum,
    sum(case when is_explosive then 1 else 0 end) as explosive
from long
group by season, week, game_id, team, side, split, flag
order by season, week, game_id, team, side, split, flag
