import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { connect, model, safeError } from './connection.mjs';

const fixture=`
 INSERT statsbomb.matches(match_id,competition_id,season_id,match_date,raw_payload) VALUES(999991,900,2026,'2026-10-20','{}');
 INSERT statsbomb.match_teams(match_id,team_id,side) VALUES(999991,1,'home'),(999991,2,'away');
 INSERT statsbomb.match_lineups(match_id,team_id,player_id,raw_payload) VALUES(999991,1,101,'{}'),(999991,1,102,'{}'),(999991,2,201,'{}');
 INSERT statsbomb.events(event_id,match_id,event_index,period,timestamp,type_id,team_id,player_id,raw_payload) VALUES
 ('ffffffff-ffff-5fff-8fff-000000000001',999991,1,1,'00:00:01.000',30,1,101,'{}'),
 ('ffffffff-ffff-5fff-8fff-000000000002',999991,2,1,'00:00:01.000',16,1,102,'{}');
 INSERT statsbomb.event_passes(event_id,match_id,team_id,recipient_player_id) VALUES('ffffffff-ffff-5fff-8fff-000000000001',999991,1,102);
 INSERT statsbomb.event_shots(event_id,match_id,team_id,statsbomb_xg,key_pass_id) VALUES('ffffffff-ffff-5fff-8fff-000000000002',999991,1,.25,'ffffffff-ffff-5fff-8fff-000000000001');
 INSERT statsbomb.tracking_runs(run_id,match_id,label,generator_name,generator_version,sample_rate_hz,pitch_length_m,pitch_width_m,max_event_offset_ms)
 VALUES('ffffffff-ffff-5fff-8fff-000000000010',999991,'test','test','1',1,105,68,100);
 INSERT statsbomb.tracking_periods(run_id,match_id,period,duration_ms,home_attacks_positive_x) VALUES('ffffffff-ffff-5fff-8fff-000000000010',999991,1,2000,1);
 INSERT statsbomb.tracking_frames(run_id,match_id,period,frame_index,period_time_ms) VALUES
 ('ffffffff-ffff-5fff-8fff-000000000010',999991,1,0,0),('ffffffff-ffff-5fff-8fff-000000000010',999991,1,1,1000);
 INSERT statsbomb.tracking_player_positions(run_id,match_id,period,frame_index,team_id,player_id,x_m,y_m,on_pitch_slot) VALUES
 ('ffffffff-ffff-5fff-8fff-000000000010',999991,1,1,1,101,30,20,1),('ffffffff-ffff-5fff-8fff-000000000010',999991,1,1,2,201,31,21,1);
 INSERT statsbomb.event_tracking_links(event_id,run_id,match_id,period,frame_index,alignment_method)
 VALUES('ffffffff-ffff-5fff-8fff-000000000002','ffffffff-ffff-5fff-8fff-000000000010',999991,1,1,'exact');
`;
const tests=[
 ['valid graph publishes',null,'EXEC statsbomb.publish_match 999991;'],
 ['missing team',51001,"DELETE statsbomb.match_teams WHERE match_id=999991 AND team_id=2; EXEC statsbomb.publish_match 999991;", "DELETE statsbomb.tracking_player_positions WHERE match_id=999991 AND team_id=2; DELETE statsbomb.match_lineups WHERE match_id=999991 AND team_id=2;"],
 ['missing shot details',51002,'DELETE statsbomb.event_shots WHERE match_id=999991; EXEC statsbomb.publish_match 999991;'],
 ['cross-team recipient',547,'UPDATE statsbomb.event_passes SET recipient_player_id=201 WHERE match_id=999991;'],
 ['wrong event subtype',547,'UPDATE statsbomb.event_passes SET event_type_id=16 WHERE match_id=999991;'],
 ['invalid xG',547,'UPDATE statsbomb.event_shots SET statsbomb_xg=1.1 WHERE match_id=999991;'],
 ['invalid event clock',547,"UPDATE statsbomb.events SET timestamp='00:99:01' WHERE match_id=999991;"],
 ['fraction precision rejected',547,"UPDATE statsbomb.events SET timestamp='00:00:01.1234567' WHERE match_id=999991;"],
 ['duplicate event order',2601,'UPDATE statsbomb.events SET event_index=1 WHERE match_id=999991 AND event_index=2;'],
 ['cross-match relation',547,"INSERT statsbomb.event_relations(event_id,related_event_id,match_id) SELECT 'ffffffff-ffff-5fff-8fff-000000000001',event_id,999991 FROM statsbomb.events WHERE match_id=900001 AND event_index=1;"],
 ['duplicate active slot',2601,"INSERT statsbomb.tracking_player_positions(run_id,match_id,period,frame_index,team_id,player_id,x_m,y_m,on_pitch_slot) VALUES('ffffffff-ffff-5fff-8fff-000000000010',999991,1,1,1,102,35,20,1);"],
 ['12th slot rejected',547,'UPDATE statsbomb.tracking_player_positions SET on_pitch_slot=12 WHERE match_id=999991;'],
 ['missing status with coordinates',547,"UPDATE statsbomb.tracking_player_positions SET position_status='missing' WHERE match_id=999991;"],
 ['explicit missing sample accepted',null,"UPDATE statsbomb.tracking_player_positions SET position_status='missing',sample_method='missing',x_m=NULL,y_m=NULL WHERE match_id=999991 AND player_id=101; EXEC statsbomb.publish_match 999991;"],
 ['frame beyond period',51003,'UPDATE statsbomb.tracking_frames SET period_time_ms=3000 WHERE match_id=999991 AND frame_index=1; EXEC statsbomb.publish_match 999991;'],
 ['misaligned exact link',51004,'UPDATE statsbomb.tracking_frames SET period_time_ms=1050 WHERE match_id=999991 AND frame_index=1; EXEC statsbomb.publish_match 999991;'],
 ['link beyond tolerance',51004,"UPDATE statsbomb.event_tracking_links SET alignment_method='within_tolerance',frame_index=0 WHERE match_id=999991; EXEC statsbomb.publish_match 999991;"],
 ['period mismatch rejected',547,'UPDATE statsbomb.event_tracking_links SET period=2 WHERE match_id=999991;'],
 ['immutable run metadata',51009,'UPDATE statsbomb.tracking_runs SET sample_rate_hz=2 WHERE match_id=999991;'],
 ['published children sealed',51008,'EXEC statsbomb.publish_match 999991; UPDATE statsbomb.event_shots SET statsbomb_xg=.5 WHERE match_id=999991;'],
 ['published parent sealed',51005,"EXEC statsbomb.publish_match 999991; UPDATE statsbomb.matches SET data_status='loading' WHERE match_id=999991;"],
 ['anonymous 360 paired polygon',51010,"INSERT statsbomb.frames_360(event_id,match_id,visible_area,raw_payload) VALUES('ffffffff-ffff-5fff-8fff-000000000002',999991,'[0,1,2]','{}');"],
 ['non-numeric polygon',51010,"INSERT statsbomb.frames_360(event_id,match_id,visible_area,raw_payload) VALUES('ffffffff-ffff-5fff-8fff-000000000002',999991,'[0,1,\"x\",2]','{}');"],
 ['invalid JSON object',547,"UPDATE statsbomb.events SET details='[]' WHERE match_id=999991;"],
 ['unpublished matches hidden',null,"IF EXISTS(SELECT 1 FROM analytics.matches WHERE match_id=999991) THROW 51999,'Loading match exposed',1;"],
 ['assist recipient must shoot',51021,'UPDATE statsbomb.event_passes SET recipient_player_id=101 WHERE match_id=999991; EXEC statsbomb.publish_match 999991;'],
 ['incomplete pass cannot assist',51021,`UPDATE statsbomb.event_passes SET outcome='{"id":9,"name":"Incomplete"}' WHERE match_id=999991; EXEC statsbomb.publish_match 999991;`],
 ['assist must precede shot',51021,'UPDATE statsbomb.events SET timestamp=\'00:00:02.000\' WHERE match_id=999991 AND type_id=30; EXEC statsbomb.publish_match 999991;'],
 ['shot code/name must agree',51022,`UPDATE statsbomb.event_shots SET outcome='{"id":96,"name":"Off T"}' WHERE match_id=999991; EXEC statsbomb.publish_match 999991;`],
 ['possession has one team',51023,'UPDATE statsbomb.events SET possession=1,possession_team_id=CASE WHEN type_id=30 THEN 1 ELSE 2 END WHERE match_id=999991; EXEC statsbomb.publish_match 999991;'],
 ['negative shot height rejected',547,'UPDATE statsbomb.event_shots SET end_z=-1 WHERE match_id=999991;'],
];
const pool=await connect();
const report={status:'running',testedAt:new Date().toISOString(),tests:[],counts:{},insights:{}};
try {
  const counts=await pool.request().query(model.tables.map(t=>`SELECT '${t.name}' name,COUNT_BIG(*) n FROM statsbomb.[${t.name}]`).join(' UNION ALL '));
  report.counts=Object.fromEntries(counts.recordset.map(r=>[r.name,Number(r.n)]));
  assert.equal(Object.keys(report.counts).length,30);
  assert(report.counts.matches>=10);
  assert(report.counts.tracking_frames>=54020);
  assert(report.counts.tracking_player_positions>=1188440);
  const expected=JSON.parse(readFileSync(new URL('./seed-report.json',import.meta.url),'utf8'));
  const scopedTables=model.tables.filter(t=>t.fields.some(f=>f.name==='match_id'));
  const legacy=await pool.request().query(scopedTables.map(t=>`SELECT '${t.name}' name,COUNT_BIG(*) n FROM statsbomb.[${t.name}] WHERE match_id BETWEEN 900001 AND 900010`).join(' UNION ALL '));
  report.syntheticCounts=Object.fromEntries(legacy.recordset.map(r=>[r.name,Number(r.n)]));
  for(const [name,n] of Object.entries(expected.counts)){
   if(name in report.syntheticCounts)assert.equal(report.syntheticCounts[name],n,`Synthetic count for ${name} must equal its load report`);
   else assert(report.counts[name]>=n,`The historical ${name} rows must remain present`);
  }
  const fk=await pool.request().query("SELECT COUNT(*) n FROM sys.foreign_keys WHERE schema_id=SCHEMA_ID('statsbomb') AND is_disabled=0 AND is_not_trusted=0");
  assert.equal(fk.recordset[0].n,43);
  for(const [name,expected,statement,before=''] of tests) {
    const tx=pool.transaction();await tx.begin();
    let caught;
    try {await tx.request().batch(fixture+before);await tx.request().batch(statement);}
    catch(e){caught=e;}
    finally{try{await tx.rollback();}catch{}}
    const accepted=expected===null?!caught:!!caught&&(caught.number===expected||(expected===2601&&caught.number===2627));
    report.tests.push({name,passed:accepted,errorNumber:caught?.number??null});
    if(!accepted) throw new Error(`Test '${name}' expected ${expected}; got ${caught?.number}: ${caught?.message}`);
  }
  const queryText=readFileSync(new URL('./queries.sql',import.meta.url),'utf8');
  const insights=await pool.request().batch(queryText);
  assert.equal(insights.recordsets.length,7);
  report.insights={shotSummary:insights.recordsets[0],shotsOnTarget:insights.recordsets[1].length,
    positionsAtSecond600:insights.recordsets[2].length,heatmapCells:insights.recordsets[3].length,
    duelGroups:insights.recordsets[4].length,pressureGroups:insights.recordsets[5].length,nearbyPlayers:insights.recordsets[6].length};
  assert.equal(report.insights.positionsAtSecond600,22);
  assert(report.insights.heatmapCells>0);
  const integrity=await pool.request().query(`
    SELECT SUM(CASE WHEN n<>22 THEN 1 ELSE 0 END) incomplete_frames FROM
      (SELECT run_id,period,frame_index,COUNT(*) n FROM statsbomb.tracking_player_positions GROUP BY run_id,period,frame_index) f;
    SELECT COUNT(*) bad_links FROM statsbomb.event_tracking_links l JOIN statsbomb.events e ON e.event_id=l.event_id
      JOIN statsbomb.tracking_frames f ON f.run_id=l.run_id AND f.period=l.period AND f.frame_index=l.frame_index
      JOIN statsbomb.tracking_runs r ON r.run_id=l.run_id
      WHERE ABS(f.period_time_ms-e.period_time_ms)>r.max_event_offset_ms OR (l.alignment_method='exact' AND f.period_time_ms<>e.period_time_ms);
    SELECT COUNT(*) incomplete_periods FROM (SELECT p.run_id,p.period,p.duration_ms,CONVERT(bigint,1000/r.sample_rate_hz) step_ms,COUNT(f.frame_index) n,MIN(f.period_time_ms) first_ms,MAX(f.period_time_ms) last_ms
      FROM statsbomb.tracking_periods p JOIN statsbomb.tracking_runs r ON r.run_id=p.run_id
      JOIN statsbomb.tracking_frames f ON f.run_id=p.run_id AND f.period=p.period GROUP BY p.run_id,p.period,p.duration_ms,r.sample_rate_hz) x
      WHERE first_ms<>0 OR last_ms<>duration_ms/step_ms*step_ms OR n<>duration_ms/step_ms+1;
    SELECT MAX(SQRT(POWER((CASE WHEN (p.home_attacks_positive_x=1 AND mt.side='home') OR (p.home_attacks_positive_x=0 AND mt.side='away') THEN e.location_x*105/120 ELSE 105-e.location_x*105/120 END)-pos.x_m,2)
      +POWER((CASE WHEN (p.home_attacks_positive_x=1 AND mt.side='home') OR (p.home_attacks_positive_x=0 AND mt.side='away') THEN e.location_y*68/80 ELSE 68-e.location_y*68/80 END)-pos.y_m,2))) max_error_m
      FROM statsbomb.events e JOIN statsbomb.event_tracking_links l ON l.event_id=e.event_id
      JOIN statsbomb.tracking_player_positions pos ON pos.run_id=l.run_id AND pos.period=l.period AND pos.frame_index=l.frame_index AND pos.player_id=e.player_id
      JOIN statsbomb.tracking_periods p ON p.run_id=l.run_id AND p.period=l.period JOIN statsbomb.match_teams mt ON mt.match_id=e.match_id AND mt.team_id=e.team_id
      JOIN statsbomb.tracking_runs r ON r.run_id=l.run_id AND r.is_synthetic=1;
  `);
  report.integrity=integrity.recordsets.map(s=>s[0]);
  assert.equal(report.integrity[0].incomplete_frames,0);assert.equal(report.integrity[1].bad_links,0);assert.equal(report.integrity[2].incomplete_periods,0);
  assert(report.integrity[3].max_error_m<1e-9);
  report.status='passed';
  console.log(JSON.stringify({status:report.status,tests:report.tests.length,counts:report.counts,insights:report.insights,integrity:report.integrity}));
} catch(e){report.status='failed';report.error=safeError(e);console.error(JSON.stringify(report.error));process.exitCode=1;}
finally{writeFileSync(new URL('./validation-report.json',import.meta.url),JSON.stringify(report,null,2)+'\n');await pool.close();}
