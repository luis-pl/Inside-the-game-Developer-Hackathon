"""Templates de página autocontenida. CSS y JS se empaquetan, nunca se generan con LLM."""

CSS = """
.report.entity_comparison,.report.match_overview,.report.player_dossier,.report.tactical_episode{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 2rem}.report .evidence-footer{grid-column:1/-1}.report.match_overview .insight:first-child,.report.player_dossier .insight:first-child,.report.tactical_episode .insight:first-child{grid-column:1/-1}.block-answer{font-weight:600;font-size:1.05rem;margin:.4rem 0 0;max-width:75ch}.team-breakdown caption{text-align:left;font-size:.8rem;color:var(--muted);padding-bottom:.3rem}.team-breakdown td.team-name{font-weight:600;white-space:nowrap}.team-breakdown .legend-key{margin-right:.5em;vertical-align:middle}.event-chain{display:flex;gap:.5rem;flex-wrap:wrap;list-style-position:inside;padding:0}.event-chain li{border-bottom:2px solid #718274;padding:.5rem;font-size:.82rem}.empty-note{color:#924019}@media(max-width:760px){.report.entity_comparison,.report.match_overview,.report.player_dossier,.report.tactical_episode{display:block}}

:root{font-family:"Segoe UI",sans-serif;color:#20372b;background:#f5f5ee;--ink:#20372b;--line:#ced7c8;--muted:#4c6354;--accent:#185540;--amber:#9b431e;font-synthesis:none;color-scheme:light}
*{box-sizing:border-box}body{margin:0;font-size:16px;line-height:1.6}::selection{background:#b3e1cb;color:#142c20}a{color:var(--accent);text-underline-offset:.2em}button,select,input{font:inherit;accent-color:var(--accent)}button,select{border:1px solid #839886;background:#fff;color:var(--ink);padding:.55em .85em;border-radius:6px}button{cursor:pointer}button:hover{background:#e6eddf}a:focus-visible,button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #994600;outline-offset:3px}button:disabled{opacity:.5;cursor:default}header,main,footer{max-width:1160px;margin:auto;padding:2rem 3rem}header{border-bottom:1px solid var(--line)}header h1{font-size:clamp(2rem,4vw,3.3rem);line-height:1.12;font-weight:650;letter-spacing:-.03em;margin:.5rem 0 1rem;max-width:23ch}h2{font-size:clamp(1.4rem,3vw,2rem);line-height:1.2;font-weight:600;letter-spacing:-.02em;margin:0}.intro{max-width:72ch;color:var(--muted)}.toolbar{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;margin-top:1.5rem}.toolbar label{display:flex;align-items:center;gap:.7rem}.toolbar select{max-width:100%}.insight{padding:2.8rem 0;border-bottom:1px solid var(--line);break-inside:avoid}.section-heading{display:flex;justify-content:space-between;gap:1rem;align-items:baseline}.status{font-size:.82rem;white-space:nowrap;color:var(--accent)}.status.partial,.status.unavailable,.status.incompatible,.status.error{color:#924019}.metrics{display:flex;flex-wrap:wrap;gap:1.1rem 2.5rem;margin:1.7rem 0}.reading{min-width:130px;max-width:270px}dt{font-size:.8rem;color:var(--muted);overflow-wrap:anywhere}dd{font-variant-numeric:tabular-nums;margin:0;font-size:1.35rem;font-weight:600}figure{margin:1.7rem 0}figure svg{display:block;width:100%;max-height:570px;background:#eef1e6}.field-lines{fill:none;stroke:#708e70;stroke-width:.3}.pitch .vector{stroke:#285f4c;stroke-width:.3;opacity:.7;fill:none}.series text{font:12px "Segoe UI",sans-serif;fill:var(--muted)}figcaption,.muted,.method,.evidence-links{font-size:.82rem;color:var(--muted)}figcaption{margin-top:.5rem}.method{overflow-wrap:anywhere}.source-notes,.data-table{margin:1.2rem 0}summary{cursor:pointer;color:var(--accent);padding:.4rem 0}li{max-width:75ch;margin:.45rem 0}.table-scroll{overflow:auto;max-height:430px}table{border-collapse:collapse;width:100%;font-size:.82rem;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:.6rem .7rem;border-bottom:1px solid var(--line);vertical-align:top;max-width:340px;overflow-wrap:anywhere}th{position:sticky;top:0;background:#e9eddf}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.8rem;max-height:500px;overflow:auto;background:#e9eddf;padding:1rem}.evidence-footer{padding-top:3rem}.evidence-footer h2{margin-bottom:1.5rem}.replay-controls{display:flex;gap:1rem;align-items:center;flex-wrap:wrap}.replay-controls label{display:flex;align-items:center;gap:.8rem;flex:1}.seek{width:100%;min-width:100px}.replay output{font-variant-numeric:tabular-nums}.empty-note{max-width:70ch;color:#924019}.report-meta{color:var(--muted);font-size:.85rem}footer{font-size:.85rem;border-top:1px solid var(--line);color:var(--muted)}[hidden]{display:none!important}@media(max-width:640px){header,main,footer{padding:1.4rem}.section-heading{display:block}.section-heading .status{display:inline-block;margin-top:.5rem}.toolbar label{display:block;width:100%}.toolbar select{width:100%}.metrics{gap:1rem}.reading{min-width:120px}.insight{padding:2rem 0}}@media print{body{background:#fff}.toolbar,.replay-controls{display:none}.insight[hidden]{display:block!important}header,main,footer{max-width:none;padding:1rem}.insight{break-inside:avoid}figure svg{max-height:350px}.source-notes{display:block}}
"""

