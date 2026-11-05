/* Deterministic natural-language command bridge for the static chat UI.
 * Ordinary questions remain on Mnemos Knowledge; explicit calculation commands
 * are dispatched only to browser engines and never to a remote application API.
 */
(() => {
"use strict";
const helpText=[
 "Perintah mesin browser yang dikenali:",
 "• turunkan: x^2 terhadap x",
 "• integralkan: x^2 terhadap x",
 "• sederhanakan: x + 0",
 "• evaluasi: x^2; x=3",
 "• isolasi x dari 2*x+3=11",
 "• benchmark semua",
 "• cari dataset: rocket propulsion",
 "• siklus riset: rocket propulsion",
 "• daftar dataset",
 "• analisis dataset: DATASET_ID; x=power; y=thrust",
 "• model dataset: DATASET_ID; target=thrust"
].join("\n");
function pairs(raw){
 const values={};for(const part of String(raw||"").split(/[;,]/)){
  if(!part.trim())continue;
  const m=part.trim().match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)$/i);
  if(!m)throw new Error("Nilai harus memakai pasangan variabel=angka, dipisahkan koma.");
  const n=Number(m[2]);if(!Number.isFinite(n))throw new Error("Nilai variabel harus finite.");values[m[1]]=n;
 }
 return values;
}
function symbolic(operation,expression,variable="x",extra={}){
 return {question:operation+" "+expression,context:{workflow:"symbolic",operation,expression,variable,...extra}};
}
function describe(result){
 const analysis=result?.analysis||{},output=analysis.output||{};
 if(analysis.error||analysis.status==="ENGINE_FAILED")return "Mesin browser gagal: "+(analysis.error||"hasil tidak tersedia.");
 return "Mesin browser: "+String(analysis.engineId||"research")+
  "\nStatus: "+String(analysis.status||"COMPLETED")+
  "\n"+JSON.stringify(output,null,2).slice(0,10000)+
  (result?.evidence?.summary?"\n\nCatatan bukti: "+result.evidence.summary:"");
}
async function execute(question){
 const q=String(question||"").trim();
 if(!q)return null;
 const core=window.BeyondLightResearchCore;
 if(/^(?:bantuan mesin|engine help|perintah mesin)$/i.test(q))return {handled:true,text:helpText};
 if(/^(?:daftar dataset|list datasets)$/i.test(q)){
  if(!core)return {handled:true,text:"Research core browser belum dimuat."};
  return {handled:true,text:"Dataset lokal browser:\n"+JSON.stringify(core.listDatasets(),null,2)};
 }
 if(!core)return null;
 let request=null,m;
 if((m=q.match(/^(?:turunkan|differentiate|derivative)\s*:?\s*(.+?)(?:\s+(?:terhadap|with respect to)\s+([A-Za-z_][A-Za-z0-9_]*))?$/i)))
  request=symbolic("differentiate",m[1],m[2]||"x");
 else if((m=q.match(/^(?:integralkan|integrate|integral)\s*:?\s*(.+?)(?:\s+(?:terhadap|with respect to)\s+([A-Za-z_][A-Za-z0-9_]*))?$/i)))
  request=symbolic("integrate",m[1],m[2]||"x");
 else if((m=q.match(/^(?:sederhanakan|simplify)\s*:?\s*(.+)$/i)))
  request=symbolic("simplify",m[1]);
 else if((m=q.match(/^(?:evaluasi|evaluate)\s*:?\s*(.+?)\s*(?:;|dengan|where)\s*(.+)$/i))){
  try{request=symbolic("evaluate",m[1],"x",{values:pairs(m[2])});}catch(error){return {handled:true,text:"Format evaluasi tidak valid: "+String(error?.message||error)};}
 }
 else if((m=q.match(/^(?:isolasi|isolate)\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:dari|from)\s+(.+)$/i))){
  const sides=m[2].split("=");if(sides.length!==2||!sides[0].trim()||!sides[1].trim())return {handled:true,text:"Format persamaan harus: isolasi x dari ruas_kiri=ruas_kanan."};
  request={question:q,context:{workflow:"symbolic",operation:"isolate",lhs:sides[0].trim(),rhs:sides[1].trim(),variable:m[1]}};
 }else if(/^(?:benchmark semua|run all benchmarks|uji semua benchmark)$/i.test(q))
  request={question:q,context:{workflow:"catalog-validation"}};
 else if((m=q.match(/^(?:cari dataset|search dataset)\s*:\s*(.{2,160})$/i)))
  request={question:m[1],context:{workflow:"open-data-discovery"}};
 else if((m=q.match(/^(?:siklus riset|research cycle)\s*:\s*(.{2,160})$/i)))
  request={question:m[1],context:{workflow:"open-data"}};
 else if((m=q.match(/^analisis dataset\s*:\s*([^;]+);\s*x\s*=\s*([^;]+);\s*y\s*=\s*(.+)$/i)))
  request={question:q,context:{workflow:"dataset-analysis",datasetId:m[1].trim(),x:m[2].trim(),y:m[3].trim()}};
 else if((m=q.match(/^model dataset\s*:\s*([^;]+);\s*target\s*=\s*(.+)$/i)))
  request={question:q,context:{workflow:"autonomous-model",datasetId:m[1].trim(),target:m[2].trim()}};
 else return null;
 try{
  const result=await core.dispatch(request);
  return {handled:true,text:describe(result),result};
 }catch(error){return {handled:true,text:"Perintah mesin browser gagal: "+String(error?.message||error)};}
}
window.BeyondLightChatCommands={execute,helpText};
})();
