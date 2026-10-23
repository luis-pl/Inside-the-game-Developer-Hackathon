import { createHash } from 'node:crypto';
export const SEED=20261021, MATCH_COUNT=10, HALF_SECONDS=2700, VERSION='3.0.0';
export const payload=(extra={})=>({is_synthetic:true,seed:SEED,generator:'inside-game-demo',version:VERSION,...extra});
const pid=(team,slot)=>team*100+slot;
const ids=[1,2,3,5,6,13,10,15,17,23,21];
const names=['Goalkeeper','Right Back','Right Center Back','Left Center Back','Left Back','Right Center Midfield','Center Defensive Midfield','Left Center Midfield','Right Wing','Center Forward','Left Wing'];
const bx=[6,28,29,29,28,51,47,51,82,85,82],by=[34,9,26,42,59,18,34,50,12,34,56];
const outcomeNames={96:'Blocked',97:'Goal',98:'Off T',100:'Saved'};
const typeNames={2:'Ball Recovery',3:'Dispossessed',4:'Duel',6:'Block',9:'Clearance',10:'Interception',14:'Dribble',16:'Shot',17:'Pressure',18:'Half Start',19:'Substitution',21:'Foul Won',22:'Foul Committed',23:'Goal Keeper',24:'Bad Behaviour',30:'Pass',33:'50/50',34:'Half End',35:'Starting XI',36:'Tactical Shift',38:'Miscontrol',39:'Dribbled Past',42:'Ball Receipt*',43:'Carry'};
export const uid=label=>{let h=createHash('sha256').update(`${SEED}:v3:${label}`).digest('hex').slice(0,32).split('');h[12]='8';h[16]='8';h=h.join('');return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;};
function rng(seed){let s=seed>>>0;return()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296;};}
const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
const clock=t=>`${String(Math.floor(t/3600)).padStart(2,'0')}:${String(Math.floor(t/60)%60).padStart(2,'0')}:${String(t%60).padStart(2,'0')}.000`;
const ease=x=>x*x*(3-2*x);
const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));

