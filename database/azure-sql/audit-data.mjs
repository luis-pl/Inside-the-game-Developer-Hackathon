import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { generateMatch, MATCH_COUNT } from './scenario-v2.mjs';
const dist=(a,b)=>Math.hypot(a.x_m-b.x_m,a.y_m-b.y_m);
export function auditData(tables){
 const errors={},metrics={maxPlayerSpeed:0,maxPlayerAcceleration:0,maxBallSpeed:0,minOutfieldDistance:Infinity,maxOutfieldDistance:0,shots:0,pressures:0,duels:0,passes:0,cards:(tables.lineup_cards??[]).length};
 const fail=(name,condition,example)=>{if(!condition){const r=errors[name]??={count:0,examples:[]};r.count++;if(r.examples.length<3)r.examples.push(example);}};
 const events=new Map(tables.events.map(e=>[e.event_id,e])),teams=tables.match_teams.sort((a,b)=>a.side==='home'?-1:1).map(r=>r.team_id),match=tables.matches[0];
 const positions=new Map(),frames=new Map(tables.tracking_frames.map(f=>[`${f.period}/${f.frame_index}`,f])),balls=new Map(tables.tracking_ball_positions.map(b=>[`${b.period}/${b.frame_index}`,b]));
 const previous=new Map(),travel=new Map();
 for(const p of tables.tracking_player_positions){
  const k=`${p.period}/${p.frame_index}`,arr=positions.get(k)??[];arr.push(p);positions.set(k,arr);
  fail('player_bounds',p.x_m>=0&&p.x_m<=105&&p.y_m>=0&&p.y_m<=68,k);
  const pk=`${p.period}/${p.player_id}`,old=previous.get(pk);
  if(old){const vx=p.x_m-old.p.x_m,vy=p.y_m-old.p.y_m,speed=Math.hypot(vx,vy),accel=Math.hypot(vx-old.vx,vy-old.vy);metrics.maxPlayerSpeed=Math.max(metrics.maxPlayerSpeed,speed);if(old.hasVelocity)metrics.maxPlayerAcceleration=Math.max(metrics.maxPlayerAcceleration,accel);
   fail('player_speed',speed<=10,{...p,speed});if(old.hasVelocity)fail('player_acceleration',accel<=7,{...p,accel});
   travel.set(p.player_id,(travel.get(p.player_id)||0)+speed);previous.set(pk,{p,vx,vy,hasVelocity:true});
  }else previous.set(pk,{p,vx:0,vy:0,hasVelocity:false});
 }
 for(const [id,d] of travel)if(id%100!==1){metrics.minOutfieldDistance=Math.min(metrics.minOutfieldDistance,d);metrics.maxOutfieldDistance=Math.max(metrics.maxOutfieldDistance,d);}
 for(const [k,f] of frames){
  const ps=positions.get(k)??[],b=balls.get(k);fail('frame_coverage',ps.length===22&&b,k);
  for(const team of teams)fail('team_capacity',ps.filter(p=>p.team_id===team&&p.is_on_pitch).length===11,k);
  if(b){fail('ball_bounds',b.x_m>=0&&b.x_m<=105&&b.y_m>=0&&b.y_m<=68&&b.z_m>=0,k);
   const prev=balls.get(`${f.period}/${f.frame_index-1}`);if(prev){const speed=Math.hypot(b.x_m-prev.x_m,b.y_m-prev.y_m,b.z_m-prev.z_m);metrics.maxBallSpeed=Math.max(metrics.maxBallSpeed,speed);fail('ball_speed',speed<=35,{k,speed});}}
 }
 const at=e=>(positions.get(`${e.period}/${Math.round(e.period_time_ms!==undefined?Number(e.period_time_ms)/1000:(e.minute-(e.period-1)*45)*60+e.second)}`)??[]);
 const sec=e=>e.period_time_ms!==undefined?Number(e.period_time_ms)/1000:(e.minute-(e.period-1)*45)*60+e.second;
 const ballAt=(p,t)=>balls.get(`${p}/${Math.round(t)}`);
 const fixed=(e,x,y)=>{const pos=(e.period===1)===(e.team_id===teams[0]);return {x_m:pos?x*105/120:105-x*105/120,y_m:pos?y*68/80:68-y*68/80};};
 const actor=e=>at(e).find(p=>p.player_id===e.player_id);
 const poss=new Map();
 const canonicalPositions={1:'Goalkeeper',2:'Right Back',3:'Right Center Back',5:'Left Center Back',6:'Left Back',13:'Right Center Midfield',10:'Center Defensive Midfield',15:'Left Center Midfield',17:'Right Wing',23:'Center Forward',21:'Left Wing'};
 for(const e of tables.events){
  if(e.position_id!==null)fail('position_code_name',canonicalPositions[e.position_id]===e.position_name,e.event_id);
  if(e.details?.foul_committed?.card)fail('card_code_name',e.details.foul_committed.card.id===7&&e.details.foul_committed.card.name==='Yellow Card',e.event_id);
  if(e.type_id===4){const d=e.details?.duel;fail('duel_code_name',d?.type?.id===11&&d.type.name==='Tackle'&&({4:'Won',13:'Lost In Play'})[d.outcome?.id]===d.outcome?.name,e.event_id);}
  if(e.type_id===33){const d=e.details?.['50_50']?.outcome;fail('fifty_code_name',({1:'Lost',3:'Success To Team'})[d?.id]===d?.name,e.event_id);}
  if(e.type_id===23){const d=e.details?.goalkeeper?.type;fail('keeper_code_name',d?.id===33&&d.name==='Shot Saved',e.event_id);}
  if(e.possession!==null&&e.possession!==undefined){const old=poss.get(e.possession);fail('possession_team',old===undefined||old===e.possession_team_id,e.event_id);poss.set(e.possession,e.possession_team_id);}
  if(e.player_id!==null){const p=actor(e);fail('active_actor',!!p&&p.is_on_pitch,e.event_id);if(p)fail('event_location',dist(p,fixed(e,e.location_x,e.location_y))<.001,e.event_id);}
  if([17,4,33,21,22].includes(e.type_id)){
   const p=actor(e),b=ballAt(e.period,sec(e));fail('contact_distance',p&&b&&dist(p,b)<3,e.event_id);
   const near=at(e).some(o=>o.team_id!==e.team_id&&dist(o,p)<3.2);fail('opponent_distance',near,e.event_id);
   if(e.type_id===17)metrics.pressures++;else if([4,33].includes(e.type_id))metrics.duels++;
  }
  if([30,16,17,4,33].includes(e.type_id))fail('live_action',frames.get(`${e.period}/${sec(e)}`)?.ball_in_play===true,e.event_id);
 }
 for(const pass of tables.event_passes){
  metrics.passes++;const e=events.get(pass.event_id),start=sec(e),end=start+e.duration,b=ballAt(e.period,start),landing=ballAt(e.period,end);
  fail('pass_duration',e.duration>0&&Number.isInteger(e.duration),e.event_id);
  fail('pass_release',dist(actor(e),b)<.001,e.event_id);
  fail('pass_endpoint',landing&&dist(landing,fixed(e,pass.end_x,pass.end_y))<.001,e.event_id);
  fail('pass_length',Math.abs(pass.length-Math.hypot(pass.end_x-e.location_x,pass.end_y-e.location_y))<.001,e.event_id);
  if(pass.recipient_player_id!==null&&pass.recipient_player_id!==undefined){
   const rec=positions.get(`${e.period}/${end}`)?.find(p=>p.player_id===pass.recipient_player_id);
   fail('pass_reception',rec&&dist(rec,landing)<.001&&rec.team_id===e.team_id,e.event_id);
   const now=at(e).find(p=>p.player_id===pass.recipient_player_id),positive=(e.period===1)===(e.team_id===teams[0]);
   const xx=p=>positive?p.x_m:105-p.x_m;
   const defenders=at(e).filter(p=>p.team_id!==e.team_id).map(xx).sort((a,b)=>b-a);
   fail('offside_completed_pass',xx(now)<=52.5+.05||xx(now)<=xx(b)+.05||xx(now)<=defenders[1]+.05,e.event_id);
  }
  if(pass.pass_type?.id===65){
   fail('kickoff_center',dist(actor(e),{x_m:52.5,y_m:34})<.001,e.event_id);
   for(const p of at(e)){
    const positive=(e.period===1)===(p.team_id===teams[0]),x=positive?p.x_m:105-p.x_m;
    fail('kickoff_own_half',p.player_id===e.player_id||x<=52.5+.001,e.event_id);
    if(p.team_id!==e.team_id)fail('kickoff_opponent_distance',dist(p,b)>=9.15,e.event_id);
   }
  }
 }
 const goalCount=new Map(teams.map(t=>[t,0]));
 for(const s of tables.event_shots){
  metrics.shots++;const e=events.get(s.event_id),code=Number(s.outcome.id),expected={96:'Blocked',97:'Goal',98:'Off T',100:'Saved'}[code];
  fail('shot_code_name',s.outcome.name===expected,s.event_id);
  const end=fixed(e,s.end_x,s.end_y),endAt=sec(e)+e.duration,b=ballAt(e.period,endAt),goal=(e.period===1)===(e.team_id===teams[0])?105:0;
  fail('shot_release',dist(actor(e),ballAt(e.period,sec(e)))<.001,s.event_id);
  fail('shot_endpoint',b&&dist(end,b)<.001&&Math.abs(s.end_z-b.z_m)<.001,{event:s.event_id,end,b});
  if(code===97){goalCount.set(e.team_id,goalCount.get(e.team_id)+1);fail('goal_geometry',Math.abs(end.x_m-goal)<.001&&Math.abs(end.y_m-34)<3.66&&s.end_z<2.44,s.event_id);
   const starts=tables.event_passes.filter(p=>p.pass_type?.id===65).map(p=>events.get(p.event_id)).filter(p=>p.period===e.period&&sec(p)>endAt).sort((a,b)=>sec(a)-sec(b));
   if(endAt+30<2700)fail('goal_restart',starts.length&&starts[0].team_id!==e.team_id&&dist(actor(starts[0]),{x_m:52.5,y_m:34})<.001,s.event_id);
  }
  if(code===98)fail('off_target_geometry',Math.abs(end.x_m-goal)<.001&&(Math.abs(end.y_m-34)>3.66||s.end_z>2.44),s.event_id);
  if(code===100){const keeper=positions.get(`${e.period}/${endAt}`)?.find(p=>p.team_id!==e.team_id&&p.on_pitch_slot===1);fail('save_keeper_contact',keeper&&dist(keeper,end)<.001,s.event_id);}
  if(code===96)fail('block_defender_contact',positions.get(`${e.period}/${endAt}`)?.some(p=>p.team_id!==e.team_id&&dist(p,end)<.001),s.event_id);
  if(s.key_pass_id){const pass=tables.event_passes.find(p=>p.event_id===s.key_pass_id),pe=events.get(s.key_pass_id);
   fail('assist_receiver',pass?.recipient_player_id===e.player_id,s.event_id);fail('assist_complete',pass?.outcome===null||pass?.outcome===undefined,s.event_id);
   fail('assist_timing',pe&&pe.period===e.period&&sec(pe)+pe.duration<=sec(e)&&sec(e)-sec(pe)<10,s.event_id);
   fail('assist_flags',pass?.shot_assist===true&&pass?.goal_assist===(code===97),s.event_id);
  }
 }
 fail('score_matches_goals',match.home_score===goalCount.get(teams[0])&&match.away_score===goalCount.get(teams[1]),match.match_id);
 const lookup=new Map(tables.shot_freeze_players.map(p=>[`${p.event_id}/${p.frame_player_index}`,p]));
 for(const f of tables.frames_360){const e=events.get(f.event_id),rows=tables.frame_360_players.filter(p=>p.event_id===f.event_id);
  fail('snapshot_actor',rows.filter(p=>p.actor).length===1,f.event_id);
  for(const p of rows){const identified=lookup.get(`${f.event_id}/${p.frame_player_index}`),tracked=at(e).find(x=>x.player_id===identified?.player_id);
   fail('snapshot_tracking',tracked&&dist(tracked,fixed(e,p.location_x,p.location_y))<.001,f.event_id);
   fail('snapshot_identity_flags',tracked&&p.teammate===(tracked.team_id===e.team_id)&&p.actor===(tracked.player_id===e.player_id)&&p.keeper===(tracked.on_pitch_slot===1),f.event_id);}
 }
 for(const card of tables.lineup_cards??[])fail('card_event',tables.events.some(e=>e.type_id===22&&e.player_id===card.player_id&&e.period===card.period&&e.details?.foul_committed?.card?.name===card.card_type),card.player_id);
 return {match:match.match_id,status:Object.keys(errors).length?'failed':'passed',metrics,errors};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const reports=[];
 for(let i=0;i<MATCH_COUNT;i++){const r=auditData(generateMatch(i).tables);reports.push(r);console.log(JSON.stringify(r));}
 writeFileSync(new URL('./realism-local-report.json',import.meta.url),JSON.stringify({status:reports.every(r=>r.status==='passed')?'passed':'failed',reports},null,2)+'\n');
 if(reports.some(r=>r.status!=='passed'))process.exitCode=1;
}