CSS += """
.analyst-note{grid-column:1/-1;padding:2rem 0;border-bottom:1px solid var(--line)}.analyst-copy{white-space:pre-wrap;max-width:72ch;line-height:1.75}
.block-question{font-size:.82rem;color:var(--muted);margin:.6rem 0 1.3rem;max-width:70ch}.possession-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin:1.5rem 0}.possession-card{border-top:1px solid var(--line);padding:.8rem 0}.possession-card strong{font-size:.82rem;color:var(--team)}.possession-card p{font-size:.8rem;margin:.4rem 0}.metric-details .metrics{padding:.5rem 0}/* Templates arrange organisms; the charts retain their own parametric data. */
:root{--ink:#192f2c;--muted:#51645e;--line:#d8dfd7;background:#f6f6f0}
header,main,footer{max-width:1380px;padding-left:3.5rem;padding-right:3.5rem}
header{padding-top:3rem;padding-bottom:2.5rem}header>p:first-child{text-transform:none;letter-spacing:normal;font-size:.85rem;font-weight:700;color:#527568}header h1{font-weight:700;max-width:28ch;font-size:clamp(2.2rem,4.5vw,4.2rem)}
.report.match_overview{gap:0 3rem}.insight{position:relative;padding:2.4rem 0 2rem;min-width:0}.insight[data-span=full]{grid-column:1/-1}.insight[data-span=half]{grid-column:auto!important}.section-heading{align-items:center}h2{font-size:clamp(1.25rem,2vw,1.65rem);max-width:28ch}.status{font-size:.8rem;padding:.22rem .6rem;background:#e8eee6;border-radius:20px}.status.partial,.status.unavailable{background:#f6e7da}
.metrics{gap:1rem 2rem;margin:1.3rem 0 1.5rem}.reading{min-width:85px;max-width:190px}dt{font-size:.8rem;line-height:1.4}dd{font-size:1.7rem;letter-spacing:-.035em;font-weight:650}
.match-banner{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:2rem;padding:1.8rem 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-top:2rem}.match-banner strong{display:block;font-size:clamp(1.1rem,2.5vw,1.8rem);line-height:1.25;color:var(--team)}.match-banner>div:last-child{text-align:right}.eyebrow{display:block;font-size:.75rem;margin-bottom:.55rem;color:var(--muted)}.score{margin:0;font-size:clamp(2.4rem,5vw,4rem);font-weight:700;line-height:1;letter-spacing:-.04em;white-space:nowrap}.score span{color:#8d9c94;font-size:.6em;margin:0 .6rem}
figure{margin:1.4rem 0 1rem}figure svg{background:#edf1e9;border-radius:4px}.pitch{background:#eaf0e8!important}.field-lines{stroke:#78917f;stroke-opacity:.65;stroke-width:.24}.jersey{font:600 1.8px 'Segoe UI',sans-serif;fill:#fff;pointer-events:none}.chart-legend{list-style:none;display:flex;gap:.5rem 1.2rem;flex-wrap:wrap;padding:0;margin:.7rem 0}.chart-legend li{display:flex;align-items:center;gap:.4rem;font-size:.75rem;line-height:1.35;margin:0}.legend-key{display:inline-block;width:.65rem;height:.65rem;border-radius:50%;flex:none}.palette-note{font-size:.75rem;color:var(--muted)}.heat-scale{display:flex;align-items:center;gap:.7rem;font-size:.75rem;margin:.5rem 0}.heat-ramp{display:inline-block;max-width:180px;flex:1;height:8px;background:linear-gradient(to right,#edf1e9,var(--team));border-radius:3px}figcaption{font-size:.8rem;line-height:1.5;max-width:85ch}.series text{font-size:12px}.method,.evidence-links{font-size:.75rem;margin:.45rem 0}.source-notes,.data-table{margin:.6rem 0}summary{font-size:.78rem}.toolbar{gap:.65rem}.toolbar button,.toolbar select{font-size:.82rem}.replay-controls{font-size:.8rem}.source-notes ul{padding-left:1.2rem;font-size:.8rem}
@media(max-width:760px){header,main,footer{padding-left:1.25rem;padding-right:1.25rem}.match-banner{gap:.8rem;padding:1.4rem 0}.score span{margin:0 .3rem}.report .insight{grid-column:auto}.metrics{gap:.8rem 1.2rem}.reading{min-width:80px}.section-heading{align-items:flex-start}.chart-legend li{font-size:.75rem}header{padding-top:1.8rem}.toolbar{gap:.6rem}.toolbar button{flex:1}.toolbar label{width:100%}figure svg{max-height:none}}
@media print{.report.match_overview{display:block}.match-banner{break-inside:avoid}.insight{break-inside:avoid}}
"""

