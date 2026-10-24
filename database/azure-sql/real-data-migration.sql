-- Extend provenance honestly. Existing synthetic rows remain explicitly synthetic.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
ALTER TABLE statsbomb.tracking_runs DROP CONSTRAINT ck_tracking_runs_5;
ALTER TABLE statsbomb.tracking_runs WITH CHECK ADD CONSTRAINT ck_tracking_runs_5 CHECK (
 is_synthetic=1 OR
 (is_synthetic=0 AND COALESCE(JSON_VALUE(config,'$.is_synthetic'),'')='false'
  AND COALESCE(JSON_VALUE(config,'$.data_kind'),'') IN ('real_anonymized','real_pseudonymized')
  AND COALESCE(JSON_VALUE(config,'$.provider'),'') IN ('Metrica Sports','SkillCorner')));
ALTER TABLE statsbomb.tracking_player_positions DROP CONSTRAINT ck_tracking_player_positions_2;
ALTER TABLE statsbomb.tracking_player_positions WITH CHECK ADD CONSTRAINT ck_tracking_player_positions_2
 CHECK(sample_method IN ('observed','generated','interpolated','extrapolated','missing'));
ALTER TABLE statsbomb.tracking_ball_positions DROP CONSTRAINT ck_tracking_ball_positions_2;
ALTER TABLE statsbomb.tracking_ball_positions WITH CHECK ADD CONSTRAINT ck_tracking_ball_positions_2
 CHECK(sample_method IN ('observed','generated','interpolated','extrapolated','missing'));
COMMIT;
