-- Azure SQL / SQL Server. Fresh database only. Generated from model.json.

SET XACT_ABORT ON;
GO
CREATE SCHEMA statsbomb;
GO
CREATE SCHEMA analytics;
GO


CREATE FUNCTION statsbomb.clock_ms(@clock nvarchar(32)) RETURNS bigint WITH SCHEMABINDING AS
BEGIN
 DECLARE @c int=CHARINDEX(':',@clock),@sec nvarchar(16),@hours nvarchar(32),@mins nvarchar(2);
 IF @c<3 RETURN NULL;
 SET @hours=LEFT(@clock,@c-1); SET @mins=SUBSTRING(@clock,@c+1,2); SET @sec=SUBSTRING(@clock,@c+4,16);
 IF SUBSTRING(@clock,@c+3,1)<>':' OR @hours COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9]%'
   OR @mins COLLATE Latin1_General_100_BIN2 NOT LIKE '[0-5][0-9]'
   OR LEFT(@sec,2) COLLATE Latin1_General_100_BIN2 NOT LIKE '[0-5][0-9]'
   OR LEN(@sec)<2 OR LEN(@sec)>9 RETURN NULL;
 IF LEN(@sec)>2 AND (SUBSTRING(@sec,3,1)<>'.' OR LEN(@sec)<4
   OR SUBSTRING(@sec,4,6) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9]%') RETURN NULL;
 IF TRY_CONVERT(bigint,@hours)>1000000000 RETURN NULL;
 RETURN TRY_CONVERT(bigint,@hours)*3600000+TRY_CONVERT(bigint,@mins)*60000
   +TRY_CONVERT(bigint,FLOOR(TRY_CONVERT(decimal(12,6),@sec)*1000));
END;
GO


CREATE TABLE [statsbomb].[countries](
  [country_id] int NOT NULL,
  [name] nvarchar(256) NOT NULL,
  CONSTRAINT [pk_countries] PRIMARY KEY ([country_id])
);
GO

CREATE TABLE [statsbomb].[competitions](
  [competition_id] int NOT NULL,
  [competition_name] nvarchar(256) NOT NULL,
  [competition_gender] nvarchar(256) NULL,
  [competition_youth] bit NULL,
  [competition_international] bit NULL,
  [country_name] nvarchar(256) NULL,
  CONSTRAINT [pk_competitions] PRIMARY KEY ([competition_id])
);
GO

CREATE TABLE [statsbomb].[seasons](
  [season_id] int NOT NULL,
  [season_name] nvarchar(256) NOT NULL,
  CONSTRAINT [pk_seasons] PRIMARY KEY ([season_id])
);
GO

CREATE TABLE [statsbomb].[competition_seasons](
  [competition_id] int NOT NULL,
  [season_id] int NOT NULL,
  [match_updated] datetime2(6) NULL,
  [match_available] datetime2(6) NULL,
  [match_updated_360] datetime2(6) NULL,
  [match_available_360] datetime2(6) NULL,
  [raw_payload] nvarchar(max) NOT NULL,
  CONSTRAINT [pk_competition_seasons] PRIMARY KEY ([competition_id],[season_id]),
  CONSTRAINT [ck_competition_seasons_0] CHECK (ISJSON([raw_payload], OBJECT)=1)
);
GO

CREATE TABLE [statsbomb].[teams](
  [team_id] int NOT NULL,
  [team_name] nvarchar(256) NOT NULL,
  [gender] nvarchar(256) NULL,
  [country_id] int NULL,
  CONSTRAINT [pk_teams] PRIMARY KEY ([team_id])
);
GO

CREATE TABLE [statsbomb].[players](
  [player_id] int NOT NULL,
  [player_name] nvarchar(256) NOT NULL,
  [player_nickname] nvarchar(256) NULL,
  [country_id] int NULL,
  CONSTRAINT [pk_players] PRIMARY KEY ([player_id])
);
GO

CREATE TABLE [statsbomb].[managers](
  [manager_id] int NOT NULL,
  [name] nvarchar(256) NOT NULL,
  [nickname] nvarchar(256) NULL,
  [dob] date NULL,
  [country_id] int NULL,
  CONSTRAINT [pk_managers] PRIMARY KEY ([manager_id])
);
GO

CREATE TABLE [statsbomb].[stadiums](
  [stadium_id] int NOT NULL,
  [name] nvarchar(256) NOT NULL,
  [country_id] int NULL,
  CONSTRAINT [pk_stadiums] PRIMARY KEY ([stadium_id])
);
GO

CREATE TABLE [statsbomb].[referees](
  [referee_id] int NOT NULL,
  [name] nvarchar(256) NOT NULL,
  [country_id] int NULL,
  CONSTRAINT [pk_referees] PRIMARY KEY ([referee_id])
);
GO

CREATE TABLE [statsbomb].[matches](
  [match_id] int NOT NULL,
  [competition_id] int NOT NULL,
  [season_id] int NOT NULL,
  [match_date] date NOT NULL,
  [kick_off] time(6) NULL,
  [home_score] int NULL,
  [away_score] int NULL,
  [match_week] int NULL,
  [competition_stage_id] int NULL,
  [competition_stage_name] nvarchar(256) NULL,
  [stadium_id] int NULL,
  [referee_id] int NULL,
  [match_status] nvarchar(256) NULL,
  [match_status_360] nvarchar(256) NULL,
  [last_updated] datetime2(6) NULL,
  [last_updated_360] datetime2(6) NULL,
  [data_version] nvarchar(256) NULL,
  [shot_fidelity_version] nvarchar(256) NULL,
  [xy_fidelity_version] nvarchar(256) NULL,
  [raw_payload] nvarchar(max) NOT NULL,
  [data_status] nvarchar(16) NOT NULL DEFAULT 'loading',
  CHECK ([data_status] IN ('loading','ready')),
  CONSTRAINT [pk_matches] PRIMARY KEY ([match_id]),
  CONSTRAINT [ck_matches_0] CHECK ([home_score] >= 0),
  CONSTRAINT [ck_matches_1] CHECK ([away_score] >= 0),
  CONSTRAINT [ck_matches_2] CHECK (ISJSON([raw_payload], OBJECT)=1)
);
GO

CREATE TABLE [statsbomb].[match_teams](
  [match_id] int NOT NULL,
  [team_id] int NOT NULL,
  [side] nvarchar(256) NOT NULL,
  [team_group] nvarchar(256) NULL,
  [lineup_raw_payload] nvarchar(max) NULL,
  CONSTRAINT [pk_match_teams] PRIMARY KEY ([match_id],[team_id]),
  CONSTRAINT [uq_match_teams_0] UNIQUE ([match_id],[side]),
  CONSTRAINT [ck_match_teams_0] CHECK ([side] IN ('home','away')),
  CONSTRAINT [ck_match_teams_1] CHECK (ISJSON([lineup_raw_payload], OBJECT)=1)
);
GO

