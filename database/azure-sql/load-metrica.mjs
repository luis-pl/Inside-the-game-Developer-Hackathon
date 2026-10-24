import assert from 'node:assert/strict';
import { createReadStream, readFileSync, writeFileSync } from 'node:fs';
import { createGunzip } from 'node:zlib';
import { createInterface } from 'node:readline';
import { connect, sql, bulk, safeError } from './connection.mjs';

const source=JSON.parse(readFileSync(new URL('./metrica-source.json',import.meta.url)));
const order=['teams','players','matches','match_teams','match_lineups','lineup_cards','lineup_positions',
 'events','event_passes','event_shots','tracking_runs','tracking_periods','tracking_frames',
 'tracking_player_positions','tracking_ball_positions','event_tracking_links'];
const pool=await connect();
const report={source:source.repository,source_revision:source.revision,is_synthetic:false,testedAt:new Date().toISOString(),status:'running',matches:[]};
try {
 // The migration is additive to permitted provenance; no match is replaced.
 await pool.request().batch(readFileSync(new URL('./real-data-migration.sql',import.meta.url),'utf8'));
 for(const game of [1,2]) {
  const folder=new URL(`../../.cache/metrica/prepared-${game}/`,import.meta.url);
  const manifest=JSON.parse(readFileSync(new URL('manifest.json',folder)));
  const existing=await pool.request().input('id',sql.Int,manifest.match_id).query('SELECT data_status,JSON_VALUE(raw_payload,\'$.source_revision\') source_revision FROM statsbomb.matches WHERE match_id=@id');
  if(existing.recordset.length){
   assert.equal(existing.recordset[0].source_revision,source.revision,'An unrelated match already uses this ID');
   assert.equal(existing.recordset[0].data_status,'ready','An incomplete import requires investigation');
   report.matches.push({match:manifest.match_id,status:'already-published'});continue;
  }
  const tx=pool.transaction();await tx.begin();
  try {
   await tx.request().query(`IF NOT EXISTS(SELECT 1 FROM statsbomb.competitions WHERE competition_id=901)
    INSERT statsbomb.competitions(competition_id,competition_name) VALUES(901,'Metrica anonymized samples (competition undisclosed)');
    IF NOT EXISTS(SELECT 1 FROM statsbomb.seasons WHERE season_id=1900)
    INSERT statsbomb.seasons(season_id,season_name) VALUES(1900,'Undisclosed; 1900 is an import placeholder');
    IF NOT EXISTS(SELECT 1 FROM statsbomb.competition_seasons WHERE competition_id=901 AND season_id=1900)
    INSERT statsbomb.competition_seasons(competition_id,season_id,raw_payload) VALUES(901,1900,'{"is_synthetic":false,"data_kind":"real_anonymized","provider":"Metrica Sports"}');`);
   for(const name of order){
    if(!manifest.counts[name])continue;
    const lines=createInterface({input:createReadStream(new URL(`${name}.jsonl.gz`,folder)).pipe(createGunzip()),crlfDelay:Infinity});
    let rows=[],count=0;
    for await(const line of lines){
     rows.push(JSON.parse(line));count++;
     if(rows.length===10000){await bulk(tx,name,rows);rows=[];}
    }
    if(rows.length)await bulk(tx,name,rows);
    assert.equal(count,manifest.counts[name]);
    console.log(JSON.stringify({match:manifest.match_id,table:name,rows:count}));
   }
   await tx.request().input('id',sql.Int,manifest.match_id).query('EXEC statsbomb.publish_match @match_id=@id');
   await tx.commit();report.matches.push({match:manifest.match_id,status:'published',counts:manifest.counts});
  }catch(e){try{await tx.rollback();}catch{}throw e;}
 }
 report.status='passed';
}catch(e){report.status='failed';report.error=safeError(e);process.exitCode=1;console.error(JSON.stringify(report.error));}
finally{writeFileSync(new URL('./metrica-load-report.json',import.meta.url),JSON.stringify(report,null,2)+'\n');await pool.close();}
