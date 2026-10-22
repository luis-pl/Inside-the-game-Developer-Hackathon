-- Queries for Azure SQL. analytics exposes published/validated matches only.
-- Synthetic xG is a toy demo value. Tracking uses FIXED pitch metres; events use
-- team-oriented 120x80 coordinates. Never compare them without a transform.
DECLARE @match_id int=900001, @period int=1, @second int=600, @player_id int=110;

-- How many shots, shots on target, goals and total xG, per team.
SELECT s.team_id,t.team_name,COUNT(*) shots,SUM(CONVERT(int,s.is_on_target)) shots_on_target,
 SUM(CASE WHEN outcome_id=97 THEN 1 ELSE 0 END) goals,SUM(xg) xg
FROM analytics.shots s JOIN analytics.teams t ON t.team_id=s.team_id
WHERE s.match_id=@match_id AND s.period BETWEEN 1 AND 4
GROUP BY s.team_id,t.team_name;

-- When and where each shot on target happened. Period is necessary to avoid
-- ambiguity between stoppage time and the next period's global minute.
SELECT period,period_time_ms,minute,second,team_id,player_id,location_x,location_y,xg,outcome_name,is_synthetic
FROM analytics.shots WHERE match_id=@match_id AND is_on_target=1 AND period BETWEEN 1 AND 4
ORDER BY period,period_time_ms,event_id;

-- All active players and the ball at an exact sampled second.
-- Filter a run explicitly when the match has multiple generated versions.
SELECT f.run_id,f.period,f.period_time_ms,p.player_id,p.team_id,p.x_m,p.y_m,p.position_status,p.sample_method,
 b.x_m ball_x_m,b.y_m ball_y_m,b.z_m ball_z_m
FROM analytics.tracking_frames f JOIN analytics.tracking_player_positions p
 ON p.run_id=f.run_id AND p.period=f.period AND p.frame_index=f.frame_index
LEFT JOIN analytics.tracking_ball_positions b
 ON b.run_id=f.run_id AND b.period=f.period AND b.frame_index=f.frame_index
WHERE f.match_id=@match_id AND f.period=@period AND f.period_time_ms=CONVERT(bigint,@second)*1000;

-- Player heatmap: 5x5 metre bins weighted by seconds, not by event count.
-- LEAD is computed before filtering positions, so missing samples are not
-- silently bridged. Uniform 1Hz demo data needs no interpolation.
WITH ticks AS (
 SELECT f.*,LEAD(f.period_time_ms) OVER(PARTITION BY f.run_id,f.period ORDER BY f.period_time_ms) next_ms
 FROM analytics.tracking_frames f WHERE f.match_id=@match_id
)
SELECT p.run_id,FLOOR(p.x_m/5)*5 cell_x_m,FLOOR(p.y_m/5)*5 cell_y_m,
 SUM((t.next_ms-t.period_time_ms)/1000.0) seconds_in_cell
FROM ticks t JOIN analytics.tracking_player_positions p
 ON p.run_id=t.run_id AND p.period=t.period AND p.frame_index=t.frame_index
WHERE p.player_id=@player_id AND p.is_on_pitch=1 AND p.position_status='available' AND t.next_ms IS NOT NULL
GROUP BY p.run_id,FLOOR(p.x_m/5),FLOOR(p.y_m/5);

-- Tackles won, separate from aerial duels and 50/50s.
SELECT team_id,player_id,COUNT(*) tackles,
 SUM(CASE WHEN TRY_CONVERT(int,JSON_VALUE(details,'$.duel.outcome.id')) IN(4,15,16,17) THEN 1 ELSE 0 END) won
FROM analytics.events WHERE match_id=@match_id AND type_id=4
 AND TRY_CONVERT(int,JSON_VALUE(details,'$.duel.type.id'))=11
GROUP BY team_id,player_id;

-- Pressure actions. Summed duration can overlap between simultaneous actions;
-- it is not the team's unique time spent pressing. under_pressure is received pressure.
SELECT team_id,player_id,COUNT(*) pressure_actions,SUM(duration) sum_action_seconds,
 SUM(CASE WHEN counterpress=1 THEN 1 ELSE 0 END) counterpress_actions
FROM analytics.events WHERE match_id=@match_id AND type_id=17 GROUP BY team_id,player_id;

-- Players within 5 metres of the shooter, using identified tracking positions.
-- Anonymous 360 rows are not used to infer player identity.
SELECT e.event_id,e.period,e.period_time_ms,other.player_id,other.team_id,
 SQRT(POWER(other.x_m-actor.x_m,2)+POWER(other.y_m-actor.y_m,2)) distance_m
FROM analytics.events e JOIN analytics.event_tracking_links l ON l.event_id=e.event_id
JOIN analytics.tracking_player_positions actor ON actor.run_id=l.run_id AND actor.period=l.period
 AND actor.frame_index=l.frame_index AND actor.player_id=e.player_id
JOIN analytics.tracking_player_positions other ON other.run_id=l.run_id AND other.period=l.period
 AND other.frame_index=l.frame_index AND other.player_id<>actor.player_id
WHERE e.match_id=@match_id AND e.type_id=16 AND actor.position_status='available' AND other.position_status='available'
 AND POWER(other.x_m-actor.x_m,2)+POWER(other.y_m-actor.y_m,2)<=25
ORDER BY e.period,e.period_time_ms,distance_m;
