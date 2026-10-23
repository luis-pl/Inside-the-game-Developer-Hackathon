import {readFileSync} from 'node:fs';
import {connect} from './connection.mjs';
const pool=await connect();
try {
 await pool.request().batch(readFileSync(new URL('./api-reader.sql',import.meta.url),'utf8'));
 const result=await pool.request().query("EXECUTE AS USER='inside_game_api_reader'; SELECT USER_NAME() principal,IS_ROLEMEMBER('football_reader') reader,HAS_PERMS_BY_NAME('statsbomb.matches','OBJECT','UPDATE') can_update; REVERT;");
 console.log(JSON.stringify(result.recordset));
} finally {await pool.close();}
