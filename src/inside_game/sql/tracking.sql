DECLARE @match int=?, @run uniqueidentifier=?, @period int=?, @start bigint=?, @end bigint=?, @stride int=?, @team int=?, @player int=?;
SELECT f.period,f.frame_index,f.period_time_ms,f.ball_in_play
FROM analytics.tracking_frames f WHERE f.match_id=@match AND f.run_id=@run AND f.period=@period
 AND f.period_time_ms>=@start AND f.period_time_ms<@end AND (f.period_time_ms-@start)%(@stride*1000)=0 ORDER BY f.frame_index;
SELECT p.period,p.frame_index,p.player_id,p.team_id,p.x_m,p.y_m,p.is_on_pitch,p.position_status,p.sample_method,p.confidence,p.on_pitch_slot
FROM analytics.tracking_player_positions p JOIN analytics.tracking_frames f ON f.run_id=p.run_id AND f.period=p.period AND f.frame_index=p.frame_index
WHERE p.match_id=@match AND p.run_id=@run AND p.period=@period AND p.is_on_pitch=1
 AND f.period_time_ms>=@start AND f.period_time_ms<@end AND (f.period_time_ms-@start)%(@stride*1000)=0
 AND (@team IS NULL OR p.team_id=@team) AND (@player IS NULL OR p.player_id=@player) ORDER BY p.frame_index,p.team_id,p.player_id;
SELECT b.period,b.frame_index,b.x_m,b.y_m,b.z_m,b.position_status,b.sample_method,b.confidence
FROM analytics.tracking_ball_positions b JOIN analytics.tracking_frames f ON f.run_id=b.run_id AND f.period=b.period AND f.frame_index=b.frame_index
WHERE b.match_id=@match AND b.run_id=@run AND b.period=@period AND f.period_time_ms>=@start AND f.period_time_ms<@end
 AND (f.period_time_ms-@start)%(@stride*1000)=0 ORDER BY b.frame_index;
