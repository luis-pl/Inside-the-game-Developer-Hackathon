SELECT m.match_id,m.match_date,m.kick_off,m.home_score,m.away_score,m.competition_id,m.season_id,
 c.competition_name,s.season_name,JSON_VALUE(m.raw_payload,'$.version') generator_version,
 CONVERT(bit,CASE WHEN JSON_VALUE(m.raw_payload,'$.is_synthetic')='true' THEN 1 ELSE 0 END) is_synthetic,
 JSON_VALUE(m.raw_payload,'$.data_kind') data_kind,JSON_VALUE(m.raw_payload,'$.provider') provider,
 CONVERT(bit,CASE WHEN JSON_VALUE(m.raw_payload,'$.date_unknown')='true' THEN 0 ELSE 1 END) match_date_known,
 home.team_id home_team_id,ht.team_name home_team_name,away.team_id away_team_id,at.team_name away_team_name
FROM analytics.matches m JOIN analytics.competitions c ON c.competition_id=m.competition_id
JOIN analytics.seasons s ON s.season_id=m.season_id
JOIN analytics.match_teams home ON home.match_id=m.match_id AND home.side='home'
JOIN analytics.match_teams away ON away.match_id=m.match_id AND away.side='away'
JOIN analytics.teams ht ON ht.team_id=home.team_id JOIN analytics.teams at ON at.team_id=away.team_id
ORDER BY m.match_id;
SELECT team_id,team_name FROM analytics.teams ORDER BY team_id;
SELECT player_id,player_name,player_nickname FROM analytics.players ORDER BY player_id;