CREATE TABLE [statsbomb].[match_team_managers](
  [match_id] int NOT NULL,
  [team_id] int NOT NULL,
  [manager_index] int NOT NULL,
  [manager_id] int NOT NULL,
  CONSTRAINT [pk_match_team_managers] PRIMARY KEY ([match_id],[team_id],[manager_index]),
  CONSTRAINT [ck_match_team_managers_0] CHECK ([manager_index] >= 0)
);
GO

CREATE TABLE [statsbomb].[match_lineups](
  [match_id] int NOT NULL,
  [team_id] int NOT NULL,
  [player_id] int NOT NULL,
  [jersey_number] int NULL,
  [raw_payload] nvarchar(max) NOT NULL,
  CONSTRAINT [pk_match_lineups] PRIMARY KEY ([match_id],[team_id],[player_id]),
  CONSTRAINT [uq_match_lineups_0] UNIQUE ([match_id],[player_id]),
  CONSTRAINT [ck_match_lineups_0] CHECK ([jersey_number] >= 0),
  CONSTRAINT [ck_match_lineups_1] CHECK (ISJSON([raw_payload], OBJECT)=1)
);
GO

CREATE TABLE [statsbomb].[lineup_cards](
  [match_id] int NOT NULL,
  [team_id] int NOT NULL,
  [player_id] int NOT NULL,
  [card_index] int NOT NULL,
  [time] nvarchar(32) NULL,
  [card_type] nvarchar(256) NULL,
  [reason] nvarchar(256) NULL,
  [period] int NULL,
  CONSTRAINT [pk_lineup_cards] PRIMARY KEY ([match_id],[team_id],[player_id],[card_index]),
  CONSTRAINT [ck_lineup_cards_0] CHECK ([card_index] >= 0),
  CONSTRAINT [ck_lineup_cards_1] CHECK ([period] BETWEEN 1 AND 5)
);
GO

CREATE TABLE [statsbomb].[lineup_positions](
  [match_id] int NOT NULL,
  [team_id] int NOT NULL,
  [player_id] int NOT NULL,
  [position_index] int NOT NULL,
  [position_id] int NULL,
  [position] nvarchar(256) NULL,
  [from_time] nvarchar(32) NULL,
  [to_time] nvarchar(32) NULL,
  [from_period] int NULL,
  [to_period] int NULL,
  [start_reason] nvarchar(256) NULL,
  [end_reason] nvarchar(256) NULL,
  CONSTRAINT [pk_lineup_positions] PRIMARY KEY ([match_id],[team_id],[player_id],[position_index]),
  CONSTRAINT [ck_lineup_positions_0] CHECK ([position_index] >= 0),
  CONSTRAINT [ck_lineup_positions_1] CHECK ([from_period] BETWEEN 1 AND 5),
  CONSTRAINT [ck_lineup_positions_2] CHECK ([to_period] BETWEEN 1 AND 5)
);
GO

CREATE TABLE [statsbomb].[events](
  [event_id] uniqueidentifier NOT NULL,
  [match_id] int NOT NULL,
  [event_index] int NOT NULL,
  [period] int NOT NULL,
  [timestamp] nvarchar(32) NOT NULL,
  [minute] int NULL,
  [second] int NULL,
  [type_id] int NOT NULL,
  [type_name] nvarchar(256) NULL,
  [possession] int NULL,
  [possession_team_id] int NULL,
  [play_pattern_id] int NULL,
  [play_pattern_name] nvarchar(256) NULL,
  [team_id] int NULL,
  [player_id] int NULL,
  [position_id] int NULL,
  [position_name] nvarchar(256) NULL,
  [location_x] float(53) NULL,
  [location_y] float(53) NULL,
  [duration] float(53) NULL,
  [under_pressure] bit NULL,
  [counterpress] bit NULL,
  [off_camera] bit NULL,
  [out] bit NULL,
  [details] nvarchar(max) NULL,
  [raw_payload] nvarchar(max) NOT NULL,
  [period_time_ms] AS statsbomb.clock_ms([timestamp]) PERSISTED,
  CONSTRAINT [pk_events] PRIMARY KEY ([event_id]),
  CONSTRAINT [uq_events_0] UNIQUE ([match_id],[event_index]),
  CONSTRAINT [uq_events_1] UNIQUE ([match_id],[event_id]),
  CONSTRAINT [uq_events_2] UNIQUE ([match_id],[team_id],[event_id],[type_id]),
  CONSTRAINT [uq_events_3] UNIQUE ([match_id],[period],[event_id]),
  CONSTRAINT [ck_events_0] CHECK ([event_index] > 0),
  CONSTRAINT [ck_events_1] CHECK ([period] BETWEEN 1 AND 5),
  CONSTRAINT [ck_events_2] CHECK ([minute] >= 0),
  CONSTRAINT [ck_events_3] CHECK ([second] BETWEEN 0 AND 59),
  CONSTRAINT [ck_events_4] CHECK ([duration] >= 0 AND 1=1),
  CONSTRAINT [ck_events_5] CHECK ([player_id] IS NULL OR [team_id] IS NOT NULL),
  CONSTRAINT [ck_events_6] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_events_7] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_events_8] CHECK (ISJSON([details], OBJECT)=1),
  CONSTRAINT [ck_events_9] CHECK (ISJSON([raw_payload], OBJECT)=1),
  CONSTRAINT ck_event_clock CHECK ([period_time_ms] IS NOT NULL AND [period_time_ms]>=0)
);
GO

CREATE TABLE [statsbomb].[event_relations](
  [event_id] uniqueidentifier NOT NULL,
  [match_id] int NOT NULL,
  [related_event_id] uniqueidentifier NOT NULL,
  CONSTRAINT [pk_event_relations] PRIMARY KEY ([event_id],[related_event_id]),
  CONSTRAINT [ck_event_relations_0] CHECK ([event_id] <> [related_event_id])
);
GO

CREATE TABLE [statsbomb].[event_passes](
  [event_id] uniqueidentifier NOT NULL,
  [event_type_id] int NOT NULL DEFAULT (30),
  [team_id] int NOT NULL,
  [match_id] int NOT NULL,
  [recipient_player_id] int NULL,
  [length] float(53) NULL,
  [angle] float(53) NULL,
  [height] nvarchar(max) NULL,
  [end_x] float(53) NULL,
  [end_y] float(53) NULL,
  [body_part] nvarchar(max) NULL,
  [pass_type] nvarchar(max) NULL,
  [outcome] nvarchar(max) NULL,
  [technique] nvarchar(max) NULL,
  [shot_assist] bit NULL,
  [goal_assist] bit NULL,
  [cross] bit NULL,
  [cut_back] bit NULL,
  [switch] bit NULL,
  [backheel] bit NULL,
  [deflected] bit NULL,
  [miscommunication] bit NULL,
  [aerial_won] bit NULL,
  [through_ball] bit NULL,
  [inswinging] bit NULL,
  [outswinging] bit NULL,
  CONSTRAINT [pk_event_passes] PRIMARY KEY ([event_id]),
  CONSTRAINT [uq_event_passes_0] UNIQUE ([match_id],[team_id],[event_id]),
  CONSTRAINT [ck_event_passes_0] CHECK ([event_type_id] = 30),
  CONSTRAINT [ck_event_passes_1] CHECK ([length] >= 0 AND 1=1),
  CONSTRAINT [ck_event_passes_2] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_event_passes_3] CHECK (ISJSON([height], OBJECT)=1),
  CONSTRAINT [ck_event_passes_4] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_event_passes_5] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_event_passes_6] CHECK (ISJSON([body_part], OBJECT)=1),
  CONSTRAINT [ck_event_passes_7] CHECK (ISJSON([pass_type], OBJECT)=1),
  CONSTRAINT [ck_event_passes_8] CHECK (ISJSON([outcome], OBJECT)=1),
  CONSTRAINT [ck_event_passes_9] CHECK (ISJSON([technique], OBJECT)=1)
);
GO

