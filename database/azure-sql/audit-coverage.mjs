import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { connect, safeError } from './connection.mjs';

const pool=await connect(),report={testedAt:new Date().toISOString(),status:'running',source:'Rows read from Azure SQL; synthetic 3.0.0',checks:[],sections:{}};
const queries={
 versions:`SELECT JSON_VALUE(raw_payload,'$.version') version,COUNT(*) n FROM analytics.matches GROUP BY JSON_VALUE(raw_payload,'$.version')`,
 types:`SELECT match_id,type_id,type_name,COUNT(*) n FROM analytics.events GROUP BY match_id,type_id,type_name`,
 dribbles:`SELECT JSON_VALUE(details,'$.dribble.outcome.name') outcome,COUNT(*) n FROM analytics.events WHERE type_id=14 GROUP BY JSON_VALUE(details,'$.dribble.outcome.name')`,
 aerial:`SELECT
  (SELECT COUNT(*) FROM analytics.events WHERE type_id=4 AND JSON_VALUE(details,'$.duel.type.id')='10') losses,
  (SELECT COUNT(*) FROM analytics.events WHERE type_id=9 AND JSON_VALUE(details,'$.clearance.aerial_won')='true') wins,
  (SELECT COUNT(*) FROM analytics.event_relations r JOIN analytics.events a ON a.event_id=r.event_id JOIN analytics.events b ON b.event_id=r.related_event_id WHERE a.type_id=4 AND JSON_VALUE(a.details,'$.duel.type.id')='10' AND b.type_id=9 AND JSON_VALUE(b.details,'$.clearance.aerial_won')='true' AND a.period=b.period AND a.period_time_ms=b.period_time_ms AND a.team_id<>b.team_id) linked_contests`,
 substitutions:`SELECT e.match_id,e.team_id,COUNT(*) changes,COUNT(DISTINCT JSON_VALUE(e.details,'$.substitution.replacement.id')) replacements FROM analytics.events e WHERE type_id=19 GROUP BY match_id,team_id`,
 receipts:`SELECT (SELECT COUNT(*) FROM analytics.events WHERE type_id=42) receipts,(SELECT COUNT(*) FROM analytics.event_passes WHERE recipient_player_id IS NOT NULL AND outcome IS NULL) completed_passes`,
 restarts:`SELECT JSON_VALUE(pass_type,'$.name') restart,COUNT(*) n FROM analytics.event_passes WHERE pass_type IS NOT NULL GROUP BY JSON_VALUE(pass_type,'$.name')`,
 shotBodies:`SELECT JSON_VALUE(body_part,'$.name') body,COUNT(*) n FROM analytics.event_shots GROUP BY JSON_VALUE(body_part,'$.name')`,
 passHeights:`SELECT JSON_VALUE(height,'$.name') height,COUNT(*) n FROM analytics.event_passes GROUP BY JSON_VALUE(height,'$.name')`,
 passFlags:`SELECT SUM(CONVERT(int,[cross])) crosses,SUM(CONVERT(int,cut_back)) cut_backs,SUM(CONVERT(int,[switch])) switches FROM analytics.event_passes`,
 roles:`SELECT COUNT(DISTINCT player_id) tracked_players FROM analytics.tracking_player_positions`,
 formation:`SELECT formation,COUNT(*) n FROM analytics.event_tactics GROUP BY formation`,
 carryOverlaps:`SELECT COUNT(*) overlaps FROM analytics.events a JOIN analytics.events b ON a.match_id=b.match_id AND a.period=b.period AND a.player_id=b.player_id AND a.type_id=43 AND b.type_id=14 AND b.duration>0 AND a.period_time_ms<b.period_time_ms+b.duration*1000 AND a.period_time_ms+a.duration*1000>b.period_time_ms`,
 tackleResults:`SELECT JSON_VALUE(details,'$.duel.outcome.name') outcome,COUNT(*) n FROM analytics.events WHERE type_id=4 AND JSON_VALUE(details,'$.duel.type.id')='11' GROUP BY JSON_VALUE(details,'$.duel.outcome.name')`,
 failedTackleAttribution:`SELECT COUNT(*) bad_attributions FROM analytics.events a WHERE a.type_id=4 AND JSON_VALUE(a.details,'$.duel.type.id')='11' AND JSON_VALUE(a.details,'$.duel.outcome.id')='13' AND NOT EXISTS(SELECT 1 FROM analytics.event_relations r JOIN analytics.events b ON b.event_id=r.related_event_id WHERE r.event_id=a.event_id AND b.type_id=14 AND JSON_VALUE(b.details,'$.dribble.outcome.id')='8' AND b.team_id<>a.team_id AND b.period=a.period AND b.period_time_ms=a.period_time_ms)`,
 };
