-- Run once as administrator. No-login context used by the local API; no data changes.
IF DATABASE_PRINCIPAL_ID('inside_game_api_reader') IS NULL
 CREATE USER inside_game_api_reader WITHOUT LOGIN;
IF IS_ROLEMEMBER('football_reader','inside_game_api_reader')<>1
 ALTER ROLE football_reader ADD MEMBER inside_game_api_reader;
DENY EXECUTE ON SCHEMA::statsbomb TO inside_game_api_reader;