CREATE TABLE [statsbomb].[event_shots](
  [event_id] uniqueidentifier NOT NULL,
  [event_type_id] int NOT NULL DEFAULT (16),
  [team_id] int NOT NULL,
  [match_id] int NOT NULL,
  [statsbomb_xg] float(53) NULL,
  [end_x] float(53) NULL,
  [end_y] float(53) NULL,
  [end_z] float(53) NULL,
  [key_pass_id] uniqueidentifier NULL,
  [shot_type] nvarchar(max) NULL,
  [outcome] nvarchar(max) NULL,
  [technique] nvarchar(max) NULL,
  [body_part] nvarchar(max) NULL,
  [aerial_won] bit NULL,
  [follows_dribble] bit NULL,
  [first_time] bit NULL,
  [open_goal] bit NULL,
  [deflected] bit NULL,
  CONSTRAINT [pk_event_shots] PRIMARY KEY ([event_id]),
  CONSTRAINT [uq_event_shots_0] UNIQUE ([match_id],[team_id],[event_id]),
  CONSTRAINT [ck_event_shots_0] CHECK ([event_type_id] = 16),
  CONSTRAINT [ck_event_shots_1] CHECK ([statsbomb_xg] BETWEEN 0 AND 1),
  CONSTRAINT [ck_event_shots_2] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_event_shots_3] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_event_shots_4] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_event_shots_5] CHECK (ISJSON([shot_type], OBJECT)=1),
  CONSTRAINT [ck_event_shots_6] CHECK (ISJSON([outcome], OBJECT)=1),
  CONSTRAINT [ck_event_shots_7] CHECK (ISJSON([technique], OBJECT)=1),
  CONSTRAINT [ck_event_shots_8] CHECK (ISJSON([body_part], OBJECT)=1)
);
GO

CREATE TABLE [statsbomb].[shot_freeze_players](
  [event_id] uniqueidentifier NOT NULL,
  [shot_team_id] int NOT NULL,
  [match_id] int NOT NULL,
  [frame_player_index] int NOT NULL,
  [player_id] int NULL,
  [position_id] int NULL,
  [position_name] nvarchar(256) NULL,
  [location_x] float(53) NULL,
  [location_y] float(53) NULL,
  [teammate] bit NULL,
  CONSTRAINT [pk_shot_freeze_players] PRIMARY KEY ([event_id],[frame_player_index]),
  CONSTRAINT [ck_shot_freeze_players_0] CHECK ([frame_player_index] >= 0),
  CONSTRAINT [ck_shot_freeze_players_1] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_shot_freeze_players_2] CHECK (1=1 AND 1=1)
);
GO

CREATE TABLE [statsbomb].[event_tactics](
  [event_id] uniqueidentifier NOT NULL,
  [event_type_id] int NOT NULL,
  [team_id] int NOT NULL,
  [match_id] int NOT NULL,
  [formation] int NULL,
  CONSTRAINT [pk_event_tactics] PRIMARY KEY ([event_id]),
  CONSTRAINT [uq_event_tactics_0] UNIQUE ([match_id],[team_id],[event_id]),
  CONSTRAINT [ck_event_tactics_0] CHECK ([event_type_id] IN (35,36))
);
GO

CREATE TABLE [statsbomb].[tactical_lineups](
  [event_id] uniqueidentifier NOT NULL,
  [team_id] int NOT NULL,
  [match_id] int NOT NULL,
  [player_id] int NOT NULL,
  [position_id] int NULL,
  [position_name] nvarchar(256) NULL,
  [jersey_number] int NULL,
  CONSTRAINT [pk_tactical_lineups] PRIMARY KEY ([event_id],[player_id])
);
GO

CREATE TABLE [statsbomb].[frames_360](
  [event_id] uniqueidentifier NOT NULL,
  [match_id] int NOT NULL,
  [visible_area] nvarchar(max) NULL,
  [raw_payload] nvarchar(max) NOT NULL,
  CONSTRAINT [pk_frames_360] PRIMARY KEY ([event_id]),
  CONSTRAINT [ck_frames_360_0] CHECK (ISJSON([visible_area], ARRAY)=1),
  CONSTRAINT [ck_frames_360_2] CHECK (ISJSON([raw_payload], OBJECT)=1)
);
GO

CREATE TABLE [statsbomb].[frame_360_players](
  [event_id] uniqueidentifier NOT NULL,
  [frame_player_index] int NOT NULL,
  [location_x] float(53) NULL,
  [location_y] float(53) NULL,
  [teammate] bit NULL,
  [actor] bit NULL,
  [keeper] bit NULL,
  CONSTRAINT [pk_frame_360_players] PRIMARY KEY ([event_id],[frame_player_index]),
  CONSTRAINT [ck_frame_360_players_0] CHECK ([frame_player_index] >= 0),
  CONSTRAINT [ck_frame_360_players_1] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_frame_360_players_2] CHECK (1=1 AND 1=1)
);
GO

CREATE TABLE [statsbomb].[tracking_runs](
  [run_id] uniqueidentifier NOT NULL,
  [match_id] int NOT NULL,
  [label] nvarchar(256) NOT NULL,
  [seed] bigint NULL,
  [generator_name] nvarchar(256) NOT NULL,
  [generator_version] nvarchar(256) NOT NULL,
  [config] nvarchar(max) NOT NULL DEFAULT ('{}'),
  [sample_rate_hz] float(53) NOT NULL,
  [pitch_length_m] float(53) NOT NULL,
  [pitch_width_m] float(53) NOT NULL,
  [is_synthetic] bit NOT NULL DEFAULT (1),
  [max_event_offset_ms] int NOT NULL DEFAULT (100),
  CONSTRAINT [pk_tracking_runs] PRIMARY KEY ([run_id]),
  CONSTRAINT [uq_tracking_runs_0] UNIQUE ([run_id],[match_id]),
  CONSTRAINT [ck_tracking_runs_0] CHECK ([sample_rate_hz] > 0 AND [sample_rate_hz] <= 1000),
  CONSTRAINT [ck_tracking_runs_1] CHECK ([pitch_length_m] > 0 AND 1=1),
  CONSTRAINT [ck_tracking_runs_2] CHECK ([pitch_width_m] > 0 AND 1=1),
  CONSTRAINT [ck_tracking_runs_3] CHECK ([max_event_offset_ms] >= 0),
  CONSTRAINT [ck_tracking_runs_4] CHECK (ISJSON([config], OBJECT)=1),
  CONSTRAINT [ck_tracking_runs_5] CHECK ([is_synthetic]=1 OR ([is_synthetic]=0 AND COALESCE(JSON_VALUE([config],'$.is_synthetic'),'')='false' AND COALESCE(JSON_VALUE([config],'$.data_kind'),'') IN ('real_anonymized','real_pseudonymized') AND COALESCE(JSON_VALUE([config],'$.provider'),'') IN ('Metrica Sports','SkillCorner')))
);
GO

