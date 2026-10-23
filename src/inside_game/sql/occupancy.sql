DECLARE @match int=?, @run uniqueidentifier=?, @period int=?, @start bigint=?, @end bigint=?, @team int=?, @player int=?, @grid int=?,
 @orient bit=?, @xmin float=?, @xmax float=?, @ymin float=?, @ymax float=?;
WITH ticks AS (
 SELECT f.*,LEAD(period_time_ms) OVER(PARTITION BY run_id,period ORDER BY frame_index) next_ms
 FROM analytics.tracking_frames f WHERE match_id=@match AND run_id=@run
), points AS (
 SELECT p.player_id,p.team_id,p.period,f.period_time_ms,f.next_ms,
 CASE WHEN @orient=0 OR (pd.home_attacks_positive_x=1 AND mt.side='home') OR (pd.home_attacks_positive_x=0 AND mt.side='away') THEN p.x_m ELSE r.pitch_length_m-p.x_m END x,
 CASE WHEN @orient=0 OR (pd.home_attacks_positive_x=1 AND mt.side='home') OR (pd.home_attacks_positive_x=0 AND mt.side='away') THEN p.y_m ELSE r.pitch_width_m-p.y_m END y
 FROM analytics.tracking_player_positions p JOIN ticks f ON f.run_id=p.run_id AND f.period=p.period AND f.frame_index=p.frame_index
 JOIN analytics.tracking_periods pd ON pd.run_id=p.run_id AND pd.period=p.period JOIN analytics.tracking_runs r ON r.run_id=p.run_id
 JOIN analytics.match_teams mt ON mt.match_id=p.match_id AND mt.team_id=p.team_id
 WHERE p.match_id=@match AND p.run_id=@run AND p.is_on_pitch=1 AND p.position_status='available'
 AND (@team IS NULL OR p.team_id=@team) AND (@player IS NULL OR p.player_id=@player)
), marked AS (
 SELECT *,CASE WHEN x>=@xmin AND (x<@xmax OR (@xmax NOT IN(35,70) AND x<=@xmax)) AND y>=@ymin AND y<=@ymax THEN 1 ELSE 0 END inside,
 LAG(x) OVER(PARTITION BY player_id,period ORDER BY period_time_ms) px,
 LAG(y) OVER(PARTITION BY player_id,period ORDER BY period_time_ms) py,
 LAG(period_time_ms) OVER(PARTITION BY player_id,period ORDER BY period_time_ms) prev_ms
 FROM points
), spans AS (
 SELECT *,CASE WHEN next_ms-period_time_ms=1000 THEN (CASE WHEN next_ms<@end THEN next_ms ELSE @end END-CASE WHEN period_time_ms>@start THEN period_time_ms ELSE @start END)/1000.0 ELSE 0 END seconds
 FROM marked WHERE (@period IS NULL OR period=@period) AND period_time_ms<@end AND next_ms>@start
)
SELECT team_id,player_id,FLOOR(x/@grid)*@grid cell_x_m,FLOOR(y/@grid)*@grid cell_y_m,
 SUM(CASE WHEN inside=1 THEN seconds ELSE 0 END) seconds_in_zone,
 SUM(CASE WHEN inside=1 AND period_time_ms>=@start AND period_time_ms-prev_ms=1000 AND (px<@xmin OR px>@xmax OR (@xmax IN(35,70) AND px=@xmax) OR py<@ymin OR py>@ymax) THEN 1 ELSE 0 END) entries,
 SUM(seconds) valid_seconds
FROM spans GROUP BY team_id,player_id,FLOOR(x/@grid),FLOOR(y/@grid) ORDER BY team_id,player_id,cell_x_m,cell_y_m;