JS = """
"use strict";
// Inicializa una página de informe dentro de `root` (el documento o una zona de
// una aplicación que inserta las mismas piezas de report_parts).
function initInsightsReport(root,payload){
root.querySelector("#block-filter")?.addEventListener("change",event=>{for(const section of root.querySelectorAll("section.insight"))section.hidden=event.target.value!=="all"&&section.id!==event.target.value;});
root.querySelector("#print-report")?.addEventListener("click",()=>window.print());
root.querySelector("#download-data")?.addEventListener("click",()=>{const blob=new Blob([JSON.stringify(payload,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download="insight-evidence.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
const ns="http://www.w3.org/2000/svg";
for(const holder of root.querySelectorAll(".replay")){
 const block=payload.blocks.find(x=>x.id===holder.dataset.block),frames=block.frames;
 const layer=holder.querySelector(".replay-points"),seek=holder.querySelector(".seek"),button=holder.querySelector(".play"),output=holder.querySelector("output");
 let index=0,playing=false,baseWall=0,baseGame=0;
 const dot=(x,y,r,fill,label)=>{const node=document.createElementNS(ns,"circle");node.setAttribute("cx",x);node.setAttribute("cy",y);node.setAttribute("r",r);node.setAttribute("fill",fill);const title=document.createElementNS(ns,"title");title.textContent=label;node.appendChild(title);layer.appendChild(node);};
 const draw=()=>{const frame=frames[index];layer.replaceChildren();const palette=["#2463bc","#bf402e","#7752ac","#13796d","#a05c13","#965475"];for(const p of frame.players){const identity=block.teams[String(p.team_id)]||{color:palette[(p.team_id-1)%palette.length]},player=block.players[String(p.player_id)]||{};dot(p.x_m,p.y_m,1.45,identity.color,player.name||String(p.player_id));if(block.visual.show_labels){const label=document.createElementNS(ns,"text");label.setAttribute("x",p.x_m);label.setAttribute("y",p.y_m+.55);label.setAttribute("text-anchor","middle");label.setAttribute("class","jersey");label.textContent=String(player.number??p.player_id);layer.appendChild(label);}}if(frame.ball)dot(frame.ball.x_m,frame.ball.y_m,.65,"#17241c","Balón");seek.value=String(index);output.textContent="P"+frame.period+" · "+(frame.period_time_ms/1000).toFixed(1)+" s · "+frame.players.length+" jugadores"+(frame.ball?"":" · balón sin posición");};
 const stop=()=>{playing=false;button.textContent="Reproducir";};
 const tick=now=>{if(!playing)return;const target=baseGame+now-baseWall;while(index<frames.length-1&&frames[index+1].period_time_ms<=target)index++;draw();if(index===frames.length-1)stop();else requestAnimationFrame(tick);};
 button.addEventListener("click",()=>{if(playing){stop();return;}if(index===frames.length-1)index=0;playing=true;button.textContent="Pausar";baseGame=frames[index].period_time_ms;baseWall=performance.now();requestAnimationFrame(tick);});
 seek.addEventListener("input",()=>{stop();index=Number(seek.value);draw();});draw();
}
}
// Los enlaces «Evidencia» apuntan a consultas plegadas: se abren al llegar a ellas.
function openEvidence(id){const target=document.getElementById(id);if(!target)return false;for(let n=target;n;n=n.parentElement)if(n.tagName==="DETAILS")n.open=true;target.scrollIntoView({block:"center"});return true;}
document.addEventListener("click",event=>{const link=event.target.closest?.('a[href^="#evidence-"]');if(link&&openEvidence(link.getAttribute("href").slice(1)))event.preventDefault();});
addEventListener("hashchange",()=>{if(location.hash.startsWith("#evidence-"))openEvidence(location.hash.slice(1));});
const reportData=document.getElementById("report-data");
if(reportData)initInsightsReport(document,JSON.parse(reportData.textContent));
"""