CREATE TABLE [statsbomb].[tracking_periods](
  [run_id] uniqueidentifier NOT NULL,
  [period] int NOT NULL,
  [match_id] int NOT NULL,
  [duration_ms] bigint NOT NULL,
  [home_attacks_positive_x] bit NOT NULL,
  CONSTRAINT [pk_tracking_periods] PRIMARY KEY ([run_id],[period]),
  CONSTRAINT [uq_tracking_periods_0] UNIQUE ([run_id],[period],[match_id]),
  CONSTRAINT [ck_tracking_periods_0] CHECK ([period] BETWEEN 1 AND 5),
  CONSTRAINT [ck_tracking_periods_1] CHECK ([duration_ms] > 0)
);
GO

CREATE TABLE [statsbomb].[tracking_frames](
  [run_id] uniqueidentifier NOT NULL,
  [period] int NOT NULL,
  [frame_index] int NOT NULL,
  [match_id] int NOT NULL,
  [period_time_ms] bigint NOT NULL,
  [ball_in_play] bit NULL,
  CONSTRAINT [pk_tracking_frames] PRIMARY KEY ([run_id],[period],[frame_index]),
  CONSTRAINT [uq_tracking_frames_0] UNIQUE ([run_id],[period],[period_time_ms]),
  CONSTRAINT [uq_tracking_frames_1] UNIQUE ([run_id],[period],[frame_index],[match_id]),
  CONSTRAINT [ck_tracking_frames_0] CHECK ([frame_index] >= 0),
  CONSTRAINT [ck_tracking_frames_1] CHECK ([period_time_ms] >= 0)
);
GO

CREATE TABLE [statsbomb].[tracking_player_positions](
  [run_id] uniqueidentifier NOT NULL,
  [period] int NOT NULL,
  [frame_index] int NOT NULL,
  [player_id] int NOT NULL,
  [match_id] int NOT NULL,
  [team_id] int NOT NULL,
  [x_m] float(53) NULL,
  [y_m] float(53) NULL,
  [is_on_pitch] bit NOT NULL DEFAULT (1),
  [position_status] nvarchar(256) NOT NULL DEFAULT ('available'),
  [sample_method] nvarchar(256) NOT NULL DEFAULT ('generated'),
  [confidence] float(53) NULL,
  [on_pitch_slot] int NULL,
  CONSTRAINT [pk_tracking_player_positions] PRIMARY KEY ([run_id],[period],[frame_index],[player_id]),
  CONSTRAINT [ck_tracking_player_positions_0] CHECK ([position_status] IN ('available','missing')),
  CONSTRAINT [ck_tracking_player_positions_1] CHECK (([position_status]='available' AND [x_m] IS NOT NULL AND [y_m] IS NOT NULL) OR ([position_status]='missing' AND [x_m] IS NULL AND [y_m] IS NULL)),
  CONSTRAINT [ck_tracking_player_positions_2] CHECK ([sample_method] IN ('observed','generated','interpolated','extrapolated','missing')),
  CONSTRAINT [ck_tracking_player_positions_3] CHECK ((([position_status]='missing' AND [sample_method]='missing') OR ([position_status]<>'missing' AND [sample_method]<>'missing'))),
  CONSTRAINT [ck_tracking_player_positions_4] CHECK ([confidence] BETWEEN 0 AND 1),
  CONSTRAINT [ck_tracking_player_positions_5] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_tracking_player_positions_6] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_tracking_player_positions_7] CHECK (([is_on_pitch]=1 AND [on_pitch_slot] IS NOT NULL AND [on_pitch_slot] BETWEEN 1 AND 11) OR ([is_on_pitch]=0 AND [on_pitch_slot] IS NULL))
);
GO

CREATE TABLE [statsbomb].[tracking_ball_positions](
  [run_id] uniqueidentifier NOT NULL,
  [period] int NOT NULL,
  [frame_index] int NOT NULL,
  [match_id] int NOT NULL,
  [x_m] float(53) NULL,
  [y_m] float(53) NULL,
  [z_m] float(53) NULL,
  [position_status] nvarchar(256) NOT NULL DEFAULT ('available'),
  [sample_method] nvarchar(256) NOT NULL DEFAULT ('generated'),
  [confidence] float(53) NULL,
  CONSTRAINT [pk_tracking_ball_positions] PRIMARY KEY ([run_id],[period],[frame_index]),
  CONSTRAINT [ck_tracking_ball_positions_0] CHECK ([position_status] IN ('available','missing')),
  CONSTRAINT [ck_tracking_ball_positions_1] CHECK (([position_status]='available' AND [x_m] IS NOT NULL AND [y_m] IS NOT NULL) OR ([position_status]='missing' AND [x_m] IS NULL AND [y_m] IS NULL)),
  CONSTRAINT [ck_tracking_ball_positions_2] CHECK ([sample_method] IN ('observed','generated','interpolated','extrapolated','missing')),
  CONSTRAINT [ck_tracking_ball_positions_3] CHECK ((([position_status]='missing' AND [sample_method]='missing') OR ([position_status]<>'missing' AND [sample_method]<>'missing'))),
  CONSTRAINT [ck_tracking_ball_positions_4] CHECK ([confidence] BETWEEN 0 AND 1),
  CONSTRAINT [ck_tracking_ball_positions_5] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_tracking_ball_positions_6] CHECK (1=1 AND 1=1),
  CONSTRAINT [ck_tracking_ball_positions_7] CHECK ([z_m] >= 0 AND 1=1),
  CONSTRAINT [ck_tracking_ball_positions_8] CHECK ([position_status]<>'missing' OR [z_m] IS NULL)
);
GO

CREATE TABLE [statsbomb].[event_tracking_links](
  [event_id] uniqueidentifier NOT NULL,
  [run_id] uniqueidentifier NOT NULL,
  [match_id] int NOT NULL,
  [period] int NOT NULL,
  [frame_index] int NOT NULL,
  [alignment_method] nvarchar(256) NOT NULL DEFAULT ('within_tolerance'),
  CONSTRAINT [pk_event_tracking_links] PRIMARY KEY ([event_id],[run_id]),
  CONSTRAINT [ck_event_tracking_links_0] CHECK ([alignment_method] IN ('exact','within_tolerance','manual'))
);
GO

