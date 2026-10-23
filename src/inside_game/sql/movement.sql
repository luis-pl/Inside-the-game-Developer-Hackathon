DECLARE @match int=?, @run uniqueidentifier=?, @period int=?, @start bigint=?, @end bigint=?, @team int=?, @player int=?;
WITH ticks AS (
 SELECT f.*,LEAD(period_time_ms) OVER(PARTITION BY run_id,period ORDER BY frame_index) next_ms
 FROM analytics.tracking_frames f WHERE match_id=@match AND run_id=@run
), points AS (
 SELECT p.*,f.period_time_ms,f.next_ms,
 LAG(p.x_m) OVER(PARTITION BY p.run_id,p.period,p.player_id ORDER BY p.frame_index) px,
 LAG(p.y_m) OVER(PARTITION BY p.run_id,p.period,p.player_id ORDER BY p.frame_index) py,
 LAG(f.period_time_ms) OVER(PARTITION BY p.run_id,p.period,p.player_id ORDER BY p.frame_index) prev_ms,
 LAG(p.position_status) OVER(PARTITION BY p.run_id,p.period,p.player_id ORDER BY p.frame_index) prev_status
 FROM analytics.tracking_player_positions p JOIN ticks f ON f.run_id=p.run_id AND f.period=p.period AND f.frame_index=p.frame_index
 WHERE p.match_id=@match AND p.run_id=@run AND p.is_on_pitch=1 AND (@team IS NULL OR p.team_id=@team) AND (@player IS NULL OR p.player_id=@player)
), segments AS (
 SELECT *,CASE WHEN position_status='available' AND prev_status='available' AND period_time_ms-prev_ms=1000
  AND prev_ms>=@start AND period_time_ms<=@end THEN SQRT(POWER(x_m-px,2)+POWER(y_m-py,2)) END distance_m,
 CASE WHEN position_status='available' AND next_ms-period_time_ms=1000 AND next_ms>@start AND period_time_ms<@end
  THEN (CASE WHEN next_ms<@end THEN next_ms ELSE @end END-CASE WHEN period_time_ms>@start THEN period_time_ms ELSE @start END)/1000.0 ELSE 0 END seconds
 FROM points WHERE (@period IS NULL OR period=@period)
)
SELECT team_id,player_id,SUM(seconds) covered_seconds,SUM(COALESCE(distance_m,0)) distance_m,
 MAX(distance_m) max_sampled_speed_m_s,SUM(CASE WHEN distance_m>5.5 THEN 1 ELSE 0 END) seconds_above_5_5_m_s
FROM segments GROUP BY team_id,player_id ORDER BY team_id,player_id;
