-- Additional publishing rules; callable for loading or already published data.
CREATE OR ALTER PROCEDURE statsbomb.validate_semantics @match_id int AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM statsbomb.event_shots s JOIN statsbomb.events e ON e.event_id=s.event_id
   JOIN statsbomb.event_passes p ON p.event_id=s.key_pass_id JOIN statsbomb.events pe ON pe.event_id=p.event_id
   WHERE s.match_id=@match_id AND (JSON_VALUE(p.outcome,'$.id') IS NOT NULL
     OR (p.recipient_player_id IS NOT NULL AND p.recipient_player_id<>e.player_id)
     OR pe.period<>e.period OR pe.event_index>=e.event_index
     OR pe.period_time_ms+COALESCE(pe.duration,0)*1000>e.period_time_ms))
   THROW 51021,'A key pass must be completed, precede reception/shot, and target the shooter when known.',1;
 IF EXISTS(SELECT 1 FROM statsbomb.event_shots WHERE match_id=@match_id AND
   ((JSON_VALUE(outcome,'$.id')='96' AND JSON_VALUE(outcome,'$.name')<>'Blocked')
    OR (JSON_VALUE(outcome,'$.id')='98' AND JSON_VALUE(outcome,'$.name')<>'Off T')
    OR (JSON_VALUE(outcome,'$.id')='97' AND JSON_VALUE(outcome,'$.name')<>'Goal')
    OR (JSON_VALUE(outcome,'$.id')='100' AND JSON_VALUE(outcome,'$.name')<>'Saved')
    OR end_z<0)) THROW 51022,'Shot outcome code/name or endpoint height is invalid.',1;
 IF EXISTS(SELECT possession FROM statsbomb.events WHERE match_id=@match_id AND possession IS NOT NULL
   GROUP BY possession HAVING COUNT(DISTINCT possession_team_id)>1)
   THROW 51023,'A possession cannot have multiple possession teams.',1;

 -- The following assumptions describe this controlled synthetic scenario,
 -- rather than imposing its simplified rules on future real-data imports.
 IF EXISTS(SELECT 1 FROM statsbomb.matches WHERE match_id=@match_id
   AND JSON_VALUE(raw_payload,'$.generator')='inside-game-demo' AND JSON_VALUE(raw_payload,'$.version')='2.0.0')
 BEGIN
  IF EXISTS(SELECT 1 FROM statsbomb.matches m JOIN statsbomb.match_teams mt ON mt.match_id=m.match_id
    OUTER APPLY(SELECT COUNT(*) n FROM statsbomb.event_shots s WHERE s.match_id=m.match_id AND s.team_id=mt.team_id AND JSON_VALUE(s.outcome,'$.id')='97') g
    WHERE m.match_id=@match_id AND ((mt.side='home' AND m.home_score<>g.n) OR (mt.side='away' AND m.away_score<>g.n)))
    THROW 51024,'Synthetic match score differs from its goal events.',1;
  IF EXISTS(SELECT 1 FROM statsbomb.events e JOIN statsbomb.event_tracking_links l ON l.event_id=e.event_id
    JOIN statsbomb.tracking_player_positions p ON p.run_id=l.run_id AND p.period=l.period AND p.frame_index=l.frame_index AND p.player_id=e.player_id
    JOIN statsbomb.tracking_ball_positions b ON b.run_id=l.run_id AND b.period=l.period AND b.frame_index=l.frame_index
    WHERE e.match_id=@match_id AND e.type_id IN(17,4,33,21,22) AND (POWER(p.x_m-b.x_m,2)+POWER(p.y_m-b.y_m,2)>9 OR p.x_m IS NULL OR b.x_m IS NULL))
    THROW 51025,'A pressure/duel/foul actor is too far from the ball.',1;
  IF EXISTS(SELECT 1 FROM statsbomb.tracking_frames f
    OUTER APPLY(SELECT COUNT(*) n FROM statsbomb.tracking_player_positions p WHERE p.run_id=f.run_id AND p.period=f.period AND p.frame_index=f.frame_index AND p.is_on_pitch=1 AND p.position_status='available') p
    WHERE f.match_id=@match_id AND (p.n<>22 OR NOT EXISTS(SELECT 1 FROM statsbomb.tracking_ball_positions b WHERE b.run_id=f.run_id AND b.period=f.period AND b.frame_index=f.frame_index AND b.position_status='available')))
    THROW 51026,'Synthetic tracking requires 22 active players and an available ball for every frame.',1;
 END;
END;
GO
IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE name='ck_shot_height_nonnegative' AND parent_object_id=OBJECT_ID('statsbomb.event_shots'))
 ALTER TABLE statsbomb.event_shots WITH CHECK ADD CONSTRAINT ck_shot_height_nonnegative CHECK(end_z>=0);
GO