ALTER TABLE [statsbomb].[competition_seasons] ADD CONSTRAINT [fk_0_competition_seasons] FOREIGN KEY ([competition_id]) REFERENCES [statsbomb].[competitions]([competition_id]);

ALTER TABLE [statsbomb].[competition_seasons] ADD CONSTRAINT [fk_1_competition_seasons] FOREIGN KEY ([season_id]) REFERENCES [statsbomb].[seasons]([season_id]);

CREATE INDEX [ix_fk_1] ON [statsbomb].[competition_seasons]([season_id]);

ALTER TABLE [statsbomb].[teams] ADD CONSTRAINT [fk_2_teams] FOREIGN KEY ([country_id]) REFERENCES [statsbomb].[countries]([country_id]);

CREATE INDEX [ix_fk_2] ON [statsbomb].[teams]([country_id]);

ALTER TABLE [statsbomb].[players] ADD CONSTRAINT [fk_3_players] FOREIGN KEY ([country_id]) REFERENCES [statsbomb].[countries]([country_id]);

CREATE INDEX [ix_fk_3] ON [statsbomb].[players]([country_id]);

ALTER TABLE [statsbomb].[managers] ADD CONSTRAINT [fk_4_managers] FOREIGN KEY ([country_id]) REFERENCES [statsbomb].[countries]([country_id]);

CREATE INDEX [ix_fk_4] ON [statsbomb].[managers]([country_id]);

ALTER TABLE [statsbomb].[stadiums] ADD CONSTRAINT [fk_5_stadiums] FOREIGN KEY ([country_id]) REFERENCES [statsbomb].[countries]([country_id]);

CREATE INDEX [ix_fk_5] ON [statsbomb].[stadiums]([country_id]);

ALTER TABLE [statsbomb].[referees] ADD CONSTRAINT [fk_6_referees] FOREIGN KEY ([country_id]) REFERENCES [statsbomb].[countries]([country_id]);

CREATE INDEX [ix_fk_6] ON [statsbomb].[referees]([country_id]);

ALTER TABLE [statsbomb].[matches] ADD CONSTRAINT [fk_7_matches] FOREIGN KEY ([competition_id],[season_id]) REFERENCES [statsbomb].[competition_seasons]([competition_id],[season_id]);

CREATE INDEX [ix_fk_7] ON [statsbomb].[matches]([competition_id],[season_id]);

ALTER TABLE [statsbomb].[matches] ADD CONSTRAINT [fk_8_matches] FOREIGN KEY ([stadium_id]) REFERENCES [statsbomb].[stadiums]([stadium_id]);

CREATE INDEX [ix_fk_8] ON [statsbomb].[matches]([stadium_id]);

ALTER TABLE [statsbomb].[matches] ADD CONSTRAINT [fk_9_matches] FOREIGN KEY ([referee_id]) REFERENCES [statsbomb].[referees]([referee_id]);

CREATE INDEX [ix_fk_9] ON [statsbomb].[matches]([referee_id]);

ALTER TABLE [statsbomb].[match_teams] ADD CONSTRAINT [fk_10_match_teams] FOREIGN KEY ([match_id]) REFERENCES [statsbomb].[matches]([match_id]);

ALTER TABLE [statsbomb].[match_teams] ADD CONSTRAINT [fk_11_match_teams] FOREIGN KEY ([team_id]) REFERENCES [statsbomb].[teams]([team_id]);

CREATE INDEX [ix_fk_11] ON [statsbomb].[match_teams]([team_id]);

ALTER TABLE [statsbomb].[match_team_managers] ADD CONSTRAINT [fk_12_match_team_managers] FOREIGN KEY ([match_id],[team_id]) REFERENCES [statsbomb].[match_teams]([match_id],[team_id]);

ALTER TABLE [statsbomb].[match_team_managers] ADD CONSTRAINT [fk_13_match_team_managers] FOREIGN KEY ([manager_id]) REFERENCES [statsbomb].[managers]([manager_id]);

CREATE INDEX [ix_fk_13] ON [statsbomb].[match_team_managers]([manager_id]);

ALTER TABLE [statsbomb].[match_lineups] ADD CONSTRAINT [fk_14_match_lineups] FOREIGN KEY ([match_id],[team_id]) REFERENCES [statsbomb].[match_teams]([match_id],[team_id]);

ALTER TABLE [statsbomb].[match_lineups] ADD CONSTRAINT [fk_15_match_lineups] FOREIGN KEY ([player_id]) REFERENCES [statsbomb].[players]([player_id]);

CREATE INDEX [ix_fk_15] ON [statsbomb].[match_lineups]([player_id]);

ALTER TABLE [statsbomb].[lineup_cards] ADD CONSTRAINT [fk_16_lineup_cards] FOREIGN KEY ([match_id],[team_id],[player_id]) REFERENCES [statsbomb].[match_lineups]([match_id],[team_id],[player_id]);

ALTER TABLE [statsbomb].[lineup_positions] ADD CONSTRAINT [fk_17_lineup_positions] FOREIGN KEY ([match_id],[team_id],[player_id]) REFERENCES [statsbomb].[match_lineups]([match_id],[team_id],[player_id]);

ALTER TABLE [statsbomb].[events] ADD CONSTRAINT [fk_18_events] FOREIGN KEY ([match_id]) REFERENCES [statsbomb].[matches]([match_id]);

ALTER TABLE [statsbomb].[events] ADD CONSTRAINT [fk_19_events] FOREIGN KEY ([match_id],[team_id]) REFERENCES [statsbomb].[match_teams]([match_id],[team_id]);

ALTER TABLE [statsbomb].[events] ADD CONSTRAINT [fk_20_events] FOREIGN KEY ([match_id],[possession_team_id]) REFERENCES [statsbomb].[match_teams]([match_id],[team_id]);

CREATE INDEX [ix_fk_20] ON [statsbomb].[events]([match_id],[possession_team_id]);

ALTER TABLE [statsbomb].[events] ADD CONSTRAINT [fk_21_events] FOREIGN KEY ([match_id],[team_id],[player_id]) REFERENCES [statsbomb].[match_lineups]([match_id],[team_id],[player_id]);

CREATE INDEX [ix_fk_21] ON [statsbomb].[events]([match_id],[team_id],[player_id]);

ALTER TABLE [statsbomb].[event_relations] ADD CONSTRAINT [fk_22_event_relations] FOREIGN KEY ([match_id],[event_id]) REFERENCES [statsbomb].[events]([match_id],[event_id]);

CREATE INDEX [ix_fk_22] ON [statsbomb].[event_relations]([match_id],[event_id]);

ALTER TABLE [statsbomb].[event_relations] ADD CONSTRAINT [fk_23_event_relations] FOREIGN KEY ([match_id],[related_event_id]) REFERENCES [statsbomb].[events]([match_id],[event_id]);

