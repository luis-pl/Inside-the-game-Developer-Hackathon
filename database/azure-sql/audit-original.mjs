import { writeFileSync } from 'node:fs';
import { connect } from './connection.mjs';
const pool=await connect();
try {
 const q=await pool.request().query(`
 SELECT COUNT(*) wrong_shot_outcome_names FROM statsbomb.event_shots WHERE
  (JSON_VALUE(outcome,'$.id')='96' AND JSON_VALUE(outcome,'$.name')<>'Blocked') OR
  (JSON_VALUE(outcome,'$.id')='98' AND JSON_VALUE(outcome,'$.name')<>'Off T');
 SELECT COUNT(*) off_target_inside_goal FROM statsbomb.event_shots WHERE JSON_VALUE(outcome,'$.name')='Off T'
  AND ABS(end_x-120)<.001 AND ABS(end_y-40)<7.32/2*80/68 AND end_z BETWEEN 0 AND 2.44;
 SELECT COUNT(*) assist_to_other_player FROM statsbomb.event_shots s JOIN statsbomb.events e ON e.event_id=s.event_id
  JOIN statsbomb.event_passes p ON p.event_id=s.key_pass_id WHERE p.recipient_player_id<>e.player_id;
 SELECT COUNT(*) incomplete_pass_assists FROM statsbomb.event_shots s JOIN statsbomb.event_passes p ON p.event_id=s.key_pass_id WHERE p.outcome IS NOT NULL;
 SELECT COUNT(*) possession_conflicts FROM (SELECT match_id,possession FROM statsbomb.events GROUP BY match_id,possession HAVING COUNT(DISTINCT possession_team_id)>1) x;
 SELECT COUNT(*) distant_pressures,MAX(SQRT(POWER(p.x_m-b.x_m,2)+POWER(p.y_m-b.y_m,2))) max_distance_m
  FROM statsbomb.events e JOIN statsbomb.event_tracking_links l ON l.event_id=e.event_id
  JOIN statsbomb.tracking_player_positions p ON p.run_id=l.run_id AND p.period=l.period AND p.frame_index=l.frame_index AND p.player_id=e.player_id
  JOIN statsbomb.tracking_ball_positions b ON b.run_id=l.run_id AND b.period=l.period AND b.frame_index=l.frame_index
  WHERE e.type_id=17 AND POWER(p.x_m-b.x_m,2)+POWER(p.y_m-b.y_m,2)>100;
 SELECT match_id,home_score,away_score FROM statsbomb.matches ORDER BY match_id;
 WITH b AS (SELECT *,LAG(x_m) OVER(PARTITION BY run_id,period ORDER BY frame_index) px,LAG(y_m) OVER(PARTITION BY run_id,period ORDER BY frame_index) py FROM statsbomb.tracking_ball_positions)
 SELECT MAX(SQRT(POWER(x_m-px,2)+POWER(y_m-py,2))) max_ball_m_per_second FROM b;
 SELECT MIN(z_m) min_ball_z,MAX(z_m) max_ball_z FROM statsbomb.tracking_ball_positions;
 SELECT COUNT(*) outside_field FROM statsbomb.tracking_player_positions WHERE x_m NOT BETWEEN 0 AND 105 OR y_m NOT BETWEEN 0 AND 68;
 `);
 const labels=['outcomeCodes','shotGeometry','assistRecipient','assistCompletion','possessions','pressures','scores','ballSpeed','ballHeight','playerBounds'];
 const report=Object.fromEntries(q.recordsets.map((r,i)=>[labels[i],r]));
 writeFileSync(new URL('./audit-before.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report));
} finally {await pool.close();}
