import assert from 'node:assert/strict';
import { createReadStream, readFileSync, writeFileSync } from 'node:fs';
import { createGunzip } from 'node:zlib';
import { createInterface } from 'node:readline';
import { connect, sql, bulk, safeError } from './connection.mjs';
const source=JSON.parse(readFileSync(new URL('./skillcorner-source.json',import.meta.url)));
const order=['teams','players','matches','match_teams','match_lineups','lineup_positions','events','event_passes','event_shots',
 'tracking_runs','tracking_periods','tracking_frames','tracking_player_positions','tracking_ball_positions','event_tracking_links'];
const pool=await connect();
const report={provider:'SkillCorner',source:source.repository,source_revision:source.revision,is_synthetic:false,testedAt:new Date().toISOString(),status:'running',matches:[]};
try{
 await pool.request().batch(`SET XACT_ABORT ON;BEGIN TRANSACTION;
  ALTER TABLE statsbomb.tracking_runs DROP CONSTRAINT ck_tracking_runs_5;
  ALTER TABLE statsbomb.tracking_runs WITH CHECK ADD CONSTRAINT ck_tracking_runs_5 CHECK (is_synthetic=1 OR
   (is_synthetic=0 AND COALESCE(JSON_VALUE(config,'$.is_synthetic'),'')='false'
    AND COALESCE(JSON_VALUE(config,'$.data_kind'),'') IN ('real_anonymized','real_pseudonymized')
    AND COALESCE(JSON_VALUE(config,'$.provider'),'') IN ('Metrica Sports','SkillCorner')));COMMIT;`);
 for(let game=1;game<=8;game++){
  const folder=new URL(`../../.cache/skillcorner/prepared-${game}/`,import.meta.url);
  const manifest=JSON.parse(readFileSync(new URL('manifest.json',folder)));
  const existing=await pool.request().input('id',sql.Int,manifest.match_id).query("SELECT data_status,JSON_VALUE(raw_payload,'$.source_revision') source_revision FROM statsbomb.matches WHERE match_id=@id");
  if(existing.recordset.length){assert.equal(existing.recordset[0].source_revision,source.revision);assert.equal(existing.recordset[0].data_status,'ready');report.matches.push({match:manifest.match_id,status:'already-published'});continue;}
  const tx=pool.transaction();await tx.begin();
  try{
   await tx.request().query(`IF NOT EXISTS(SELECT 1 FROM statsbomb.competitions WHERE competition_id=902)
    INSERT statsbomb.competitions(competition_id,competition_name) VALUES(902,'SkillCorner Open Data (pseudonymized teams)');
    IF NOT EXISTS(SELECT 1 FROM statsbomb.seasons WHERE season_id=2025)
    INSERT statsbomb.seasons(season_id,season_name) VALUES(2025,'2024/2025');
    IF NOT EXISTS(SELECT 1 FROM statsbomb.competition_seasons WHERE competition_id=902 AND season_id=2025)
    INSERT statsbomb.competition_seasons(competition_id,season_id,raw_payload) VALUES(902,2025,'{"is_synthetic":false,"data_kind":"real_pseudonymized","provider":"SkillCorner"}');`);
   for(const name of order){
    if(!manifest.counts[name])continue;
    const lines=createInterface({input:createReadStream(new URL(`${name}.jsonl.gz`,folder)).pipe(createGunzip()),crlfDelay:Infinity});
    let rows=[],count=0;
    for await(const line of lines){rows.push(JSON.parse(line));count++;if(rows.length===10000){await bulk(tx,name,rows);rows=[];}}
    if(rows.length)await bulk(tx,name,rows);
    assert.equal(count,manifest.counts[name]);console.log(JSON.stringify({match:manifest.match_id,table:name,rows:count}));
   }
   await tx.request().input('id',sql.Int,manifest.match_id).query('EXEC statsbomb.publish_match @match_id=@id');
   await tx.commit();report.matches.push({match:manifest.match_id,status:'published',counts:manifest.counts});
   writeFileSync(new URL('./skillcorner-load-report.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
  }catch(e){try{await tx.rollback();}catch{}throw e;}
 }
 report.status='passed';
}catch(e){report.status='failed';report.error=safeError(e);process.exitCode=1;console.error(JSON.stringify(report.error));}
finally{writeFileSync(new URL('./skillcorner-load-report.json',import.meta.url),JSON.stringify(report,null,2)+'\n');await pool.close();}