CREATE INDEX [ix_fk_23] ON [statsbomb].[event_relations]([match_id],[related_event_id]);

ALTER TABLE [statsbomb].[event_passes] ADD CONSTRAINT [fk_24_event_passes] FOREIGN KEY ([match_id],[team_id],[event_id],[event_type_id]) REFERENCES [statsbomb].[events]([match_id],[team_id],[event_id],[type_id]);

CREATE INDEX [ix_fk_24] ON [statsbomb].[event_passes]([match_id],[team_id],[event_id],[event_type_id]);

ALTER TABLE [statsbomb].[event_shots] ADD CONSTRAINT [fk_25_event_shots] FOREIGN KEY ([match_id],[team_id],[event_id],[event_type_id]) REFERENCES [statsbomb].[events]([match_id],[team_id],[event_id],[type_id]);

CREATE INDEX [ix_fk_25] ON [statsbomb].[event_shots]([match_id],[team_id],[event_id],[event_type_id]);

ALTER TABLE [statsbomb].[event_tactics] ADD CONSTRAINT [fk_26_event_tactics] FOREIGN KEY ([match_id],[team_id],[event_id],[event_type_id]) REFERENCES [statsbomb].[events]([match_id],[team_id],[event_id],[type_id]);

CREATE INDEX [ix_fk_26] ON [statsbomb].[event_tactics]([match_id],[team_id],[event_id],[event_type_id]);

ALTER TABLE [statsbomb].[frames_360] ADD CONSTRAINT [fk_27_frames_360] FOREIGN KEY ([match_id],[event_id]) REFERENCES [statsbomb].[events]([match_id],[event_id]);

CREATE INDEX [ix_fk_27] ON [statsbomb].[frames_360]([match_id],[event_id]);

ALTER TABLE [statsbomb].[event_passes] ADD CONSTRAINT [fk_28_event_passes] FOREIGN KEY ([match_id],[team_id],[recipient_player_id]) REFERENCES [statsbomb].[match_lineups]([match_id],[team_id],[player_id]);

CREATE INDEX [ix_fk_28] ON [statsbomb].[event_passes]([match_id],[team_id],[recipient_player_id]);

ALTER TABLE [statsbomb].[event_shots] ADD CONSTRAINT [fk_29_event_shots] FOREIGN KEY ([match_id],[team_id],[key_pass_id]) REFERENCES [statsbomb].[event_passes]([match_id],[team_id],[event_id]);

CREATE INDEX [ix_fk_29] ON [statsbomb].[event_shots]([match_id],[team_id],[key_pass_id]);

ALTER TABLE [statsbomb].[shot_freeze_players] ADD CONSTRAINT [fk_30_shot_freeze_players] FOREIGN KEY ([match_id],[shot_team_id],[event_id]) REFERENCES [statsbomb].[event_shots]([match_id],[team_id],[event_id]);

CREATE INDEX [ix_fk_30] ON [statsbomb].[shot_freeze_players]([match_id],[shot_team_id],[event_id]);

ALTER TABLE [statsbomb].[shot_freeze_players] ADD CONSTRAINT [fk_31_shot_freeze_players] FOREIGN KEY ([match_id],[player_id]) REFERENCES [statsbomb].[match_lineups]([match_id],[player_id]);

CREATE INDEX [ix_fk_31] ON [statsbomb].[shot_freeze_players]([match_id],[player_id]);

ALTER TABLE [statsbomb].[tactical_lineups] ADD CONSTRAINT [fk_32_tactical_lineups] FOREIGN KEY ([match_id],[team_id],[event_id]) REFERENCES [statsbomb].[event_tactics]([match_id],[team_id],[event_id]);

CREATE INDEX [ix_fk_32] ON [statsbomb].[tactical_lineups]([match_id],[team_id],[event_id]);

ALTER TABLE [statsbomb].[tactical_lineups] ADD CONSTRAINT [fk_33_tactical_lineups] FOREIGN KEY ([match_id],[team_id],[player_id]) REFERENCES [statsbomb].[match_lineups]([match_id],[team_id],[player_id]);

CREATE INDEX [ix_fk_33] ON [statsbomb].[tactical_lineups]([match_id],[team_id],[player_id]);

ALTER TABLE [statsbomb].[frame_360_players] ADD CONSTRAINT [fk_34_frame_360_players] FOREIGN KEY ([event_id]) REFERENCES [statsbomb].[frames_360]([event_id]);

ALTER TABLE [statsbomb].[tracking_runs] ADD CONSTRAINT [fk_35_tracking_runs] FOREIGN KEY ([match_id]) REFERENCES [statsbomb].[matches]([match_id]);

CREATE INDEX [ix_fk_35] ON [statsbomb].[tracking_runs]([match_id]);

ALTER TABLE [statsbomb].[tracking_periods] ADD CONSTRAINT [fk_36_tracking_periods] FOREIGN KEY ([run_id],[match_id]) REFERENCES [statsbomb].[tracking_runs]([run_id],[match_id]);

CREATE INDEX [ix_fk_36] ON [statsbomb].[tracking_periods]([run_id],[match_id]);

ALTER TABLE [statsbomb].[tracking_frames] ADD CONSTRAINT [fk_37_tracking_frames] FOREIGN KEY ([run_id],[period],[match_id]) REFERENCES [statsbomb].[tracking_periods]([run_id],[period],[match_id]);

CREATE INDEX [ix_fk_37] ON [statsbomb].[tracking_frames]([run_id],[period],[match_id]);

ALTER TABLE [statsbomb].[tracking_player_positions] ADD CONSTRAINT [fk_38_tracking_player_positions] FOREIGN KEY ([run_id],[period],[frame_index],[match_id]) REFERENCES [statsbomb].[tracking_frames]([run_id],[period],[frame_index],[match_id]);

CREATE INDEX [ix_fk_38] ON [statsbomb].[tracking_player_positions]([run_id],[period],[frame_index],[match_id]);

ALTER TABLE [statsbomb].[tracking_player_positions] ADD CONSTRAINT [fk_39_tracking_player_positions] FOREIGN KEY ([match_id],[team_id],[player_id]) REFERENCES [statsbomb].[match_lineups]([match_id],[team_id],[player_id]);

CREATE INDEX [ix_fk_39] ON [statsbomb].[tracking_player_positions]([match_id],[team_id],[player_id]);

ALTER TABLE [statsbomb].[tracking_ball_positions] ADD CONSTRAINT [fk_40_tracking_ball_positions] FOREIGN KEY ([run_id],[period],[frame_index],[match_id]) REFERENCES [statsbomb].[tracking_frames]([run_id],[period],[frame_index],[match_id]);

CREATE INDEX [ix_fk_40] ON [statsbomb].[tracking_ball_positions]([run_id],[period],[frame_index],[match_id]);