const check=(name,ok)=>{assert(ok,name);report.checks.push({name,passed:true});};
// This report is historical synthetic coverage, never a mixture of providers.
const syntheticQuery=query=>{
 const names=[...new Set([...query.matchAll(/analytics\.(\w+)/g)].map(m=>m[1]))];
 return 'WITH '+names.map(n=>`syn_${n} AS (SELECT * FROM analytics.[${n}] WHERE match_id BETWEEN 900001 AND 900010)`).join(',')+'\n'+query.replace(/analytics\.(\w+)/g,'syn_$1');
};
try{
 for(const [name,query] of Object.entries(queries))report.sections[name]=(await pool.request().query(syntheticQuery(query))).recordset;
 const s=report.sections;
 check('Exactly ten published matches at 3.0.0',s.versions.length===1&&s.versions[0].version==='3.0.0'&&s.versions[0].n===10);
 for(const type of [2,3,4,6,9,10,14,16,17,19,21,22,23,30,33,35,36,38,39,42,43])check(`Type ${type} exists in every match`,s.types.filter(r=>r.type_id===type).length===10);
 for(const outcome of ['Complete','Incomplete'])check(`Dribble ${outcome}`,s.dribbles.some(r=>r.outcome===outcome&&r.n>0));
 check('Every aerial contest has linked winner and loser',s.aerial[0].wins>0&&s.aerial[0].wins===s.aerial[0].losses&&s.aerial[0].wins===s.aerial[0].linked_contests);
 check('Three substitutions per team per match',s.substitutions.length===20&&s.substitutions.every(r=>r.changes===3&&r.replacements===3));
 check('One recorded reception per completed pass',s.receipts[0].receipts===s.receipts[0].completed_passes);
 for(const restart of ['Corner','Throw-in','Free Kick','Goal Kick','Kick Off'])check(`Restart ${restart}`,s.restarts.some(r=>r.restart===restart&&r.n>0));
 for(const body of ['Head','Left Foot','Right Foot'])check(`Shot body ${body}`,s.shotBodies.some(r=>r.body===body&&r.n>0));
 for(const height of ['Ground Pass','Low Pass','High Pass'])check(`Pass height ${height}`,s.passHeights.some(r=>r.height===height&&r.n>0));
 check('All 56 registered players actually have playing samples',s.roles[0].tracked_players===56);
 check('Carries do not overlap annotated dribbles',s.carryOverlaps[0].overlaps===0);
 check('Failed tackler is the beaten challenger, not the carrier',s.failedTackleAttribution[0].bad_attributions===0);
 check('Won and failed tackle attempts are present',s.tackleResults.some(r=>r.outcome==='Won'&&r.n>0)&&s.tackleResults.some(r=>r.outcome==='Lost In Play'&&r.n>0));
 const examples=await pool.request().batch(readFileSync(new URL('./queries-coverage.sql',import.meta.url),'utf8'));
 report.exampleQueryRows=examples.recordsets.map(rows=>rows.length);
 check('Nine analytic example queries return rows',examples.recordsets.length===9&&examples.recordsets.every(rows=>rows.length>0));
 report.status='passed';console.log(JSON.stringify({status:report.status,checks:report.checks.length,aerial:s.aerial,dribbles:s.dribbles,restarts:s.restarts,exampleQueryRows:report.exampleQueryRows}));
}catch(e){report.status='failed';report.error=safeError(e);console.error(JSON.stringify(report.error));process.exitCode=1;}
finally{writeFileSync(new URL('./coverage-cloud-report.json',import.meta.url),JSON.stringify(report,null,2)+'\n');await pool.close();}
