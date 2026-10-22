import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { connect, sql, safeError } from './connection.mjs';
import { auditData } from './audit-data.mjs';
const names=['matches','match_teams','events','event_passes','event_shots','lineup_cards','shot_freeze_players','frames_360','frame_360_players','tracking_frames','tracking_player_positions','tracking_ball_positions'];
const jsonFields=['raw_payload','details','outcome','pass_type','config','visible_area'];
const pool=await connect(),report={testedAt:new Date().toISOString(),status:'running',source:'Actual rows read back from Azure SQL',reports:[]};
try{
 for(let id=900001;id<=900010;id++){
  const tables={};
  for(const name of names){
   const clause=name==='frame_360_players'?'event_id IN(SELECT event_id FROM statsbomb.events WHERE match_id=@id)':'match_id=@id';
   // Explicit order is necessary for finite-difference speed checks.
   const order=name==='tracking_player_positions'?' ORDER BY period,frame_index,player_id':name==='events'?' ORDER BY event_index':'';
   const result=await pool.request().input('id',sql.Int,id).query(`SELECT * FROM statsbomb.[${name}] WHERE ${clause}${order}`);
   tables[name]=result.recordset;
   for(const r of tables[name])for(const key of jsonFields)if(typeof r[key]==='string')r[key]=JSON.parse(r[key]);
  }
  assert.equal(tables.matches[0].raw_payload.version,'2.0.0','Cloud still has an older generator version');
  await pool.request().input('id',sql.Int,id).query('EXEC statsbomb.validate_match @match_id=@id');
  const r=auditData(tables);report.reports.push(r);console.log(JSON.stringify({match:id,status:r.status,errors:r.errors,metrics:r.metrics}));
  assert.equal(r.status,'passed');
 }
 const fixture=await pool.request().query("SELECT COUNT(*) n FROM statsbomb.matches WHERE match_id=999991; SELECT COUNT(*) n FROM sys.triggers WHERE parent_class=1 AND is_disabled=1 AND OBJECT_SCHEMA_NAME(object_id)='statsbomb'");
 assert.equal(fixture.recordsets[0][0].n,0,'Test fixture leaked');assert.equal(fixture.recordsets[1][0].n,0,'All integrity triggers must be enabled');
 report.status='passed';
}catch(e){report.status='failed';report.error=safeError(e);console.error(JSON.stringify(report.error));process.exitCode=1;}
finally{writeFileSync(new URL('./realism-cloud-report.json',import.meta.url),JSON.stringify(report,null,2)+'\n');await pool.close();}