ALTER TABLE [statsbomb].[event_tracking_links] ADD CONSTRAINT [fk_41_event_tracking_links] FOREIGN KEY ([match_id],[period],[event_id]) REFERENCES [statsbomb].[events]([match_id],[period],[event_id]);

CREATE INDEX [ix_fk_41] ON [statsbomb].[event_tracking_links]([match_id],[period],[event_id]);

ALTER TABLE [statsbomb].[event_tracking_links] ADD CONSTRAINT [fk_42_event_tracking_links] FOREIGN KEY ([run_id],[period],[frame_index],[match_id]) REFERENCES [statsbomb].[tracking_frames]([run_id],[period],[frame_index],[match_id]);

CREATE INDEX [ix_fk_42] ON [statsbomb].[event_tracking_links]([run_id],[period],[frame_index],[match_id]);

CREATE UNIQUE INDEX uq_active_slot ON statsbomb.tracking_player_positions(run_id,period,frame_index,team_id,on_pitch_slot) WHERE on_pitch_slot IS NOT NULL;

CREATE INDEX ix_events_match_clock ON statsbomb.events(match_id,period,period_time_ms) INCLUDE(type_id,team_id,player_id,location_x,location_y);

CREATE INDEX ix_positions_player ON statsbomb.tracking_player_positions(match_id,player_id,period,frame_index) INCLUDE(x_m,y_m,position_status);

GO

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
   AND JSON_VALUE(raw_payload,'$.generator')='inside-game-demo' AND JSON_VALUE(raw_payload,'$.version') IN('2.0.0','3.0.0'))
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
 IF EXISTS(SELECT 1 FROM statsbomb.matches WHERE match_id=@match_id AND JSON_VALUE(raw_payload,'$.generator')='inside-game-demo' AND JSON_VALUE(raw_payload,'$.version')='3.0.0')
 BEGIN
  IF EXISTS(SELECT v.id FROM (VALUES(2),(3),(4),(6),(9),(10),(14),(16),(17),(19),(21),(22),(23),(30),(33),(35),(36),(38),(39),(42),(43)) v(id)
    WHERE NOT EXISTS(SELECT 1 FROM statsbomb.events e WHERE e.match_id=@match_id AND e.type_id=v.id))
    THROW 51027,'Synthetic analytic coverage is incomplete: required event family missing.',1;
  IF (SELECT COUNT(*) FROM statsbomb.events WHERE match_id=@match_id AND type_id=19)<>6
    THROW 51028,'Synthetic scenario requires three substitutions per team.',1;
  IF EXISTS(SELECT 1 FROM statsbomb.events e JOIN statsbomb.event_tracking_links l ON l.event_id=e.event_id
    LEFT JOIN statsbomb.tracking_player_positions p ON p.run_id=l.run_id AND p.period=l.period AND p.frame_index=l.frame_index AND p.player_id=e.player_id
    WHERE e.match_id=@match_id AND e.player_id IS NOT NULL AND (p.player_id IS NULL OR p.is_on_pitch=0))
    THROW 51029,'Synthetic event actor must be active at its linked tracking frame.',1;
 END;
END;
GO
IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE name='ck_shot_height_nonnegative' AND parent_object_id=OBJECT_ID('statsbomb.event_shots'))
 ALTER TABLE statsbomb.event_shots WITH CHECK ADD CONSTRAINT ck_shot_height_nonnegative CHECK(end_z>=0);
GO



CREATE PROCEDURE statsbomb.validate_match @match_id int AS
BEGIN
 SET NOCOUNT ON;
 IF (SELECT COUNT(*) FROM statsbomb.match_teams WHERE match_id=@match_id)<>2
   OR NOT EXISTS(SELECT 1 FROM statsbomb.match_teams WHERE match_id=@match_id AND side='home')
   OR NOT EXISTS(SELECT 1 FROM statsbomb.match_teams WHERE match_id=@match_id AND side='away')
   THROW 51001,'A match needs exactly one home and one away team.',1;
 IF EXISTS(SELECT 1 FROM statsbomb.events e WHERE match_id=@match_id AND
   ((type_id=30 AND NOT EXISTS(SELECT 1 FROM statsbomb.event_passes d WHERE d.event_id=e.event_id))
   OR (type_id=16 AND NOT EXISTS(SELECT 1 FROM statsbomb.event_shots d WHERE d.event_id=e.event_id))
   OR (type_id IN (35,36) AND NOT EXISTS(SELECT 1 FROM statsbomb.event_tactics d WHERE d.event_id=e.event_id))))
   THROW 51002,'An event is missing its required detail row.',1;
 IF EXISTS(SELECT 1 FROM statsbomb.tracking_frames f JOIN statsbomb.tracking_periods p
   ON p.run_id=f.run_id AND p.period=f.period WHERE f.match_id=@match_id AND f.period_time_ms>p.duration_ms)
   THROW 51003,'A tracking frame lies outside its period.',1;
 IF EXISTS(SELECT 1 FROM statsbomb.event_tracking_links l
   JOIN statsbomb.events e ON e.event_id=l.event_id
   JOIN statsbomb.tracking_frames f ON f.run_id=l.run_id AND f.period=l.period AND f.frame_index=l.frame_index
   JOIN statsbomb.tracking_runs r ON r.run_id=l.run_id
   JOIN statsbomb.tracking_periods p ON p.run_id=l.run_id AND p.period=l.period
   WHERE l.match_id=@match_id AND (e.period_time_ms>p.duration_ms
     OR ABS(e.period_time_ms-f.period_time_ms)>r.max_event_offset_ms
     OR (l.alignment_method='exact' AND e.period_time_ms<>f.period_time_ms)))
   THROW 51004,'Event and tracking clocks are not aligned.',1;
 EXEC statsbomb.validate_semantics @match_id;
END;
GO
CREATE TRIGGER statsbomb.seal_match ON statsbomb.matches AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM deleted WHERE data_status='ready')
   THROW 51005,'Published matches are immutable. Import a new version.',1;
 DECLARE @id int;
 DECLARE ready_matches CURSOR LOCAL FAST_FORWARD FOR SELECT match_id FROM inserted WHERE data_status='ready';
 OPEN ready_matches;
 FETCH NEXT FROM ready_matches INTO @id;
 WHILE @@FETCH_STATUS=0
 BEGIN
   EXEC statsbomb.validate_match @id;
   FETCH NEXT FROM ready_matches INTO @id;
 END;
 CLOSE ready_matches; DEALLOCATE ready_matches;
END;
GO
CREATE PROCEDURE statsbomb.publish_match @match_id int AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 BEGIN TRY
   BEGIN TRANSACTION;
   DECLARE @state nvarchar(16);
   SELECT @state=data_status FROM statsbomb.matches WITH (UPDLOCK,HOLDLOCK) WHERE match_id=@match_id;
   IF @state IS NULL THROW 51006,'Unknown match.',1;
   IF @state<>'loading' THROW 51007,'Match already published.',1;
   UPDATE statsbomb.matches SET data_status='ready' WHERE match_id=@match_id;
   COMMIT;
 END TRY
 BEGIN CATCH
   IF XACT_STATE()<>0 ROLLBACK;
   THROW;
 END CATCH;