# --- Template «espacio de trabajo»: la aplicación web que compone informes ---
# Reutiliza los tokens y la base de CSS (botones, campos, foco, header/main del
# informe); sólo añade la distribución consola + lienzo y sus estados.
WORKSPACE_CSS = """
[hidden]{display:none!important}
body.workspace{min-height:100vh;display:flex;flex-direction:column;font-size:15px;line-height:1.5}
@media(min-width:961px){body.workspace{height:100vh;overflow:hidden}}
.workspace h2,.workspace h3{max-width:none}
.masthead{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:.9rem 1.5rem;border-bottom:1px solid var(--line);background:#fff}
.brand h1{font-size:1.25rem;font-weight:700;letter-spacing:-.01em;margin:0}.brand p{margin:.1rem 0 0;color:var(--muted);font-size:.875rem;max-width:62ch}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600;white-space:nowrap}button.primary:hover:not(:disabled){background:#10402f}
button.quiet{white-space:nowrap}button.link{border:0;background:none;padding:0;color:var(--accent);text-decoration:underline;text-underline-offset:.2em}button.link:hover{background:none}
.desk{flex:1;display:grid;grid-template-columns:minmax(340px,420px) minmax(0,1fr);min-height:0}
.console{display:flex;flex-direction:column;min-height:0;border-right:1px solid var(--line)}
.thread-wrap{flex:1;overflow-y:auto;padding:1.25rem 1.25rem .5rem;min-height:0}
.thread{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.75rem}.thread>li{margin:0;max-width:none}
.welcome h2{font-size:1.4rem}.welcome p{margin:.35rem 0 .9rem;color:var(--muted)}.suggestions,.options{display:flex;flex-direction:column;gap:.5rem}.suggestions button,.options button{text-align:left}.options{margin-top:.6rem}
.msg{background:#fff;border:1px solid var(--line);border-radius:8px;padding:.75rem .9rem;font-size:.875rem}.msg p{margin:0}.msg p+p,.msg p+ul,.msg ul+p{margin-top:.4rem}
.msg.user{align-self:flex-end;max-width:88%;background:#e3eee5;border-color:transparent}.msg.hint{background:none;border-style:dashed;color:var(--muted)}
.msg.error{background:#fbe9e5;border-color:transparent;color:#8f2a1d}.msg.clarification{border-color:var(--accent)}.msg.pending{color:var(--muted)}
.answer-title{font-weight:600;font-size:.95rem}.msg .tag{margin:.4rem 0 .5rem}.pieces{margin:.25rem 0 0;padding-left:1.1rem}.pieces li,.missing li{margin:.1rem 0}
.note{color:var(--muted)}.missing{margin-top:.5rem;color:var(--muted)}.missing ul{margin:.4rem 0 0;padding-left:1.1rem}.view-report{margin-top:.6rem}.codes{font-size:.75rem;color:var(--muted)}
.tag{display:inline-block;font-size:.75rem;font-weight:600;border-radius:4px;padding:.1rem .5rem;background:#e3eee5;color:var(--accent)}.tag.synthetic{background:#f8e8dc;color:var(--amber)}
.hint{margin:0;font-size:.8rem;color:var(--muted)}
.spinner{display:inline-flex;align-items:center;gap:.6rem}.spinner::before{content:"";width:14px;height:14px;border-radius:50%;border:2px solid var(--line);border-top-color:var(--accent);animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.compose{border-top:1px solid var(--line);background:#fff;padding:.75rem 1.25rem 1rem}
.modes{display:inline-flex;gap:2px;padding:2px;margin-bottom:.75rem;border:1px solid var(--line);border-radius:8px;background:#f5f5ee}
.modes [role=tab]{border:0;background:none;padding:.35rem .9rem;color:var(--muted);border-radius:6px}.modes [role=tab][aria-selected=true]{background:#fff;color:var(--ink);font-weight:600;box-shadow:0 1px 3px rgba(32,55,43,.16)}
.compose textarea,.compose select,.compose input[type=number]{width:100%;font:inherit;color:var(--ink);background:#fff;border:1px solid #839886;border-radius:6px;padding:.5rem .65rem}.compose textarea{resize:vertical;min-height:64px}.compose textarea:disabled{background:#f5f5ee;color:var(--muted)}
.compose-row{display:flex;justify-content:space-between;align-items:center;gap:.75rem;margin-top:.5rem}
.pick{display:flex;flex-direction:column;gap:.75rem;max-height:46vh;overflow-y:auto;padding-right:2px}.pick>*{flex-shrink:0}
.field{display:flex;flex-direction:column;gap:.25rem;font-size:.8rem;color:var(--muted)}.field small{color:var(--muted)}.pair{display:grid;grid-template-columns:1fr 1fr;gap:.6rem}.inline-error{margin:0;font-size:.8rem;color:#8f2a1d}
.compose fieldset{margin:0;padding:0;border:0;min-width:0}.compose legend{font-size:.8rem;color:var(--muted);padding:0}
.kinds{border:1px solid var(--line)!important;border-radius:8px;overflow:hidden}.kinds legend{float:left;width:100%;padding:.5rem .75rem 0}
.kind{display:flex;gap:.6rem;align-items:flex-start;padding:.5rem .75rem;cursor:pointer}.kind+.kind{border-top:1px solid var(--line)}.kind:has(input:checked){background:#e3eee5}.kind input{margin-top:.3rem}.kind span{display:flex;flex-direction:column}.kind strong{font-weight:600;font-size:.875rem}.kind small{color:var(--muted);font-size:.8rem}
.recipes{display:grid;gap:2px;max-height:180px;overflow-y:auto;border:1px solid var(--line);border-radius:8px;padding:.4rem .6rem}.recipes label{display:flex;gap:.5rem;align-items:center;font-size:.875rem}.recipes label:has(input:disabled){color:#8a988e}.recipes-box legend span{font-variant-numeric:tabular-nums;color:var(--ink)}
.about{padding:.6rem 1.25rem .9rem;font-size:.8rem;color:var(--muted);border-top:1px solid var(--line)}.about p{margin:.4rem 0 0;max-width:62ch}
.canvas{display:flex;flex-direction:column;min-width:0;min-height:0;background:#fff}
.canvas-bar{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:.75rem 1.25rem;border-bottom:1px solid var(--line)}.canvas-title{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;min-width:0}.canvas-title h2{font-size:1rem;font-weight:600}.canvas-bar a{font-size:.875rem;white-space:nowrap}
.canvas-wrap{position:relative;flex:1;min-height:0;overflow-y:auto;background:#f6f6f0}
.canvas-body header,.canvas-body main,.canvas-body footer{max-width:1100px;padding-left:2.5rem;padding-right:2.5rem}.canvas-body header{padding-top:2rem}.canvas-body header h1{font-size:clamp(1.6rem,2.6vw,2.6rem)}
.canvas-empty{max-width:560px;margin:0 auto;padding:4.5rem 1.5rem;color:var(--muted)}.canvas-empty h3{font-size:1.25rem;color:var(--ink);margin:0 0 .9rem}.canvas-empty ul{margin:0;padding-left:1.1rem;line-height:1.7}.canvas-empty li{margin:0}.canvas-empty strong{color:var(--ink)}
.canvas-loading{position:absolute;inset:0;z-index:1;display:flex;justify-content:center;align-items:flex-start;padding-top:4.5rem;background:rgba(246,246,240,.85);color:var(--muted)}
.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media(prefers-reduced-motion:reduce){.spinner::before{animation:none}}
@media(max-width:960px){.masthead{padding:.75rem 1rem;align-items:flex-start}.desk{display:block}.console{border-right:0;border-bottom:1px solid var(--line)}.thread-wrap{padding:1rem 1rem .5rem;max-height:55vh}.compose,.about{padding-left:1rem;padding-right:1rem}.pick{max-height:none;overflow:visible}.canvas{min-height:92vh}.canvas-wrap{overflow:visible}.canvas-body header,.canvas-body main,.canvas-body footer{padding-left:1.25rem;padding-right:1.25rem}}
@media(max-width:420px){.pair{grid-template-columns:1fr}.compose-row{flex-direction:column;align-items:stretch}.masthead{flex-direction:column}}
@media print{.masthead,.console,.canvas-bar{display:none}body.workspace{height:auto;overflow:visible}.desk{display:block}.canvas-wrap{overflow:visible}}
"""

