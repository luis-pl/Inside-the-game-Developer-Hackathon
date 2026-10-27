import assert from 'node:assert/strict';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { connect, sql, bulk, model, safeError } from './connection.mjs';
import { generateMatch, SEED, VERSION, MATCH_COUNT, payload } from './scenario-v3.mjs';
import { auditData } from './audit-data.mjs';
// Alias ficticios por team_id; misma fuente que rename-teams.sql.
const TEAM_NAMES=Object.fromEntries(JSON.parse(readFileSync(new URL('./team-names.json',import.meta.url),'utf8')).teams.map(t=>[t.team_id,t.team_name]));
export const order=['matches','match_teams','match_team_managers','match_lineups','lineup_cards','lineup_positions','events','event_relations',
 'event_passes','event_shots','shot_freeze_players','event_tactics','tactical_lineups','frames_360','frame_360_players',
 'tracking_runs','tracking_periods','tracking_frames','tracking_player_positions','tracking_ball_positions','event_tracking_links'];

export async function seed({replace=false}={}){
 const pool=await connect(),counts={};
 try{
  const existing=await pool.request().query("SELECT match_id,JSON_VALUE(raw_payload,'$.generator') generator,JSON_VALUE(raw_payload,'$.is_synthetic') synthetic FROM statsbomb.matches");
  if(replace){
   assert(existsSync(new URL('./backups/before-v3/manifest.json',import.meta.url)),'A completed backup is required.');
   assert.equal(existing.recordset.length,10,'Refusing to replace a changed match set.');
   for(const r of existing.recordset)assert(r.match_id>=900001&&r.match_id<=900010&&r.generator==='inside-game-demo'&&r.synthetic==='true','Refusing to replace data outside this synthetic demo.');
  }else assert.equal(existing.recordset.length,0,'Refusing to overwrite existing matches; use the reviewed replacement workflow.');
  const catalogs={countries:[{country_id:1,name:'Synthetic Country'}],competitions:[{competition_id:900,competition_name:'Synthetic Demo League',competition_gender:'mixed',competition_youth:false,competition_international:false,country_name:'Synthetic Country'}],
   seasons:[{season_id:2026,season_name:'2026 synthetic'}],competition_seasons:[{competition_id:900,season_id:2026,raw_payload:payload()}],teams:[],players:[],managers:[],stadiums:[],referees:[]};
  for(let team=1;team<=4;team++){
   catalogs.teams.push({team_id:team,team_name:TEAM_NAMES[team],country_id:1});catalogs.managers.push({manager_id:team,name:`Synthetic Coach ${team}`,country_id:1});catalogs.stadiums.push({stadium_id:team,name:`Synthetic Stadium ${team}`,country_id:1});
   for(let slot=1;slot<=14;slot++)catalogs.players.push({player_id:team*100+slot,player_name:`Synthetic Player ${team}-${slot}`,country_id:1});
  }
  for(let i=1;i<=2;i++)catalogs.referees.push({referee_id:i,name:`Synthetic Referee ${i}`,country_id:1});
  if(!replace)for(const [name,rows] of Object.entries(catalogs))await bulk(pool,name,rows);
  for(const [n,r] of Object.entries(catalogs))counts[n]=r.length;
  // Install the semantic validator and include it in the normal publish path.
  const quality=readFileSync(new URL('./quality-rules.sql',import.meta.url),'utf8').split(/^GO\s*$/mi).filter(s=>s.trim());
  for(const batch of quality)await pool.request().batch(batch);
  let proc=(await pool.request().query("SELECT OBJECT_DEFINITION(OBJECT_ID('statsbomb.validate_match')) definition")).recordset[0].definition;
  if(!proc.includes('EXEC statsbomb.validate_semantics')){
   proc=proc.replace(/CREATE\s+PROCEDURE/i,'ALTER PROCEDURE').replace(/END\s*;?\s*$/i,'EXEC statsbomb.validate_semantics @match_id;\nEND;');
   await pool.request().batch(proc);
  }
  for(let mi=0;mi<MATCH_COUNT;mi++){
   const {match,tables}=generateMatch(mi),audit=auditData(tables);assert.equal(audit.status,'passed',JSON.stringify(audit.errors));
   const tx=pool.transaction();await tx.begin();
   try{
    if(replace){
     // This is an administrator-only repair with a backup. Transactional DDL
     // holds a schema lock until commit; readers never see a half-loaded match.
     await tx.request().input('id',sql.Int,match).batch(`
       DISABLE TRIGGER statsbomb.seal_match ON statsbomb.matches;
       UPDATE statsbomb.matches SET data_status='loading' WHERE match_id=@id;
       ENABLE TRIGGER statsbomb.seal_match ON statsbomb.matches;
     `);
     for(const name of [...order].reverse()){
      const clause=name==='frame_360_players'?'event_id IN(SELECT event_id FROM statsbomb.events WHERE match_id=@id)':'match_id=@id';
      await tx.request().input('id',sql.Int,match).query(`DELETE FROM statsbomb.[${name}] WHERE ${clause}`);
     }
    }
    for(const name of order){const rows=tables[name]??[];for(let offset=0;offset<rows.length;offset+=10000)await bulk(tx,name,rows.slice(offset,offset+10000));}
    await tx.request().input('id',sql.Int,match).query('EXEC statsbomb.publish_match @match_id=@id');
    await tx.commit();
   }catch(e){try{await tx.rollback();}catch{}throw e;}
   for(const [n,r]of Object.entries(tables))counts[n]=(counts[n]??0)+r.length;
   console.log(JSON.stringify({match,status:'published',version:VERSION,events:tables.events.length,shots:tables.event_shots.length,score:[tables.matches[0].home_score,tables.matches[0].away_score]}));
  }
  for(const t of model.tables)counts[t.name]??=0;
  writeFileSync(new URL('./seed-report.json',import.meta.url),JSON.stringify({seed:SEED,version:VERSION,is_synthetic:true,matches:MATCH_COUNT,counts},null,2)+'\n');
 }catch(e){console.error(JSON.stringify(safeError(e)));process.exitCode=1;}
 finally{await pool.close();}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await seed({replace:process.argv.includes('--replace-demo')});
