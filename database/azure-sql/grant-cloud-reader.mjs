// Asigna sólo lectura de analytics a la identidad del contenedor. No toca partidos.
import { readFileSync } from 'node:fs';
import { connect, sql, safeError } from './connection.mjs';

const state = JSON.parse(readFileSync(new URL('../../deployment/cloud.json', import.meta.url), 'utf8'));
let pool;
try {
  pool = await connect();
  const result = await pool.request().input('clientId', sql.UniqueIdentifier, state.identity_client_id).query(`
    DECLARE @sid VARBINARY(16)=CONVERT(VARBINARY(16),@clientId);
    IF DATABASE_PRINCIPAL_ID('inside_game_cloud_reader') IS NULL
    BEGIN
      DECLARE @statement NVARCHAR(MAX)=N'CREATE USER [inside_game_cloud_reader] WITH SID='+CONVERT(VARCHAR(MAX),@sid,1)+', TYPE=E;';
      EXEC(@statement);
    END;
    IF NOT EXISTS(SELECT 1 FROM sys.database_principals WHERE name='inside_game_cloud_reader' AND sid=@sid AND type='E')
      THROW 51099,'Cloud reader SID differs from the configured managed identity.',1;
    IF IS_ROLEMEMBER('football_reader','inside_game_cloud_reader')<>1
      ALTER ROLE football_reader ADD MEMBER inside_game_cloud_reader;
    DENY EXECUTE ON SCHEMA::statsbomb TO inside_game_cloud_reader;
    EXECUTE AS USER='inside_game_cloud_reader';
    SELECT USER_NAME() AS principal,IS_ROLEMEMBER('football_reader') AS reader,
      HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS admin,
      HAS_PERMS_BY_NAME('statsbomb.matches','OBJECT','UPDATE') AS can_update;
    REVERT;
  `);
  console.log(JSON.stringify(result.recordset));
  if (result.recordset[0].reader !== 1 || result.recordset[0].admin === 1 || result.recordset[0].can_update === 1) throw new Error('Unsafe cloud reader permissions');
} catch (e) {
  console.error(JSON.stringify(safeError(e)));
  process.exitCode = 1;
} finally {
  if (pool) await pool.close();
}
