DECLARE @run uniqueidentifier=?, @ids nvarchar(max)=?;
WITH anchors AS(SELECT DISTINCT l.period,l.frame_index FROM analytics.event_tracking_links l
 WHERE l.run_id=@run AND l.event_id IN(SELECT TRY_CONVERT(uniqueidentifier,value) FROM OPENJSON(@ids)))
SELECT f.period,f.frame_index,f.period_time_ms,f.ball_in_play FROM analytics.tracking_frames f JOIN anchors a ON a.period=f.period AND a.frame_index=f.frame_index WHERE f.run_id=@run ORDER BY f.period,f.frame_index;
WITH anchors AS(SELECT DISTINCT l.period,l.frame_index FROM analytics.event_tracking_links l
 WHERE l.run_id=@run AND l.event_id IN(SELECT TRY_CONVERT(uniqueidentifier,value) FROM OPENJSON(@ids)))
SELECT p.period,p.frame_index,p.player_id,p.team_id,p.x_m,p.y_m,p.is_on_pitch,p.position_status,p.sample_method,p.confidence,p.on_pitch_slot
FROM analytics.tracking_player_positions p JOIN anchors a ON a.period=p.period AND a.frame_index=p.frame_index WHERE p.run_id=@run AND p.is_on_pitch=1 ORDER BY p.period,p.frame_index,p.player_id;
WITH anchors AS(SELECT DISTINCT l.period,l.frame_index FROM analytics.event_tracking_links l
 WHERE l.run_id=@run AND l.event_id IN(SELECT TRY_CONVERT(uniqueidentifier,value) FROM OPENJSON(@ids)))
SELECT b.period,b.frame_index,b.x_m,b.y_m,b.z_m,b.position_status,b.sample_method,b.confidence FROM analytics.tracking_ball_positions b JOIN anchors a ON a.period=b.period AND a.frame_index=b.frame_index WHERE b.run_id=@run ORDER BY b.period,b.frame_index;