export function generateMatch(mi){
 const schedule=[[1,2],[3,4],[1,3],[2,4],[1,4],[2,3],[2,1],[4,3],[3,1],[4,2]];
 const teams=schedule[mi],match=900001+mi,run=uid(`run:${match}`),random=rng(SEED+mi*104729);
 const tables={},add=(n,r)=>(tables[n]??=[]).push(r),goals=[0,0],actions=[],segments=[],anchors=Array.from({length:3},()=>Array.from({length:2},()=>Array.from({length:11},()=>new Map())));
 let possession=0,serial=0,possessionSide=null;const carded=new Set();
 const attackPositive=(p,s)=>(p===1)===(s===0);
 const fromAttack=(p,s,pt)=>attackPositive(p,s)?{...pt}:{x:105-pt.x,y:68-pt.y};
 const toAttack=fromAttack;
 const normalized=(p,s,pt)=>{const a=toAttack(p,s,pt);return {x:a.x*120/105,y:a.y*80/68};};
 const baseline=(p,s,slot,t)=>{
  const g=slot===1,phase=mi*.79+s*1.17+p*.41+slot*.71;
  const x=clamp(bx[slot-1]+(g?1.2:7)*Math.sin(t/(g?23:6)+phase)+(g?.7:3)*Math.sin(t/(g?8.7:2.5)+phase*.3),g?1:3,g?11:101);
  const y=clamp(by[slot-1]+(g?1.4:5)*Math.sin(t/(g?17.3:5)+phase)+(g?.5:2)*Math.sin(t/(g?7.1:2.2)+phase),1,67);
  return fromAttack(p,s,{x,y});
 };
 // Positions are smooth base paths plus interpolated offsets through exact
 // contact anchors. Exact anchors remain fixed when later actions are planned.
 const point=(p,s,slot,t)=>{
  const base=baseline(p,s,slot,t),map=anchors[p][s][slot-1];
  if(map.has(t))return {...map.get(t)};
  let left=-Infinity,right=Infinity,lp,rp;
  for(const [at,pt] of map){if(at<t&&at>left){left=at;lp=pt;}if(at>t&&at<right){right=at;rp=pt;}}
  const offset=(at,pt)=>{if(!pt)return {x:0,y:0};const b=baseline(p,s,slot,at);return {x:pt.x-b.x,y:pt.y-b.y};};
  // Fixed zero-offset control points make the return continuous. Moving these
  // control times with the queried second would introduce an artificial jump.
  if(!Number.isFinite(left)&&!Number.isFinite(right))return base;
  if(!Number.isFinite(left)){left=right-18;lp=null;if(t<left)return base;}
  if(!Number.isFinite(right)){right=left+18;rp=null;if(t>right)return base;}
  if(right-left>36){
   if(t<=left+18){right=left+18;rp=null;}
   else if(t>=right-18){left=right-18;lp=null;}
   else return base;
  }
  const a=offset(left,lp),b=offset(right,rp),u=ease((t-left)/(right-left));
  return {x:clamp(base.x+a.x*(1-u)+b.x*u,.2,104.8),y:clamp(base.y+a.y*(1-u)+b.y*u,.2,67.8)};
 };
 const anchor=(p,s,slot,t,pt=point(p,s,slot,t))=>{
  const map=anchors[p][s][slot-1];
  if(map.has(t)&&distance(map.get(t),pt)>.001)throw new Error(`Conflicting player anchor ${p}/${s}/${slot}/${t}`);
  const v={x:clamp(pt.x,.2,104.8),y:clamp(pt.y,.2,67.8)};map.set(t,v);return v;
 };
 const owned=(p,s,slot,a,b,live=true)=>{if(b>=a){if(possessionSide!==s){possession++;possessionSide=s;}segments.push({p,a,b,owner:{s,slot},live,possession,possSide:s});}};
 const flight=(p,a,b,start,end,z=0,live=true,arc=0)=>segments.push({p,a,b,start:{...start,z:start.z??0},end:{...end,z},live,arc});
 const event=(p,t,s,slot,type,possSide,detail={},duration=0,meta={})=>{
  const e={event_id:uid(`${match}:${++serial}`),match_id:match,event_index:0,period:p,timestamp:clock(t),minute:(p-1)*45+Math.floor(t/60),second:t%60,
   type_id:type,type_name:typeNames[type],possession:[18,34,35].includes(type)?null:possession,possession_team_id:[18,34,35].includes(type)?null:teams[possSide],play_pattern_id:1,play_pattern_name:'Regular Play',
   team_id:s===null?null:teams[s],player_id:slot===null?null:pid(teams[s],slot),position_id:slot===null?null:ids[slot-1],position_name:slot===null?null:names[slot-1],
   duration,under_pressure:false,counterpress:false,details:detail,raw_payload:payload({period_time_ms:t*1000,...meta}),_t:t,_s:s,_slot:slot};
  actions.push(e);return e;
 };
 const reachable=(p,s,slot,t,target)=>{
  const map=anchors[p][s][slot-1];
  for(const [at,pt] of map)if(Math.abs(t-at)<18&&distance(pt,target)>Math.abs(t-at)*3+.01)return false;
  return true;
 };
 const nearest=(p,s,t,target,exclude=[])=>{
  const candidates=Array.from({length:10},(_,i)=>i+2).filter(x=>!exclude.includes(x));
  const possible=candidates.filter(x=>reachable(p,s,x,t,target));
  if(!possible.length)return null;
  return possible.sort((a,b)=>distance(point(p,s,a,t),target)-distance(point(p,s,b,t),target))[0];
 };
 // Put two defenders goal-side of an advanced receiver at the pass release.
 // This explicitly avoids completing every forward pass to an offside winger.
 const onside=(p,s,t,receiver,sender)=>{
  const rec=toAttack(p,s,point(p,s,receiver,t)),ball=toAttack(p,s,point(p,s,sender,t));
  if(rec.x<=52.5||rec.x<=ball.x)return;
  let placed=0;
  for(const slot of [3,4,2,5,6,7,8,9,10,11]){
   if(placed===2)break;
   if(anchors[p][1-s][slot-1].has(t))continue;
   const prev=toAttack(p,s,point(p,1-s,slot,t));
   const target=fromAttack(p,s,{x:clamp(Math.max(rec.x+1.2,prev.x),3,103),y:prev.y});
   if(!reachable(p,1-s,slot,t,target))continue;
   anchor(p,1-s,slot,t,target);placed++;
  }
 };
 const kickoffPositions=(p,kicking,t)=>{
  for(let s=0;s<2;s++)for(let slot=1;slot<=11;slot++){
   const base=toAttack(p,s,baseline(p,s,slot,t)),pt=slot===10&&s===kicking?{x:52.5,y:34}:fromAttack(p,s,{x:Math.min(base.x,s===kicking?50:42),y:base.y});
   anchor(p,s,slot,t,pt);anchor(p,s,slot,t+1,pt);
  }
 };
 for(let side=0;side<2;side++){
  const team=teams[side];add('match_teams',{match_id:match,team_id:team,side:side?'away':'home',lineup_raw_payload:payload()});
  add('match_team_managers',{match_id:match,team_id:team,manager_index:0,manager_id:team});
  for(let slot=1;slot<=14;slot++){
   add('match_lineups',{match_id:match,team_id:team,player_id:pid(team,slot),jersey_number:slot,raw_payload:payload({bench:slot>11})});
   if(slot<=11)add('lineup_positions',{match_id:match,team_id:team,player_id:pid(team,slot),position_index:0,position_id:ids[slot-1],position:names[slot-1],from_time:'00:00',to_time:'90:00',from_period:1,to_period:2,start_reason:'Starting XI',end_reason:'Final Whistle'});
  }
 }
 for(let p=1;p<=2;p++){
  let t=0,side=p===1?mi%2:1-mi%2,owner=10,restart='kickoff',previousSide=null,afterTurnover=false,episode=0;
  for(let s=0;s<2;s++){
   const e=event(p,0,s,null,35,side,{},0);add('event_tactics',{event_id:e.event_id,event_type_id:35,match_id:match,team_id:teams[s],formation:433});
   for(let slot=1;slot<=11;slot++)add('tactical_lineups',{event_id:e.event_id,match_id:match,team_id:teams[s],player_id:pid(teams[s],slot),position_id:ids[slot-1],position_name:names[slot-1],jersey_number:slot});
  }
  event(p,0,null,null,18,side,{},0);
  while(t<HALF_SECONDS-35){
   possession++;possessionSide=side;episode++;
   const start=t,possSide=side,wantsShot=random()<.30,passCount=5+Math.floor(random()*6);
   if(restart==='kickoff')kickoffPositions(p,side,t);
   if(restart===null)event(p,t,side,owner,2,side,{ball_recovery:{recovery_failure:false}},0,{restart});
   let lastPass=null,finished=false,chainComplete=false;
   for(let j=0;j<passCount&&t<HALF_SECONDS-30;j++){
    const isLast=j===passCount-1;
    if(restart===null&&random()<.035&&t<HALF_SECONDS-50){
     const foulAt=t+2,a=anchor(p,side,owner,foulAt),defender=nearest(p,1-side,foulAt,a);
     if(defender!==null){
     anchor(p,1-side,defender,foulAt,{x:a.x+.7,y:a.y+.4});
     const key=pid(teams[1-side],defender),yellow=!carded.has(key)&&random()<.17;
     event(p,foulAt,1-side,defender,22,side,{foul_committed:yellow?{card:{id:7,name:'Yellow Card'}}:{}});
     event(p,foulAt,side,owner,21,side,{foul_won:{defensive:false}});
     if(yellow){carded.add(key);add('lineup_cards',{match_id:match,team_id:teams[1-side],player_id:key,card_index:0,time:`${String((p-1)*45+Math.floor(foulAt/60)).padStart(2,'0')}:${String(foulAt%60).padStart(2,'0')}`,card_type:'Yellow Card',reason:'Foul Committed',period:p});}
     owned(p,side,owner,t,foulAt);const resume=foulAt+8+Math.floor(random()*5);
     anchor(p,side,owner,resume,a);flight(p,foulAt,resume,a,a,0,false);t=resume;restart='free_kick';
     }
    }
    const hold=restart?1:4+Math.floor(random()*5);
    const kick=t+hold;
    if(kick+10>=HALF_SECONDS)break;
    // A pressure is a nearby defender approaching the current ball carrier.
    let pressured=random()<.47&&restart===null;
    if(pressured){
     const at=kick-2,a=anchor(p,side,owner,at),b=anchor(p,side,owner,kick);
     const opponent=nearest(p,1-side,at,a),angle=random()*Math.PI*2;
     const shift={x:Math.cos(angle)*1.4,y:Math.sin(angle)*1.4};
     if(opponent!==null){
     anchor(p,1-side,opponent,at,{x:a.x+shift.x,y:a.y+shift.y});
     const dribbled=random()<.28;
     if(dribbled){const d=Math.hypot(b.x-a.x,b.y-a.y)||1;shift.x=(b.x-a.x)*1.4/d;shift.y=(b.y-a.y)*1.4/d;
      // Re-anchor the challenger ahead of the carrier, then behind at escape.
      anchors[p][1-side][opponent-1].delete(at);anchor(p,1-side,opponent,at,{x:a.x+shift.x,y:a.y+shift.y});}
     anchor(p,1-side,opponent,kick,{x:b.x+(dribbled?-1:1)*shift.x,y:b.y+(dribbled?-1:1)*shift.y});
     const e=event(p,at,1-side,opponent,17,side,{},2);
     e.counterpress=afterTurnover&&previousSide===1-side&&at-start<=5;
     if(dribbled){
      const win=event(p,at,side,owner,14,side,{dribble:{outcome:{id:8,name:'Complete'},nutmeg:false,overrun:false}},2);
      const lost=event(p,at,1-side,opponent,39,side,{},2);
      add('event_relations',{event_id:win.event_id,related_event_id:lost.event_id,match_id:match});
     }
     }else pressured=false;
    }
    owned(p,side,owner,t,kick,restart===null);
    let recipient=isLast&&wantsShot?9+Math.floor(random()*3):2+Math.floor(random()*10);
    if(recipient===owner)recipient=isLast&&wantsShot?9+(recipient-9+1)%3:recipient===11?8:recipient+1;
    const completed=!(isLast&&!wantsShot);
    const turnover=completed?null:['interception','aerial','tackle','fifty','miscontrol'][Math.floor(random()*5)];
    const origin=anchor(p,side,owner,kick);
    // Receiver has a precise contact point at arrival, based on their smooth path.
    let arrival=kick+Math.max(1,Math.ceil(distance(origin,point(p,side,recipient,kick+2))/19));
    let end=anchor(p,side,recipient,arrival);
    let winner=null,contested=true;
    if(!completed){
     winner=nearest(p,1-side,arrival,end);
     if(winner===null){contested=false;winner=Array.from({length:10},(_,i)=>i+2).sort((a,b)=>distance(point(p,1-side,a,arrival),end)-distance(point(p,1-side,b,arrival),end))[0];}
     if(contested)anchor(p,1-side,winner,arrival,{x:end.x+.7,y:end.y+.4});
     if(!contested||!['tackle','miscontrol'].includes(turnover))end=point(p,1-side,winner,arrival);
    }else onside(p,side,kick,recipient,owner);
    const e=event(p,kick,side,owner,30,side,{},arrival-kick,{arrival_ms:arrival*1000});
    e.under_pressure=pressured;
    const a=normalized(p,side,origin),b=normalized(p,side,end);
    const pass={event_id:e.event_id,event_type_id:30,match_id:match,team_id:teams[side],recipient_player_id:completed?pid(teams[side],recipient):null,
     length:distance(a,b),angle:Math.atan2(b.y-a.y,b.x-a.x),height:{id:1,name:'Ground Pass'},end_x:b.x,end_y:b.y,
     body_part:{id:random()<.25?38:40,name:''},outcome:completed?null:{id:9,name:'Incomplete'},shot_assist:false,goal_assist:false,
     pass_type:restart==='kickoff'?{id:65,name:'Kick Off'}:restart==='goal_kick'?{id:63,name:'Goal Kick'}:restart==='free_kick'?{id:62,name:'Free Kick'}:restart==='corner'?{id:61,name:'Corner'}:restart==='throw_in'?{id:67,name:'Throw-in'}:null,
     cross:a.x>65&&Math.abs(a.y-40)>20&&b.x>85&&Math.abs(b.y-40)<20,
     cut_back:a.x>100&&b.x<a.x-8&&Math.abs(b.y-40)<15,switch:Math.abs(b.y-a.y)>40,backheel:false,deflected:false,aerial_won:false};
    pass.body_part.name=pass.body_part.id===38?'Left Foot':'Right Foot';
    if(restart==='throw_in')pass.body_part={id:70,name:'Other'};
    if(pass.pass_type){const patterns={61:[2,'From Corner'],62:[3,'From Free Kick'],63:[7,'From Goal Kick'],65:[9,'From Kick Off'],67:[4,'From Throw In']};[e.play_pattern_id,e.play_pattern_name]=patterns[pass.pass_type.id];}
    add('event_passes',pass);lastPass={e,pass,arrival,recipient};
    const headed=completed&&isLast&&wantsShot&&random()<.3;
    const high=headed||turnover==='aerial'||restart==='corner'||(!restart&&random()<.12),low=!high&&(restart==='throw_in'||!restart&&random()<.12);
    pass.height=high?{id:3,name:'High Pass'}:low?{id:2,name:'Low Pass'}:{id:1,name:'Ground Pass'};
    const received=!completed&&contested&&['tackle','miscontrol'].includes(turnover);
    if(received){pass.recipient_player_id=pid(teams[side],recipient);pass.outcome=null;onside(p,side,kick,recipient,owner);}
    flight(p,kick,arrival,origin,end,headed||turnover==='aerial'?1.6:0,true,high?2.5:low?.5:0);
    lastPass.headed=headed;
    if(completed||received){
     const receipt=event(p,arrival,side,recipient,42,side,{'ball_receipt':{}},0);
     add('event_relations',{event_id:e.event_id,related_event_id:receipt.event_id,match_id:match});
    }
    t=arrival;restart=null;
    if(!completed){
     if(!contested||turnover==='interception')event(p,t,1-side,winner,10,side,{interception:{outcome:{id:16,name:'Success In Play'}}});
     else if(turnover==='aerial'){
      const lose=event(p,t,side,recipient,4,side,{duel:{type:{id:10,name:'Aerial Lost'}}});
      let target=2+Math.floor(random()*10);if(target===winner)target=target===11?8:target+1;
      const out=random()<.3;
      const landing=t+Math.max(2,Math.ceil(distance(end,point(p,1-side,target,t+3))/15)),dest=out?{x:end.x,y:end.y<34?0:68}:anchor(p,1-side,target,landing),n=normalized(p,1-side,dest);
      const clear=event(p,t,1-side,winner,9,side,{clearance:{body_part:{id:37,name:'Head'},aerial_won:true,end_location:[n.x,n.y] }},landing-t,{arrival_ms:landing*1000});
      add('event_relations',{event_id:lose.event_id,related_event_id:clear.event_id,match_id:match});
      flight(p,t,landing,{...end,z:1.6},dest,0,true,1);t=landing;winner=target;
      if(out){
       const resume=t+12,thrower=dest.y<34?2:5,spot={x:dest.x,y:dest.y===0?.2:67.8};
       anchor(p,side,thrower,resume,spot);flight(p,t,resume,dest,spot,0,false);t=resume;winner=thrower;restart='throw_in';
      }
     }else if(turnover==='fifty'){
      const win=event(p,t,1-side,winner,33,side,{'50_50':{outcome:{id:3,name:'Success To Team'}}});
      const lose=event(p,t,side,recipient,33,side,{'50_50':{outcome:{id:1,name:'Lost'}}});
      add('event_relations',{event_id:win.event_id,related_event_id:lose.event_id,match_id:match});
     }else if(turnover==='miscontrol'){
      event(p,t,side,recipient,38,side,{miscontrol:{aerial_won:false}});
     }else{
      const lose=event(p,t,side,recipient,14,side,{dribble:{outcome:{id:9,name:'Incomplete'},nutmeg:false,overrun:false}});
      const dispossessed=event(p,t,side,recipient,3,side);
      add('event_relations',{event_id:lose.event_id,related_event_id:dispossessed.event_id,match_id:match});
      event(p,t,1-side,winner,4,side,{duel:{type:{id:11,name:'Tackle'},outcome:{id:4,name:'Won'}}});
      // Reserve this serial for stable IDs, but do not label the carrier as
      // attempting a tackle: their losing perspective is Dispossessed above.
      event(p,t,side,recipient,4,side,{duel:{type:{id:11,name:'Tackle'},outcome:{id:13,name:'Lost In Play'}}})._omit=true;
     }
     if(received){const next=anchor(p,1-side,winner,t+1);flight(p,t,t+1,end,next);t++;}
     previousSide=side;side=restart==='throw_in'?side:1-side;owner=winner;afterTurnover=restart===null;finished=true;break;
    }
    owner=recipient;chainComplete=isLast;
   }
   if(finished)continue;
   if(!lastPass||!chainComplete||t>HALF_SECONDS-20){owned(p,side,owner,t,HALF_SECONDS);t=HALF_SECONDS;break;}
   // Completed final pass feeds the same player who shoots, after reception.
   const shotAt=lastPass.headed?t:t+2+Math.floor(random()*3);
   owned(p,side,owner,t,shotAt);
   const origin=anchor(p,side,owner,shotAt),att=toAttack(p,side,origin),d=Math.hypot(105-att.x,34-att.y);
   const aperture=Math.abs(Math.atan2(37.66-att.y,105-att.x)-Math.atan2(30.34-att.y,105-att.x));
   const xg=clamp(.36*Math.exp(-d/24)*clamp(aperture/.5,.25,1.5),.01,.65),roll=random();
   const outcome=!(tables.event_shots?.length)?96:roll<xg?97:roll<xg+(1-xg)*.36?100:roll<xg+(1-xg)*.62?96:98;
   let endAtt={x:105,y:34+(random()-.5)*5.6},z=.25+random()*1.4,contact=shotAt+2,blocker=null;
   if(outcome===98)endAtt.y=34+(random()<.5?-1:1)*(4.6+random()*4);
   if(outcome===100){endAtt.x=103.2;anchor(p,1-side,1,contact,fromAttack(p,side,endAtt));}
   if(outcome===96){
    const u=clamp(3/Math.max(d,1),.07,.5);endAtt={x:att.x+(105-att.x)*u,y:att.y+(34-att.y)*u};contact=shotAt+1;z=.2;
    blocker=nearest(p,1-side,contact,fromAttack(p,side,endAtt));
    anchor(p,1-side,blocker,contact,fromAttack(p,side,endAtt));
   }
   const end=fromAttack(p,side,endAtt),e=event(p,shotAt,side,owner,16,side,{},contact-shotAt,{arrival_ms:contact*1000,xg_model:'toy-distance-angle-v2'});
   const a=normalized(p,side,end);
   const key=lastPass.pass.recipient_player_id===e.player_id?lastPass:null;
   if(key){key.pass.shot_assist=true;key.pass.goal_assist=outcome===97;add('event_relations',{event_id:key.e.event_id,related_event_id:e.event_id,match_id:match});}
   add('event_shots',{event_id:e.event_id,event_type_id:16,match_id:match,team_id:teams[side],statsbomb_xg:xg,key_pass_id:key?.e.event_id??null,
    end_x:a.x,end_y:a.y,end_z:z,shot_type:{id:87,name:'Open Play'},outcome:{id:outcome,name:outcomeNames[outcome]},technique:{id:93,name:'Normal'},
    body_part:lastPass.headed?{id:37,name:'Head'}:random()<.3?{id:38,name:'Left Foot'}:{id:40,name:'Right Foot'},first_time:lastPass.headed,open_goal:false,
    follows_dribble:false,aerial_won:false,deflected:false,_p:p,_s:side,_t:shotAt,_end:contact});
   flight(p,shotAt,contact,{...origin,z:lastPass.headed?1.6:0},end,z);
   if(outcome===97)goals[side]++;
   const oldSide=side;previousSide=side;side=1-side;afterTurnover=false;
   if(outcome===97||outcome===98){
    owner=outcome===97?10:1;restart=outcome===97?'kickoff':'goal_kick';
    const resume=Math.min(HALF_SECONDS,contact+18+Math.floor(random()*10));
    const target=restart==='kickoff'?{x:52.5,y:34}:point(p,side,owner,resume);
    anchor(p,side,owner,resume,target);
    flight(p,contact,resume,{...end,z},target,0,false);t=resume;
   }else if(outcome===96&&random()<.3){
    tables.event_shots.at(-1).deflected=true;
    const block=event(p,contact,side,blocker,6,oldSide,{block:{offensive:false,deflection:true,save_block:false}});
    add('event_relations',{event_id:e.event_id,related_event_id:block.event_id,match_id:match});
    const outAt=contact+Math.max(2,Math.ceil(distance(end,fromAttack(p,oldSide,{x:105,y:att.y<34?5:63}))/20));
    const out=fromAttack(p,oldSide,{x:105,y:att.y<34?5:63});flight(p,contact,outAt,{...end,z},out,0,true);
    side=oldSide;owner=att.y<34?9:11;restart='corner';const resume=outAt+20;
    const corner=fromAttack(p,side,{x:104.8,y:att.y<34?.2:67.8});anchor(p,side,owner,resume,corner);
    flight(p,outAt,resume,out,corner,0,false);t=resume;
   }else{
    owner=outcome===100?1:blocker;
    const pt=anchor(p,side,owner,contact+1);
    flight(p,contact,contact+1,{...end,z},pt,0,true);t=contact+1;
    if(outcome===100){
     const save=event(p,contact,side,1,23,oldSide,{goalkeeper:{type:{id:33,name:'Shot Saved'}}});
     save.possession=e.possession;
     add('event_relations',{event_id:e.event_id,related_event_id:save.event_id,match_id:match});
    }else{
     const block=event(p,contact,side,blocker,6,oldSide,{block:{offensive:false,deflection:false,save_block:false}});
     add('event_relations',{event_id:e.event_id,related_event_id:block.event_id,match_id:match});
    }
   }
  }
  if(t<HALF_SECONDS)owned(p,side,owner,t,HALF_SECONDS);
  event(p,HALF_SECONDS,null,null,34,side);
 }
 // Derive carries only from live controlled segments; split at intervening
 // dribbles/pressures so a carry never claims an airborne pass or dead ball.
 for(const seg of segments.filter(s=>s.owner&&s.live&&s.b>s.a)){
  const cuts=[seg.a,...actions.filter(e=>e.period===seg.p&&e._t>seg.a&&e._t<seg.b).map(e=>e._t),seg.b].sort((a,b)=>a-b);
  for(let i=1;i<cuts.length;i++){
   const a=cuts[i-1],b=cuts[i],start=point(seg.p,seg.owner.s,seg.owner.slot,a),end=point(seg.p,seg.owner.s,seg.owner.slot,b);
   if(b<=a||distance(start,end)<1||actions.some(e=>e.type_id===14&&e.period===seg.p&&e._s===seg.owner.s&&e._slot===seg.owner.slot&&e.duration>0&&e._t<b&&e._t+e.duration>a))continue;
   const n=normalized(seg.p,seg.owner.s,end),e=event(seg.p,a,seg.owner.s,seg.owner.slot,43,seg.possSide,{carry:{end_location:[n.x,n.y]}},b-a);
   e.possession=seg.possession;
  }
 }
 // Changes are scheduled during actual dead-ball windows. The first tracking
 // sample AFTER the substitution contains the replacement in the vacated role.
 const substitutions=[];
 for(let s=0;s<2;s++)for(let n=0;n<3;n++){
  const threshold=700+n*550;
  const window=segments.find(x=>x.p===2&&!x.live&&x.b-x.a>=6&&x.a>=threshold&&!substitutions.some(q=>q.s===s&&Math.abs(q.t-(x.a+2))<8));
  if(!window)throw new Error('No legal dead-ball substitution window');
  const t=window.a+2,slot=[6,9,11][n],replacement=12+n;
  const e=event(2,t,s,slot,19,s,{substitution:{replacement:{id:pid(teams[s],replacement),name:`Synthetic Player ${teams[s]}-${replacement}`},outcome:{id:103,name:'Tactical'}}});
  e.possession=null;e.possession_team_id=null;
  substitutions.push({s,slot,replacement,t,at:t+1,event:e});
 }
 const identity=(p,s,slot,t)=>{const q=substitutions.find(q=>p===2&&q.s===s&&q.slot===slot&&t>=q.at);return pid(teams[s],q?q.replacement:slot);};
 const minuteClock=t=>`${String(Math.floor(t/60)).padStart(2,'0')}:${String(t%60).padStart(2,'0')}`;
 for(const q of substitutions){
  const outgoing=tables.lineup_positions.find(r=>r.player_id===pid(teams[q.s],q.slot));
  outgoing.to_time=minuteClock(2700+q.at);outgoing.end_reason='Substitution';
  add('lineup_positions',{...outgoing,player_id:pid(teams[q.s],q.replacement),from_time:minuteClock(2700+q.at),to_time:'90:00',from_period:2,to_period:2,start_reason:'Substitution',end_reason:'Final Whistle'});
  const e=event(2,q.at,q.s,null,36,q.s);e.possession=null;e.possession_team_id=null;
  add('event_tactics',{event_id:e.event_id,event_type_id:36,match_id:match,team_id:teams[q.s],formation:433});
  for(let slot=1;slot<=11;slot++)add('tactical_lineups',{event_id:e.event_id,match_id:match,team_id:teams[q.s],player_id:identity(2,q.s,slot,q.at),position_id:ids[slot-1],position_name:names[slot-1],jersey_number:identity(2,q.s,slot,q.at)%100});
 }
 // A failed tackle belongs to a challenger who tried and was beaten, not to
 // the dispossessed carrier. A deterministic subset of escapes has that duel.
 for(const past of [...actions].filter(e=>e.type_id===39&&e._t%4===0)){
  const attempt=event(past.period,past._t,past._s,past._slot,4,past.possession_team_id===teams[0]?0:1,{duel:{type:{id:11,name:'Tackle'},outcome:{id:13,name:'Lost In Play'}}},past.duration);
  attempt.possession=past.possession;
  const win=tables.event_relations.find(r=>r.related_event_id===past.event_id);
  add('event_relations',{event_id:attempt.event_id,related_event_id:win.event_id,match_id:match});
 }
 for(let i=actions.length-1;i>=0;i--)if(actions[i]._omit)actions.splice(i,1);
 for(const e of actions)if(e._slot!==null)e.player_id=identity(e.period,e._s,e._slot,e._t);
 for(const pass of tables.event_passes){const e=actions.find(e=>e.event_id===pass.event_id);if(pass.recipient_player_id)pass.recipient_player_id=identity(e.period,e._s,pass.recipient_player_id%100,e._t+e.duration);}
 for(const c of tables.lineup_cards??[]){const [m,s]=c.time.split(':').map(Number);c.player_id=identity(c.period,teams.indexOf(c.team_id),c.player_id%100,m*60+s-(c.period-1)*2700);}
 // Convert exact contact anchors to the actual sampled paths once the whole
 // period is planned. All snapshots and action locations use these same paths.
 for(const e of actions){
  if(e._slot!==null){const loc=normalized(e.period,e._s,point(e.period,e._s,e._slot,e._t));e.location_x=loc.x;e.location_y=loc.y;}
 }
 actions.sort((a,b)=>a.period-b.period||a._t-b._t);
 const patterns=new Map(),passIndex=new Map(tables.event_passes.map(p=>[p.event_id,p]));
 for(const e of actions){
  if(e.possession===null)continue;
  const pass=passIndex.get(e.event_id);
  if(pass?.pass_type)patterns.set(e.possession,[e.play_pattern_id,e.play_pattern_name]);
  if(patterns.has(e.possession))[e.play_pattern_id,e.play_pattern_name]=patterns.get(e.possession);
 }
 actions.forEach((e,i)=>{
  e.event_index=i+1;
  // Do not expose planning helpers as extra fields in the stored source payload.
  e.raw_payload={...e.raw_payload,event:{id:e.event_id,index:e.event_index,period:e.period,timestamp:e.timestamp,type:{id:e.type_id,name:e.type_name},team:e.team_id,player:e.player_id,location:e.location_x===undefined?null:[e.location_x,e.location_y]}};
  add('event_tracking_links',{event_id:e.event_id,run_id:run,match_id:match,period:e.period,frame_index:e._t,alignment_method:'exact'});
  add('events',e);
 });
 for(const shot of tables.event_shots??[]){
  const {event_id,_p:p,_s:s,_t:t}=shot;
  add('frames_360',{event_id,match_id:match,visible_area:[0,0,120,0,120,80,0,80],raw_payload:payload({coverage:'synthetic full-pitch; not camera coverage'})});
  for(let other=0;other<2;other++)for(let slot=1;slot<=11;slot++){
   const a=normalized(p,s,point(p,other,slot,t)),idx=other*11+slot-1;
   add('shot_freeze_players',{event_id,match_id:match,shot_team_id:teams[s],frame_player_index:idx,player_id:identity(p,other,slot,t),position_id:ids[slot-1],position_name:names[slot-1],location_x:a.x,location_y:a.y,teammate:other===s});
   add('frame_360_players',{event_id,frame_player_index:idx,location_x:a.x,location_y:a.y,teammate:other===s,actor:identity(p,other,slot,t)===tables.events.find(e=>e.event_id===event_id).player_id,keeper:slot===1});
  }
 }
 add('matches',{match_id:match,competition_id:900,season_id:2026,match_date:`2026-10-${String(1+Math.floor(mi/2)*4).padStart(2,'0')}T00:00:00Z`,kick_off:`1970-01-01T${mi%2?'20':'18'}:00:00Z`,
  home_score:goals[0],away_score:goals[1],match_week:Math.floor(mi/2)+1,competition_stage_id:1,competition_stage_name:'Synthetic Friendly Series',stadium_id:teams[0],referee_id:mi%2+1,
  match_status:'available',match_status_360:'available',data_version:'synthetic-3.0',raw_payload:payload({xg_model:'toy-distance-angle-v2',scenario:'training friendlies; three substitutions per team; no added time',source_coordinates:'team-oriented affine 120x80',tracking_coordinates:'fixed pitch metres'})});
 add('tracking_runs',{run_id:run,match_id:match,label:`Audited synthetic match ${mi+1}`,seed:SEED,generator_name:'inside-game-demo',generator_version:VERSION,
  config:payload({sampling_hz:1,half_seconds:HALF_SECONDS,no_substitutions:false,substitution_tracking:'role handoff on first second after event; off-pitch walking not simulated',coordinates:'fixed x right, y down; origin top-left',pitch_goal_width_m:7.32,pitch_goal_height_m:2.44,
   motion:'smooth contact-constrained paths',event_coordinate_transform:'affine 120x80 from fixed 105x68, rotated to attacking team',no_added_time:true}),sample_rate_hz:1,pitch_length_m:105,pitch_width_m:68,is_synthetic:true,max_event_offset_ms:0});
 for(let p=1;p<=2;p++){
  add('tracking_periods',{run_id:run,match_id:match,period:p,duration_ms:HALF_SECONDS*1000,home_attacks_positive_x:p===1});
  const ball=Array(HALF_SECONDS+1);
  for(const seg of segments.filter(s=>s.p===p))for(let t=seg.a;t<=seg.b;t++){
   let v;
   if(seg.owner)v={...point(p,seg.owner.s,seg.owner.slot,t),z:0};
   else{const u=seg.b===seg.a?1:(t-seg.a)/(seg.b-seg.a);v={x:seg.start.x*(1-u)+seg.end.x*u,y:seg.start.y*(1-u)+seg.end.y*u,z:seg.start.z*(1-u)+seg.end.z*u+4*(seg.arc??0)*u*(1-u)};}
   ball[t]={...v,live:seg.live};
  }
  for(let t=0;t<=HALF_SECONDS;t++){
   if(!ball[t])throw new Error(`Missing ball sample ${match}/${p}/${t}`);
   const key={run_id:run,match_id:match,period:p,frame_index:t},b=ball[t];
   add('tracking_frames',{...key,period_time_ms:t*1000,ball_in_play:b.live&&t<HALF_SECONDS});
   add('tracking_ball_positions',{...key,x_m:b.x,y_m:b.y,z_m:b.z,position_status:'available',sample_method:'generated',confidence:1});
   for(let side=0;side<2;side++)for(let slot=1;slot<=11;slot++){
    const a=point(p,side,slot,t);
    add('tracking_player_positions',{...key,team_id:teams[side],player_id:identity(p,side,slot,t),x_m:a.x,y_m:a.y,is_on_pitch:true,on_pitch_slot:slot,position_status:'available',sample_method:'generated',confidence:1});
   }
  }
 }
 return {match,run,tables,debugAnchors:anchors};
}



