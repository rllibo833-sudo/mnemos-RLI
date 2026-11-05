/* Bounded browser port of AutonomousModelExplorer.java.
 * Searches a deterministic feature grammar; it does not discover physical laws.
 */
(() => {
"use strict";
const finite=(v,label)=>{const n=Number(v);if(!Number.isFinite(n))throw new Error(label+" must be finite.");return n;};
const sq=x=>x*x;
const mean=a=>a.reduce((s,v)=>s+v,0)/a.length;
const variance=a=>{const m=mean(a);return a.reduce((s,v)=>s+sq(v-m),0)/a.length;};
const correlation=(x,y)=>{const mx=mean(x),my=mean(y);let a=0,b=0,c=0;for(let i=0;i<x.length;i++){const u=x[i]-mx,v=y[i]-my;a+=u*v;b+=u*u;c+=v*v;}return b*c===0?0:a/Math.sqrt(b*c);};
const map=(a,f)=>a.map(f);
function fit(features,indices,y,fold,folds){
 const p=indices.length+1,a=Array.from({length:p},()=>Array(p+1).fill(0));let count=0;
 for(let i=0;i<y.length;i++)if(fold===null||i%folds!==fold){
  count++;const v=[1,...indices.map(k=>features[k].values[i])];
  for(let r=0;r<p;r++){a[r][p]+=v[r]*y[i];for(let c=0;c<p;c++)a[r][c]+=v[r]*v[c];}
 }
 if(count<p)return null;
 for(let i=0;i<p;i++){
  let pivot=i;for(let r=i+1;r<p;r++)if(Math.abs(a[r][i])>Math.abs(a[pivot][i]))pivot=r;
  if(Math.abs(a[pivot][i])<1e-12)return null;
  [a[i],a[pivot]]=[a[pivot],a[i]];
  const d=a[i][i];for(let c=i;c<=p;c++)a[i][c]/=d;
  for(let r=0;r<p;r++)if(r!==i){const f=a[r][i];for(let c=i;c<=p;c++)a[r][c]-=f*a[i][c];}
 }
 return a.map(row=>row[p]);
}
function explore(dataset,target){
 const headers=Array.isArray(dataset?.headers)?dataset.headers.map(String):[];
 const rows=Array.isArray(dataset?.rows)?dataset.rows:[];
 const yi=headers.indexOf(String(target));
 if(yi<0||rows.length<6)throw new Error("Target column and at least six rows are required.");
 const n=Math.min(2000,rows.length),indices=Array.from({length:n},(_,i)=>n===rows.length?i:Math.floor(i*(rows.length-1)/(n-1)));
 const y=indices.map((r,i)=>finite(rows[r]?.[yi],"target row "+(i+1)));
 const columns=new Map();
 for(let c=0;c<headers.length;c++)if(c!==yi){
  const values=indices.map((r,i)=>finite(rows[r]?.[c],"input "+headers[c]+" row "+(i+1)));
  if(variance(values)>1e-24)columns.set(headers[c],values);
 }
 const selected=[...columns.entries()].sort((a,b)=>Math.abs(correlation(b[1],y))-Math.abs(correlation(a[1],y))).slice(0,4);
 if(!selected.length)throw new Error("No varying numeric predictor columns are available.");
 const features=[],zcols=new Map(),normalization={};
 for(const [name,values] of selected){
  const m=mean(values),sd=Math.sqrt(variance(values));if(!(sd>0))continue;
  const z=values.map(v=>(v-m)/sd);zcols.set(name,z);normalization[name]=[m,sd];
  features.push({expression:"z("+name+")",kind:"linear",columns:[name],values:z});
  features.push({expression:"z("+name+")^2",kind:"square",columns:[name],values:map(z,v=>v*v)});
  features.push({expression:"exp(clamp(z("+name+")))",kind:"exponential",columns:[name],values:map(z,v=>Math.exp(Math.max(-5,Math.min(5,v))))});
  features.push({expression:"ln(1+abs(z("+name+")))",kind:"log_abs",columns:[name],values:map(z,v=>Math.log1p(Math.abs(v)))});
 }
 const names=[...zcols.keys()];
 for(let a=0;a<names.length;a++)for(let b=a+1;b<names.length;b++){
  const x=zcols.get(names[a]),z=zcols.get(names[b]);
  features.push({expression:"z("+names[a]+")*z("+names[b]+")",kind:"interaction",columns:[names[a],names[b]],values:x.map((v,i)=>v*z[i])});
 }
 const folds=Math.min(5,Math.floor(n/3)),models=[];
 for(let a=0;a<features.length;a++)for(let b=-1;b<a;b++){
  const chosen=b<0?[a]:[b,a],full=fit(features,chosen,y,null,0);if(!full)continue;
  let cv=0,base=0,count=0,valid=true;
  for(let f=0;f<folds;f++){
   const coeff=fit(features,chosen,y,f,folds);if(!coeff){valid=false;break;}
   let trainMean=0,trainCount=0;
   for(let i=0;i<n;i++)if(i%folds!==f){trainMean+=y[i];trainCount++;}
   trainMean/=trainCount;
   for(let i=0;i<n;i++)if(i%folds===f){
    let pred=coeff[0];for(let k=0;k<chosen.length;k++)pred+=coeff[k+1]*features[chosen[k]].values[i];
    cv+=sq(y[i]-pred);base+=sq(y[i]-trainMean);count++;
   }
  }
  if(!valid||!count)continue;
  const ym=mean(y);let sse=0,sst=0;
  for(let i=0;i<n;i++){let pred=full[0];for(let k=0;k<chosen.length;k++)pred+=full[k+1]*features[chosen[k]].values[i];sse+=sq(y[i]-pred);sst+=sq(y[i]-ym);}
  const terms=chosen.map(k=>features[k].expression),definitions=chosen.map(k=>({expression:features[k].expression,kind:features[k].kind,columns:features[k].columns}));
  let equation=String(target)+" = "+full[0];for(let k=0;k<terms.length;k++)equation+=" + ("+full[k+1]+")*"+terms[k];
  models.push({equation,terms,termDefinitions:definitions,coefficients:full,fitRmse:Math.sqrt(sse/n),crossValidationRmse:Math.sqrt(cv/count),trainingMeanBaselineRmse:Math.sqrt(base/count),rSquared:sst===0?null:1-sse/sst,beatsInternalBaseline:cv<base,coefficientUnit:String(dataset.units||"").split(",").map(p=>p.trim().split(":",2)).find(p=>p.length===2&&p[0].trim()===target)?.[1]?.trim()||"unknown",classification:cv<base?"UNVERIFIED_CANDIDATE_SUPPORTED_WITHIN_DATASET":"UNVERIFIED_CANDIDATE_NOT_SUPPORTED_BY_INTERNAL_CV"});
 }
 models.sort((a,b)=>a.crossValidationRmse-b.crossValidationRmse);
 const best=models.slice(0,8),supported=best.some(m=>m.beatsInternalBaseline);
 return {id:"browser-model-"+String(dataset.id||"local")+"-"+String(target),recordType:"AUTONOMOUS_MODEL_EXPLORATION",category:"research",title:"Pencarian struktur model otomatis: "+target+" dari "+String(dataset.filename||"dataset"),model:"Feature grammar search: linear, quadratic, exponential, logarithmic, pair interactions; one- and two-term combinations",inputs:{datasetId:dataset.id||"user-supplied",filename:dataset.filename||"",target,predictorsSearched:names,normalization,rowsAnalyzed:n,folds,featureStructuresGenerated:features.length,candidateStructuresFitted:models.length},result:{status:supported?"CANDIDATE_MODEL_FOUND_INTERNAL_SCREEN_ONLY":"NO_MODEL_PASSED_INTERNAL_SCREEN",bestModels:best},sources:[{datasetId:dataset.id||"",filename:dataset.filename||"",source:dataset.source||"USER_IMPORTED",author:dataset.author||"",year:dataset.year||"",doi:dataset.doi||"",datasetStatus:dataset.status||"NOT_ASSESSED"}],equations:best.map(m=>({equation:m.equation,classification:m.classification})),status:supported?"UNVERIFIED_DATA_DERIVED_MODEL_CANDIDATE":"NO_MODEL_SUPPORTED_BY_INTERNAL_CV",limitations:["Feature grammar is bounded; this is not autonomous physical theory or law discovery.","Predictors are standardized using the full dataset before cross-validation, matching the Java reference implementation; this can leak distribution information across folds.","Cross-validation reuses this dataset. Independent sourced data and experiments are still required.","A model outperforming the internal baseline is only an unverified candidate, not causal evidence."]};
}
window.BeyondLightAutonomousModel={explore};
})();