END;
GO


CREATE TRIGGER statsbomb.[seal_match_teams] ON [statsbomb].[match_teams] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_match_team_managers] ON [statsbomb].[match_team_managers] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_match_lineups] ON [statsbomb].[match_lineups] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_lineup_cards] ON [statsbomb].[lineup_cards] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_lineup_positions] ON [statsbomb].[lineup_positions] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_events] ON [statsbomb].[events] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_event_relations] ON [statsbomb].[event_relations] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_event_passes] ON [statsbomb].[event_passes] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_event_shots] ON [statsbomb].[event_shots] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_shot_freeze_players] ON [statsbomb].[shot_freeze_players] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_event_tactics] ON [statsbomb].[event_tactics] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_tactical_lineups] ON [statsbomb].[tactical_lineups] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_frames_360] ON [statsbomb].[frames_360] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_frame_360_players] ON [statsbomb].[frame_360_players] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT f.match_id FROM statsbomb.frames_360 f JOIN (SELECT event_id FROM inserted UNION SELECT event_id FROM deleted) x ON x.event_id=f.event_id) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_tracking_runs] ON [statsbomb].[tracking_runs] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_tracking_periods] ON [statsbomb].[tracking_periods] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_tracking_frames] ON [statsbomb].[tracking_frames] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_tracking_player_positions] ON [statsbomb].[tracking_player_positions] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_tracking_ball_positions] ON [statsbomb].[tracking_ball_positions] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[seal_event_tracking_links] ON [statsbomb].[event_tracking_links] AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN (SELECT match_id FROM inserted UNION SELECT match_id FROM deleted) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO

CREATE TRIGGER statsbomb.[version_tracking_runs] ON [statsbomb].[tracking_runs] AFTER UPDATE AS
BEGIN
 IF EXISTS(SELECT 1 FROM inserted) THROW 51009,'Create a new run instead of editing tracking metadata.',1;
END;
GO

CREATE TRIGGER statsbomb.[version_tracking_periods] ON [statsbomb].[tracking_periods] AFTER UPDATE AS
BEGIN
 IF EXISTS(SELECT 1 FROM inserted) THROW 51009,'Create a new run instead of editing tracking metadata.',1;
END;
GO


CREATE TRIGGER statsbomb.valid_visible_area ON statsbomb.frames_360 AFTER INSERT,UPDATE AS
BEGIN
 IF EXISTS(SELECT 1 FROM inserted i WHERE i.visible_area IS NOT NULL AND
   ((SELECT COUNT(*) FROM OPENJSON(i.visible_area)) % 2 <> 0
    OR EXISTS(SELECT 1 FROM OPENJSON(i.visible_area) WHERE type<>2)))
   THROW 51010,'visible_area must contain numeric coordinate pairs.',1;
END;
GO


CREATE VIEW analytics.[countries] AS SELECT * FROM [statsbomb].[countries];
GO

CREATE VIEW analytics.[competitions] AS SELECT * FROM [statsbomb].[competitions];
GO

CREATE VIEW analytics.[seasons] AS SELECT * FROM [statsbomb].[seasons];
GO

CREATE VIEW analytics.[competition_seasons] AS SELECT * FROM [statsbomb].[competition_seasons];
GO

CREATE VIEW analytics.[teams] AS SELECT * FROM [statsbomb].[teams];
GO

CREATE VIEW analytics.[players] AS SELECT * FROM [statsbomb].[players];
GO

CREATE VIEW analytics.[managers] AS SELECT * FROM [statsbomb].[managers];
GO

CREATE VIEW analytics.[stadiums] AS SELECT * FROM [statsbomb].[stadiums];
GO

CREATE VIEW analytics.[referees] AS SELECT * FROM [statsbomb].[referees];
GO

CREATE VIEW analytics.[matches] AS SELECT * FROM statsbomb.matches WHERE data_status='ready';
GO

CREATE VIEW analytics.[match_teams] AS SELECT d.* FROM [statsbomb].[match_teams] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[match_team_managers] AS SELECT d.* FROM [statsbomb].[match_team_managers] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[match_lineups] AS SELECT d.* FROM [statsbomb].[match_lineups] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[lineup_cards] AS SELECT d.* FROM [statsbomb].[lineup_cards] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[lineup_positions] AS SELECT d.* FROM [statsbomb].[lineup_positions] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[events] AS SELECT d.* FROM [statsbomb].[events] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[event_relations] AS SELECT d.* FROM [statsbomb].[event_relations] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[event_passes] AS SELECT d.* FROM [statsbomb].[event_passes] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[event_shots] AS SELECT d.* FROM [statsbomb].[event_shots] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[shot_freeze_players] AS SELECT d.* FROM [statsbomb].[shot_freeze_players] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[event_tactics] AS SELECT d.* FROM [statsbomb].[event_tactics] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[tactical_lineups] AS SELECT d.* FROM [statsbomb].[tactical_lineups] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[frames_360] AS SELECT d.* FROM [statsbomb].[frames_360] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[frame_360_players] AS SELECT d.* FROM statsbomb.frame_360_players d JOIN analytics.frames_360 f ON f.event_id=d.event_id;
GO

CREATE VIEW analytics.[tracking_runs] AS SELECT d.* FROM [statsbomb].[tracking_runs] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[tracking_periods] AS SELECT d.* FROM [statsbomb].[tracking_periods] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[tracking_frames] AS SELECT d.* FROM [statsbomb].[tracking_frames] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[tracking_player_positions] AS SELECT d.* FROM [statsbomb].[tracking_player_positions] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[tracking_ball_positions] AS SELECT d.* FROM [statsbomb].[tracking_ball_positions] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO

CREATE VIEW analytics.[event_tracking_links] AS SELECT d.* FROM [statsbomb].[event_tracking_links] d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready';
GO


CREATE VIEW analytics.shots AS
 SELECT e.match_id,e.event_id,e.period,e.period_time_ms,e.minute,e.second,e.team_id,e.player_id,
 e.location_x,e.location_y,s.statsbomb_xg AS xg,TRY_CONVERT(int,JSON_VALUE(s.outcome,'$.id')) AS outcome_id,
 JSON_VALUE(s.outcome,'$.name') AS outcome_name,
 CONVERT(bit,CASE WHEN TRY_CONVERT(int,JSON_VALUE(s.outcome,'$.id')) IN (97,100,116) THEN 1 ELSE 0 END) AS is_on_target,
 CONVERT(bit,CASE WHEN JSON_VALUE(m.raw_payload,'$.is_synthetic')='true' THEN 1 ELSE 0 END) AS is_synthetic
 FROM analytics.events e JOIN analytics.event_shots s ON s.event_id=e.event_id
 JOIN analytics.matches m ON m.match_id=e.match_id;
GO
CREATE ROLE football_reader;
GRANT SELECT ON SCHEMA::analytics TO football_reader;
GO