WORKSPACE_JS = """
(()=>{
// Coloca los fragmentos que compone el servidor con los mismos átomos, moléculas
// y organismos; aquí no se construye HTML a partir de datos.
if(!document.body.classList.contains("workspace"))return;
const $=id=>document.getElementById(id);
const MAX=6,state={previous:null,busy:false};
const fragment=html=>{const t=document.createElement("template");t.innerHTML=html;return t.content;};
const plain=(cls,label)=>{const li=document.createElement("li");li.className="msg "+cls;li.textContent=label;return li;};
function add(node){$("welcome")?.remove();$("thread").append(node);const last=$("thread").lastElementChild;last.scrollIntoView({block:"end",behavior:"smooth"});return last;}
function showCanvas(data){
 $("canvas-body").replaceWith(fragment(data.canvas_html));
 const fresh=$("canvas-body"),payload=fresh.querySelector(".report-payload");
 if(payload)initInsightsReport(fresh,JSON.parse(payload.textContent));
 $("canvas-wrap").scrollTop=0;
 $("report-title").textContent=data.title||"Informe";
 $("report-tag").replaceChildren(fragment(data.source_html||""));
 const open=$("report-open");open.hidden=!data.report_url;if(data.report_url)open.href=data.report_url;
 if(data.report_id)history.replaceState(null,"","#informe="+data.report_id);
 if(matchMedia("(max-width: 960px)").matches)$("canvas").scrollIntoView({behavior:"smooth"});
}
function setBusy(busy){
 state.busy=busy;$("canvas-loading").hidden=!busy;
 for(const b of document.querySelectorAll("#ask-button,#intent-button,[data-question]"))b.disabled=busy||(b.id==="ask-button"&&$("question").disabled)||(b.id==="intent-button"&&!$("match"));
}
async function ask(request,label){
 if(state.busy)return;
 add(plain("user",label));
 const waiting=add(plain("pending","Preparando el informe…"));waiting.classList.add("spinner");
 const started=performance.now(),timer=setInterval(()=>{waiting.textContent="Preparando el informe · "+Math.round((performance.now()-started)/1000)+" s";},1000);
 setBusy(true);
 try{
  const response=await fetch("/api/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...request,previous:state.previous})});
  const data=await response.json().catch(()=>({}));
  waiting.remove();
  if(data.message_html)add(fragment(data.message_html));
  else add(plain("error","No se pudo preparar el informe. Inténtalo de nuevo."));
  if(response.ok){state.previous=data.next??state.previous;if(data.canvas_html)showCanvas(data);}
 }catch{waiting.remove();add(plain("error","No hay conexión con el servidor local. Comprueba que sigue en marcha."));}
 finally{clearInterval(timer);setBusy(false);}
}
function mode(name){for(const n of ["ask","pick"]){const on=n===name;$("tab-"+n).setAttribute("aria-selected",String(on));$("tab-"+n).tabIndex=on?0:-1;$("panel-"+n).hidden=!on;}}
const template=()=>document.querySelector("input[name=template]:checked").value;
function teams(){const select=$("team"),option=$("match")?.selectedOptions[0];select.replaceChildren(new Option("El local",""));for(const t of JSON.parse(option?.dataset.teams||"[]"))select.append(new Option(t.name,t.team_id));}
function fields(){$("minute-field").hidden=template()!=="tactical_episode";$("recipes-field").hidden=template()!=="custom_report";}
function count(){const n=document.querySelectorAll("#recipes input:checked").length;$("recipe-count").textContent=n+" de "+MAX;for(const i of document.querySelectorAll("#recipes input"))i.disabled=!i.checked&&n>=MAX;}
function intent(){
 const value={template_id:template(),match_id:Number($("match").value)};
 if($("team").value)value.team_id=Number($("team").value);
 if($("period").value)value.period=Number($("period").value);
 if(value.template_id==="tactical_episode"&&$("minute").value!==""){value.period=value.period||1;value.time_ms=Math.round(Number($("minute").value)*60000);}
 if(value.template_id==="custom_report")value.insight_ids=[...document.querySelectorAll("#recipes input:checked")].map(i=>i.value);
 return value;
}
function describe(){const kind=document.querySelector("input[name=template]:checked + span strong").textContent,team=$("team").value?" · "+$("team").selectedOptions[0].textContent:"";return kind+team+" · "+$("match").selectedOptions[0].textContent;}
$("tab-ask").addEventListener("click",()=>mode("ask"));$("tab-pick").addEventListener("click",()=>mode("pick"));
$("tab-ask").addEventListener("keydown",e=>{if(e.key==="ArrowRight"){mode("pick");$("tab-pick").focus();}});
$("tab-pick").addEventListener("keydown",e=>{if(e.key==="ArrowLeft"){mode("ask");$("tab-ask").focus();}});
$("ask-form").addEventListener("submit",e=>{e.preventDefault();const q=$("question").value.trim();if(!q||$("question").disabled)return;$("question").value="";ask({question:q},q);});
$("question").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();$("ask-form").requestSubmit();}});
$("intent-form").addEventListener("submit",e=>{e.preventDefault();if(!$("match"))return;const value=intent();if(value.template_id==="custom_report"&&!value.insight_ids.length){add(plain("error","Elige al menos una pieza."));return;}ask({intent:value},describe());});
$("match")?.addEventListener("change",teams);
for(const r of document.querySelectorAll("input[name=template]"))r.addEventListener("change",fields);
$("recipes").addEventListener("change",count);
document.addEventListener("click",e=>{
 const q=e.target.closest("[data-question]");if(q&&!q.disabled){ask({question:q.dataset.question},q.dataset.question);return;}
 if(e.target.closest(".view-report"))$("canvas").scrollIntoView({behavior:"smooth"});
});
$("reset").addEventListener("click",()=>{state.previous=null;$("thread").replaceChildren(plain("hint","Nueva conversación. ¿Qué quieres ver?"));});
async function restore(){
 const id=new URLSearchParams(location.hash.slice(1)).get("informe");
 if(!id||!/^[0-9a-f]{32}$/.test(id))return;
 const response=await fetch("/api/reports/"+id).catch(()=>null);
 if(response?.ok)showCanvas(await response.json());else history.replaceState(null,"",location.pathname);
}
teams();fields();count();setBusy(false);restore();
})();
"""
