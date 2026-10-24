import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createReadStream, readFileSync, writeFileSync } from 'node:fs';
import { createGunzip } from 'node:zlib';
import { createInterface } from 'node:readline';
import { connect, sql, safeError } from './connection.mjs';

const columns={
 tracking_frames:['period','frame_index','period_time_ms','ball_in_play'],
 tracking_player_positions:['period','frame_index','team_id','player_id','x_m','y_m','is_on_pitch','on_pitch_slot','position_status','sample_method'],
 tracking_ball_positions:['period','frame_index','x_m','y_m','z_m','position_status','sample_method'],
 event_passes:['event_id','match_id','team_id','recipient_player_id','length','angle','end_x','end_y','outcome'],
};
function fingerprint(rows,fields){
 let sum=0n,count=0;
 for(const r of rows){
  const textFields=new Set(['event_id','position_status','sample_method','outcome','ball_in_play','is_on_pitch']);
  const line=fields.map(f=>{
   const v=r[f];
   if(v===null||v===undefined)return 'NULL';
   if(f==='outcome'){const obj=typeof v==='string'?JSON.parse(v):v;return JSON.stringify(obj,Object.keys(obj).sort());}
   return !textFields.has(f)?Number(v).toFixed(6):String(v).toLowerCase();
  }).join('|');
  sum=(sum+BigInt('0x'+createHash('sha256').update(line).digest('hex')))% (1n<<256n);count++;
 }
 return {count,sha256_sum:sum.toString(16).padStart(64,'0')};
}
async function expectedRows(url){
 const rows=[];
 for await(const line of createInterface({input:createReadStream(url).pipe(createGunzip()),crlfDelay:Infinity}))rows.push(JSON.parse(line));
 return rows;
}
const report={testedAt:new Date().toISOString(),source:'Actual complete Azure SQL rows compared with normalized official source samples',status:'running',matches:[]};
const pool=await connect(),allReal=process.argv.includes('--all-real');
const targets=[...[1,2].map(game=>({game,id:900010+game,cache:'metrica'})),...(allReal?Array.from({length:8},(_,i)=>({game:i+1,id:900101+i,cache:'skillcorner'})):[])];
try{
 for(const {game,id,cache} of targets){
  const folder=new URL(`../../.cache/${cache}/prepared-${game}/`,import.meta.url);
  const m={match:id,status:'running',fingerprints:{}};
  for(const [name,fields] of Object.entries(columns)){
   const expected=fingerprint(await expectedRows(new URL(`${name}.jsonl.gz`,folder)),fields);
   const result=await pool.request().input('id',sql.Int,id).query(`SELECT ${fields.map(f=>'['+f+']').join(',')} FROM statsbomb.[${name}] WHERE match_id=@id`);
   const actual=fingerprint(result.recordset,fields);
   assert.deepEqual(actual,expected,`Source mismatch in ${id}/${name}`);
   m.fingerprints[name]=actual;
  }
  const r=await pool.request().input('id',sql.Int,id).query(`
   SELECT period,COUNT(*) samples,MIN(period_time_ms) first_ms,MAX(period_time_ms) last_ms,
    SUM(CASE WHEN period_time_ms<300000 THEN 1 ELSE 0 END) first_five_minutes_samples
    FROM statsbomb.tracking_frames WHERE match_id=@id GROUP BY period ORDER BY period;
   SELECT COUNT(*) n FROM statsbomb.event_tracking_links l JOIN statsbomb.events e ON e.event_id=l.event_id
    JOIN statsbomb.tracking_frames f ON f.run_id=l.run_id AND f.period=l.period AND f.frame_index=l.frame_index
    WHERE l.match_id=@id AND ABS(e.period_time_ms-f.period_time_ms)>160;
   SELECT COUNT(*) n FROM statsbomb.event_shots WHERE match_id=@id AND statsbomb_xg IS NOT NULL;
   SELECT is_synthetic,sample_rate_hz,JSON_VALUE(config,'$.provider') provider FROM statsbomb.tracking_runs WHERE match_id=@id;
   SELECT COUNT(*) n FROM statsbomb.tracking_frames f OUTER APPLY(SELECT COUNT(*) n FROM statsbomb.tracking_player_positions p
    WHERE p.run_id=f.run_id AND p.period=f.period AND p.frame_index=f.frame_index AND p.is_on_pitch=1) p WHERE f.match_id=@id AND p.n<>22;
   EXEC statsbomb.validate_match @match_id=@id;`);
  for(const p of r.recordsets[0])assert.equal(p.first_five_minutes_samples,1500);
  assert.equal(r.recordsets[1][0].n,0,'Event alignment');
  assert.equal(r.recordsets[2][0].n,0,'No fabricated xG');
  assert.equal(r.recordsets[3][0].is_synthetic,false);
  assert.equal(r.recordsets[3][0].sample_rate_hz,5);
  assert.equal(r.recordsets[4][0].n,0,'Source active identities');
  m.periods=r.recordsets[0];m.provenance=r.recordsets[3][0];m.status='passed';report.matches.push(m);
  console.log(JSON.stringify(m));
 }
 if(allReal){
  const catalogue=await pool.request().query("SELECT match_id,JSON_VALUE(raw_payload,'$.provider') provider,COALESCE(JSON_VALUE(raw_payload,'$.source_match_id'),JSON_VALUE(raw_payload,'$.source_game')) source_match_id FROM analytics.matches WHERE JSON_VALUE(raw_payload,'$.is_synthetic')='false'");
  assert(catalogue.recordset.length>=10,'At least ten actual real matches are required');
  assert(new Set(catalogue.recordset.map(r=>`${r.provider}/${r.source_match_id}`)).size>=10,'Real matches must have distinct source games, not duplicated aliases');
  report.catalogue=catalogue.recordset;report.real_match_count=catalogue.recordset.length;
 }
 report.status='passed';
}catch(e){report.status='failed';report.error=safeError(e);console.error(JSON.stringify(report.error));process.exitCode=1;}
finally{writeFileSync(new URL(allReal?'./real-data-cloud-report.json':'./metrica-cloud-report.json',import.meta.url),JSON.stringify(report,null,2)+'\n');await pool.close();}
