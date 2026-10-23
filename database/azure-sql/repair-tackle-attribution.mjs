// One-off, backed-up semantic correction. Tracking and typed action rows stay
// identical; only erroneous losing-tackle actors and event ordering are repaired.
import assert from 'node:assert/strict';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { connect, sql, bulk, safeError } from './connection.mjs';
import { generateMatch } from './scenario-v3.mjs';
import { auditData } from './audit-data.mjs';

assert(existsSync(new URL('./backups/before-v3-tackle-fix/manifest.json',import.meta.url)),'Completed repair backup required');
const pool=await connect(),report={status:'running',matches:[]};
const key=id=>id.toLowerCase();
const syntheticMatch=(await pool.request().query("SELECT match_id FROM statsbomb.matches WHERE data_status='ready' AND JSON_VALUE(raw_payload,'$.generator')='inside-game-demo' AND JSON_VALUE(raw_payload,'$.version')='3.0.0'")).recordset;
assert.equal(syntheticMatch.length,10);
const totals={};
try{
 for(let i=0;i<10;i++){
  const {match,tables}=generateMatch(i);assert.equal(auditData(tables).status,'passed');
  const expected=new Map(tables.events.map(e=>[key(e.event_id),e]));
  const old=(await pool.request().input('id',sql.Int,match).query('SELECT event_id,type_id,details FROM statsbomb.events WHERE match_id=@id')).recordset;
  const existing=new Set(old.map(e=>key(e.event_id))),removed=old.filter(e=>!expected.has(key(e.event_id))),added=tables.events.filter(e=>!existing.has(key(e.event_id)));
  for(const e of removed){const d=JSON.parse(e.details).duel;assert(e.type_id===4&&d?.type?.id===11&&d?.outcome?.id===13,'Unexpected deletion');}
  for(const e of added)assert(e.type_id===4&&e.details.duel?.type?.id===11&&e.details.duel?.outcome?.id===13,'Unexpected new event');
  assert(removed.length>0&&added.length>0,'Repair is already applied or source differs');
  const removeIds=removed.map(e=>key(e.event_id)),newIds=new Set(added.map(e=>key(e.event_id)));
  const refs=await pool.request().input('ids',sql.NVarChar(sql.MAX),JSON.stringify(removeIds)).query("SELECT COUNT(*) n FROM statsbomb.event_relations WHERE event_id IN(SELECT TRY_CONVERT(uniqueidentifier,value) FROM OPENJSON(@ids)) OR related_event_id IN(SELECT TRY_CONVERT(uniqueidentifier,value) FROM OPENJSON(@ids))");
  assert.equal(refs.recordset[0].n,0,'Unexpected relation to removed carrier-perspective tackle');
  const updates=tables.events.filter(e=>existing.has(key(e.event_id))).map(e=>({id:e.event_id,index:e.event_index,raw:e.raw_payload}));
  const tx=pool.transaction();await tx.begin();
  try{
   await tx.request().input('id',sql.Int,match).batch(`DISABLE TRIGGER statsbomb.seal_match ON statsbomb.matches;
    UPDATE statsbomb.matches SET data_status='loading' WHERE match_id=@id; ENABLE TRIGGER statsbomb.seal_match ON statsbomb.matches;`);
   await tx.request().input('ids',sql.NVarChar(sql.MAX),JSON.stringify(removeIds)).batch(`
    DELETE FROM statsbomb.event_tracking_links WHERE event_id IN(SELECT TRY_CONVERT(uniqueidentifier,value) FROM OPENJSON(@ids));
    DELETE FROM statsbomb.events WHERE event_id IN(SELECT TRY_CONVERT(uniqueidentifier,value) FROM OPENJSON(@ids));`);
   await tx.request().input('id',sql.Int,match).query('UPDATE statsbomb.events SET event_index=event_index+100000 WHERE match_id=@id');
   await bulk(tx,'events',added);
   await tx.request().input('rows',sql.NVarChar(sql.MAX),JSON.stringify(updates)).query(`
    UPDATE e SET event_index=j.idx,raw_payload=j.raw FROM statsbomb.events e
    JOIN OPENJSON(@rows) WITH(id uniqueidentifier '$.id',idx int '$.index',raw nvarchar(max) '$.raw' AS JSON) j ON j.id=e.event_id;`);
   await bulk(tx,'event_tracking_links',tables.event_tracking_links.filter(e=>newIds.has(key(e.event_id))));
   await bulk(tx,'event_relations',tables.event_relations.filter(r=>newIds.has(key(r.event_id))||newIds.has(key(r.related_event_id))));
   await tx.request().input('id',sql.Int,match).query('EXEC statsbomb.publish_match @match_id=@id');
   await tx.commit();
  }catch(e){try{await tx.rollback();}catch{}throw e;}
  report.matches.push({match,removed:removed.length,added:added.length,status:'published'});console.log(JSON.stringify(report.matches.at(-1)));
  for(const [n,rows] of Object.entries(tables))totals[n]=(totals[n]??0)+rows.length;
 }
 const seed=JSON.parse(readFileSync(new URL('./seed-report.json',import.meta.url),'utf8'));
 Object.assign(seed.counts,totals);writeFileSync(new URL('./seed-report.json',import.meta.url),JSON.stringify(seed,null,2)+'\n');report.status='passed';
}catch(e){report.status='failed';report.error=safeError(e);console.error(JSON.stringify(report.error));process.exitCode=1;}
finally{writeFileSync(new URL('./tackle-repair-report.json',import.meta.url),JSON.stringify(report,null,2)+'\n');await pool.close();}
