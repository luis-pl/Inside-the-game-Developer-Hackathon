-- Coverage and example analyses for SYNTHETIC 3.0.0. SELECT only.
DECLARE @match_id int=900001;

-- Presence is tested per match, rather than relying on a type catalog.
SELECT match_id,type_id,type_name,COUNT(*) n FROM analytics.events
WHERE match_id BETWEEN 900001 AND 900010
GROUP BY match_id,type_id,type_name ORDER BY match_id,type_id;

-- Interceptions: who, when and where. Quit(es)/tackles are separate below.
SELECT player_id,team_id,period,period_time_ms,location_x,location_y,
 JSON_VALUE(details,'$.interception.outcome.name') outcome
FROM analytics.events WHERE match_id=@match_id AND type_id=10 ORDER BY event_index;

-- Dribble success: NULL when there are no attempts.
SELECT team_id,player_id,COUNT(*) attempts,
 SUM(CASE WHEN JSON_VALUE(details,'$.dribble.outcome.id')='8' THEN 1 ELSE 0 END) completed,
 1.0*SUM(CASE WHEN JSON_VALUE(details,'$.dribble.outcome.id')='8' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0) success_rate
FROM analytics.events WHERE match_id=@match_id AND type_id=14 GROUP BY team_id,player_id;

-- Carries: displacement in metres, distinguished from path length in tracking.
SELECT event_id,team_id,player_id,period,period_time_ms,duration,
 location_x*105.0/120 start_attacking_x_m,location_y*68.0/80 start_attacking_y_m,
 TRY_CONVERT(float,JSON_VALUE(details,'$.carry.end_location[0]'))*105/120 end_attacking_x_m,
 TRY_CONVERT(float,JSON_VALUE(details,'$.carry.end_location[1]'))*68/80 end_attacking_y_m
FROM analytics.events WHERE match_id=@match_id AND type_id=43 ORDER BY event_index;

-- Tackles won. Exclude Aerial Lost and do not count Dispossessed again.
SELECT player_id,team_id,COUNT(*) tackles,
 SUM(CASE WHEN JSON_VALUE(details,'$.duel.outcome.id') IN('4','16','17') THEN 1 ELSE 0 END) won
FROM analytics.events WHERE match_id=@match_id AND type_id=4 AND JSON_VALUE(details,'$.duel.type.id')='11'
GROUP BY team_id,player_id;

-- One row per aerial contest, both perspectives; no double counting.
SELECT lost.event_id contest_id,lost.player_id losing_player,won.player_id winning_player,
 lost.period,lost.period_time_ms,lost.location_x,lost.location_y
FROM analytics.events lost JOIN analytics.event_relations r ON r.event_id=lost.event_id
JOIN analytics.events won ON won.event_id=r.related_event_id AND won.match_id=lost.match_id
WHERE lost.match_id=@match_id AND lost.type_id=4 AND JSON_VALUE(lost.details,'$.duel.type.id')='10'
 AND won.type_id=9 AND JSON_VALUE(won.details,'$.clearance.aerial_won')='true';

-- Substitutions: next tracking sample is the identity handoff.
SELECT team_id,player_id outgoing_player,
 TRY_CONVERT(int,JSON_VALUE(details,'$.substitution.replacement.id')) incoming_player,
 period,period_time_ms,JSON_VALUE(details,'$.substitution.outcome.name') reason
FROM analytics.events WHERE match_id=@match_id AND type_id=19 ORDER BY event_index;

-- Actual playing time: 2701 boundary samples represent 2700 seconds.
WITH ticks AS (
 SELECT run_id,period,frame_index,period_time_ms,
 LEAD(period_time_ms) OVER(PARTITION BY run_id,period ORDER BY period_time_ms) next_ms
 FROM analytics.tracking_frames WHERE match_id=@match_id
)
SELECT p.team_id,p.player_id,SUM((t.next_ms-t.period_time_ms)/1000.0)/60 minutes_on_pitch
FROM ticks t JOIN analytics.tracking_player_positions p ON p.run_id=t.run_id AND p.period=t.period AND p.frame_index=t.frame_index
WHERE p.is_on_pitch=1 AND p.position_status='available' AND t.next_ms IS NOT NULL
GROUP BY p.team_id,p.player_id;

-- Restarts and body/height variety, including headers and corners/throw-ins.
SELECT COALESCE(JSON_VALUE(pass_type,'$.name'),'Regular') restart,
 JSON_VALUE(height,'$.name') height,JSON_VALUE(body_part,'$.name') body_part,COUNT(*) n
FROM analytics.event_passes WHERE match_id=@match_id
GROUP BY JSON_VALUE(pass_type,'$.name'),JSON_VALUE(height,'$.name'),JSON_VALUE(body_part,'$.name');
