// Read-only evidence for the hackathon's data/MCP operation catalogue.
import { writeFileSync } from 'node:fs';
import { connect, model, safeError } from './connection.mjs';
const pool=await connect(),evidence={observedAt:new Date().toISOString(),status:'running',source:'Azure SQL, analytics views and metadata; SELECT only',sections:{}};
const queries={
 tableCounts:model.tables.map(t=>`SELECT '${t.name}' table_name,COUNT_BIG(*) row_count FROM statsbomb.[${t.name}]`).join(' UNION ALL '),
 columns:`SELECT t.name table_name,c.name column_name,ty.name data_type,c.max_length,c.is_nullable,c.is_computed
  FROM sys.tables t JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id
  WHERE t.schema_id=SCHEMA_ID('statsbomb') ORDER BY t.name,c.column_id`,
 eventTypes:`SELECT type_id,type_name,COUNT(*) events,COUNT(DISTINCT match_id) matches,COUNT(DISTINCT player_id) players,
  MIN(duration) min_duration,MAX(duration) max_duration FROM analytics.events GROUP BY type_id,type_name ORDER BY type_id`,
 matches:`SELECT m.match_id,m.match_date,m.home_score,m.away_score,JSON_VALUE(m.raw_payload,'$.version') generator_version,
  (SELECT COUNT(*) FROM analytics.events e WHERE e.match_id=m.match_id) events,
  (SELECT COUNT(*) FROM analytics.shots s WHERE s.match_id=m.match_id) shots,
  (SELECT SUM(xg) FROM analytics.shots s WHERE s.match_id=m.match_id) total_xg,
  (SELECT COUNT(*) FROM analytics.shots s WHERE s.match_id=m.match_id AND is_on_target=1) shots_on_target
  FROM analytics.matches m ORDER BY m.match_id`,
 shotOutcomes:`SELECT JSON_VALUE(outcome,'$.id') outcome_id,JSON_VALUE(outcome,'$.name') outcome_name,COUNT(*) n,
  MIN(statsbomb_xg) min_xg,MAX(statsbomb_xg) max_xg FROM analytics.event_shots GROUP BY JSON_VALUE(outcome,'$.id'),JSON_VALUE(outcome,'$.name')`,
 shotCoverage:`SELECT COUNT(*) shots,COUNT(statsbomb_xg) xg_present,COUNT(key_pass_id) assisted_shots,
  SUM(CASE WHEN first_time=1 THEN 1 ELSE 0 END) first_time_true,COUNT(first_time) first_time_present,
  SUM(CASE WHEN open_goal=1 THEN 1 ELSE 0 END) open_goal_true,COUNT(open_goal) open_goal_present,
  COUNT(follows_dribble) follows_dribble_present,COUNT(aerial_won) aerial_won_present,COUNT(deflected) deflected_present,
  COUNT(DISTINCT JSON_VALUE(shot_type,'$.id')) shot_types,COUNT(DISTINCT JSON_VALUE(body_part,'$.id')) body_parts FROM analytics.event_shots`,
 passOutcomes:`SELECT COALESCE(JSON_VALUE(outcome,'$.id'),'complete') outcome_id,JSON_VALUE(outcome,'$.name') outcome_name,COUNT(*) n,
  COUNT(recipient_player_id) known_recipient FROM analytics.event_passes GROUP BY JSON_VALUE(outcome,'$.id'),JSON_VALUE(outcome,'$.name')`,
 passTypes:`SELECT COALESCE(JSON_VALUE(pass_type,'$.name'),'Regular') pass_type,JSON_VALUE(height,'$.name') height,
  JSON_VALUE(body_part,'$.name') body_part,COUNT(*) n FROM analytics.event_passes
  GROUP BY JSON_VALUE(pass_type,'$.name'),JSON_VALUE(height,'$.name'),JSON_VALUE(body_part,'$.name')`,
 passCoverage:`SELECT COUNT(*) passes,COUNT(length) length_present,COUNT(angle) angle_present,COUNT(end_x) endpoint_present,
  SUM(CASE WHEN shot_assist=1 THEN 1 ELSE 0 END) shot_assists,SUM(CASE WHEN goal_assist=1 THEN 1 ELSE 0 END) goal_assists,
  SUM(CASE WHEN [cross]=1 THEN 1 ELSE 0 END) crosses,COUNT([cross]) cross_present,
  COUNT(cut_back) cut_back_present,COUNT([switch]) switch_present,COUNT(through_ball) through_ball_present,
  COUNT(aerial_won) aerial_won_present,COUNT(backheel) backheel_present,COUNT(deflected) deflected_present,
  COUNT(technique) technique_present FROM analytics.event_passes`,
 flags:`SELECT type_id,COUNT(*) n,COUNT(duration) duration_present,COUNT(under_pressure) under_pressure_present,
  SUM(CASE WHEN under_pressure=1 THEN 1 ELSE 0 END) under_pressure_true,
  SUM(CASE WHEN counterpress=1 THEN 1 ELSE 0 END) counterpress_true,COUNT(off_camera) off_camera_present,COUNT([out]) out_present
  FROM analytics.events GROUP BY type_id ORDER BY type_id`,
 detailKeys:`SELECT e.type_id,j.[key] detail_key,COUNT(*) n FROM analytics.events e CROSS APPLY OPENJSON(e.details) j GROUP BY e.type_id,j.[key] ORDER BY e.type_id,j.[key]`,
 defensiveOutcomes:`SELECT e.type_id,COALESCE(JSON_VALUE(details,'$.duel.outcome.name'),JSON_VALUE(details,'$."50_50".outcome.name'),JSON_VALUE(details,'$.interception.outcome.name')) outcome,COUNT(*) n
  FROM analytics.events e WHERE type_id IN(4,10,33) GROUP BY e.type_id,COALESCE(JSON_VALUE(details,'$.duel.outcome.name'),JSON_VALUE(details,'$."50_50".outcome.name'),JSON_VALUE(details,'$.interception.outcome.name'))`,
 possessions:`SELECT match_id,COUNT(DISTINCT possession) possessions,MIN(possession) min_id,MAX(possession) max_id,
  SUM(CASE WHEN possession IS NULL THEN 1 ELSE 0 END) without_possession FROM analytics.events GROUP BY match_id`,
 sameTimePossessions:`SELECT COUNT(*) ambiguous_same_time FROM (SELECT match_id,period,period_time_ms FROM analytics.events WHERE possession IS NOT NULL GROUP BY match_id,period,period_time_ms HAVING COUNT(DISTINCT possession_team_id)>1) a`,
 tracking:`SELECT r.match_id,r.run_id,r.sample_rate_hz,r.pitch_length_m,r.pitch_width_m,r.generator_version,r.max_event_offset_ms,
  p.period,p.duration_ms,p.home_attacks_positive_x FROM analytics.tracking_runs r JOIN analytics.tracking_periods p ON p.run_id=r.run_id ORDER BY r.match_id,p.period`,
 trackingCoverage:`SELECT position_status,sample_method,is_on_pitch,COUNT_BIG(*) rows,MIN(confidence) min_confidence,MAX(confidence) max_confidence,
  MIN(x_m) min_x,MAX(x_m) max_x,MIN(y_m) min_y,MAX(y_m) max_y FROM analytics.tracking_player_positions GROUP BY position_status,sample_method,is_on_pitch`,
 rosterCoverage:`SELECT l.team_id,COUNT(DISTINCT l.player_id) registered_players,
  COUNT(DISTINCT CASE WHEN p.player_id IS NOT NULL THEN l.player_id END) players_with_tracking
  FROM analytics.match_lineups l LEFT JOIN (SELECT DISTINCT match_id,team_id,player_id FROM analytics.tracking_player_positions) p
  ON p.match_id=l.match_id AND p.team_id=l.team_id AND p.player_id=l.player_id GROUP BY l.team_id`,
 gameTime:`WITH spans AS (SELECT f.run_id,f.period,f.period_time_ms,f.ball_in_play,
  LEAD(f.period_time_ms) OVER(PARTITION BY f.run_id,f.period ORDER BY f.period_time_ms) next_ms FROM analytics.tracking_frames f)
  SELECT SUM(CASE WHEN ball_in_play=1 THEN (next_ms-period_time_ms)/1000.0 ELSE 0 END) live_seconds,
  SUM(CASE WHEN ball_in_play=0 THEN (next_ms-period_time_ms)/1000.0 ELSE 0 END) dead_seconds,
  SUM((next_ms-period_time_ms)/1000.0) sampled_seconds FROM spans`,
 frames360:`SELECT COUNT(*) frames,MIN(n) min_players,MAX(n) max_players,COUNT(DISTINCT type_id) event_types FROM
  (SELECT f.event_id,e.type_id,COUNT(p.frame_player_index) n FROM analytics.frames_360 f JOIN analytics.events e ON e.event_id=f.event_id
  JOIN analytics.frame_360_players p ON p.event_id=f.event_id GROUP BY f.event_id,e.type_id) x`,
 tactics:`SELECT e.type_id,t.formation,COUNT(*) n FROM analytics.event_tactics t JOIN analytics.events e ON e.event_id=t.event_id GROUP BY e.type_id,t.formation`,
 discipline:`SELECT card_type,COUNT(*) n FROM analytics.lineup_cards GROUP BY card_type`,
 spatialProof:`WITH target AS(SELECT TOP(1) * FROM analytics.shots ORDER BY match_id,period,period_time_ms)
  SELECT t.event_id,t.match_id,t.team_id,t.player_id,t.period,t.period_time_ms,l.run_id,l.frame_index,p.team_id position_team,p.player_id position_player,p.x_m,p.y_m,p.on_pitch_slot,
  b.x_m ball_x_m,b.y_m ball_y_m,b.z_m ball_z_m,pd.home_attacks_positive_x FROM target t
  JOIN analytics.event_tracking_links l ON l.event_id=t.event_id
  JOIN analytics.tracking_player_positions p ON p.run_id=l.run_id AND p.period=l.period AND p.frame_index=l.frame_index
  JOIN analytics.tracking_ball_positions b ON b.run_id=l.run_id AND b.period=l.period AND b.frame_index=l.frame_index
  JOIN analytics.tracking_periods pd ON pd.run_id=l.run_id AND pd.period=l.period`,
 graphProof:`SELECT e.team_id,e.player_id source_player,p.recipient_player_id target_player,COUNT(*) passes,
  AVG(e.location_x) mean_start_x,AVG(e.location_y) mean_start_y FROM analytics.events e JOIN analytics.event_passes p ON p.event_id=e.event_id
  WHERE e.match_id=900001 AND JSON_VALUE(p.outcome,'$.id') IS NULL AND p.recipient_player_id IS NOT NULL
  GROUP BY e.team_id,e.player_id,p.recipient_player_id ORDER BY e.team_id,e.player_id,p.recipient_player_id`
};
try{
 for(const [name,query] of Object.entries(queries)){
  const result=await pool.request().query(query);evidence.sections[name]=result.recordset;
  console.log(JSON.stringify({section:name,rows:result.recordset.length}));
 }
 evidence.status='passed';
}catch(e){evidence.status='failed';evidence.error=safeError(e);console.error(JSON.stringify(evidence.error));process.exitCode=1;}
finally{
 writeFileSync(new URL('../../docs/data-capabilities-evidence.json',import.meta.url),JSON.stringify(evidence,null,2)+'\n');await pool.close();
}
