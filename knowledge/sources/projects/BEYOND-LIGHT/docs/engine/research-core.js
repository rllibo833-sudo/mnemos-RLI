/* Beyond-Light browser research integration.
 * Browser translation of ResearchRequest/Plan, ResearchPlanner, EngineRegistry,
 * ResearchOrchestrator, ResearchDomainAdapters and EvidenceEvaluator contracts.
 * No server, filesystem, credentials, or hidden remote execution.
 */
(() => {
"use strict";
const now=()=>new Date().toISOString();
const text=(v,k,max=2000)=>{const s=String(v??"").trim();if(!s||s.length>max)throw new Error(k+" harus berisi 1–"+max+" karakter.");return s;};
const obj=v=>v&&typeof v==="object"&&!Array.isArray(v)?v:{};
const finite=(v,k)=>{const n=Number(v);if(!Number.isFinite(n))throw new Error(k+" harus angka finite.");return n;};
const routes={
 "catalog-validation":"science.catalog-validation","symbolic":"mathematics.symbolic",
 "relativity":"physics.special-relativity","feasibility":"engineering.feasibility-assessment",
 "benchmark":"science.numerical-benchmarks","material-selection":"engineering.material-selection",
 "uncertainty":"science.uncertainty-analysis","technology-domain":"engineering.technology-domain",
 "cross-domain-technology":"engineering.cross-domain-technology","integrated-technology":"technology.integrated-research",
 "dataset-analysis":"dataset.deterministic-analysis","autonomous-model":"research.autonomous-model-exploration","equation-composition":"mathematics.equation-composition","open-data":"research.open-data-cycle",
 "general-relativity":"physics.metric-geometry","engineering-calculation":"engineering.calculation",
 "open-data-discovery":"research.open-data-discovery","core-calculation":"core.deterministic-calculations"
};
const descriptions={
 "science.catalog-validation":"Validasi metadata katalog, dimensi persamaan, dan benchmark browser.",
 "mathematics.symbolic":"Penyederhanaan, turunan, integral, substitusi, dan evaluasi simbolik.",
 "physics.special-relativity":"Kalkulasi relativitas khusus dalam model inersial terbatas.",
 "engineering.feasibility-assessment":"Assessment bertahap propulsion dan agregasi komponen/material.",
 "science.numerical-benchmarks":"Benchmark numerik yang memang memiliki evaluator browser.",
 "engineering.material-selection":"Penyaringan properti material dari data yang diimpor pengguna.",
 "science.uncertainty-analysis":"Analisis ketidakpastian; hanya bila port browser tersedia.",
 "engineering.technology-domain":"Eksplorasi domain desain teknologi yang terdaftar di browser.",
 "engineering.cross-domain-technology":"Screening desain lintas-domain berbasis modul desain browser.",
 "technology.integrated-research":"Integrasi riset teknologi berbasis dataset lokal yang dipilih.",
 "dataset.deterministic-analysis":"Analisis deterministik dataset yang diberikan secara lokal.",
 "research.autonomous-model-exploration":"Pencarian feature grammar satu dan dua term pada dataset lokal; kandidat belum terverifikasi.",
 "mathematics.equation-composition":"Isolasi variabel bersama, substitusi antar-persamaan, dan pemeriksaan dimensi SI.",
 "research.open-data-cycle":"Siklus open-data dan screening dataset; impor file otomatis memerlukan dukungan CORS dan penyimpanan browser.",
 "physics.metric-geometry":"Geometri metrik relativitas umum; belum tersedia sebagai solver browser penuh.",
 "engineering.calculation":"Kalkulasi rekayasa melalui primitive browser yang tersedia.",
 "research.open-data-discovery":"Penemuan metadata Zenodo tanpa mengklaim telaah full-text.",
 "core.deterministic-calculations":"Kalkulasi deterministik SI: propulsion ideal, screening material, Simpson, RK4, dan konversi unit."
};
function createRequest(input){
 const v=obj(input),question=text(v.question,"question",2000),context=obj(v.context);
 const hints=Array.isArray(v.disciplineHints)?[...new Set(v.disciplineHints.filter(x=>typeof x==="string").map(x=>x.trim()).filter(Boolean))].slice(0,12):[];
 return {id:String(v.id||crypto.randomUUID()),question,context,disciplineHints:hints,createdAt:v.createdAt||now()};
}
function infer(question,hints){
 if(hints.length)return hints[0].toLowerCase();
 const q=question.toLowerCase(),tests=[
  ["history",["sejarah","history","historis"]],["philosophy",["filsafat","filosofi","philosophy","etika","ethics"]],
  ["economics",["ekonomi","economy","economic","pasar"]],["social-science",["sosial","masyarakat","sociology"]],
  ["chemistry",["kimia","chemical","chemistry","reaksi"]],["biology",["biologi","biology","genetik"]],
  ["physics",["fisika","physics","energi","gravitasi"]],["mathematics",["matematika","mathematics","equation","persamaan"]],
  ["engineering",["mesin","rekayasa","engineering","material","desain"]]
 ];
 for(const [d,words] of tests)if(words.some(w=>q.includes(w)))return d;
 return "general";
}
function plan(request){
 const c=request.context,w=String(c.workflow||"");
 let engineId=routes[w],discipline=infer(request.question,request.disciplineHints);
 if(!engineId&&c.datasetId&&c.target)engineId=routes["autonomous-model"];
 if(!engineId&&c.datasetId&&c.x&&c.y)engineId=routes["dataset-analysis"];
 if(!engineId){if(request.question.length>160)throw new Error("Rute open-data umum menerima pertanyaan maksimal 160 karakter.");engineId=["history","philosophy","economics","social-science","chemistry","biology"].includes(discipline)?routes["open-data-discovery"]:routes["open-data"];}
 if(w==="symbolic")discipline="mathematics";
 else if(w==="relativity"||w==="general-relativity")discipline="physics";
 else if(w==="dataset-analysis")discipline="data-science";
 else if(w==="open-data"||w==="open-data-discovery")discipline=infer(request.question,request.disciplineHints);
 else if(w==="catalog-validation"||w==="benchmark"||w==="uncertainty")discipline="science";
 else if(engineId.startsWith("engineering.")||engineId.startsWith("technology."))discipline="engineering";
 return {requestId:request.id,primaryDiscipline:discipline,disciplines:[discipline,...request.disciplineHints.filter(x=>x!==discipline)],steps:[{id:"step-1",engineId,purpose:descriptions[engineId],required:true}],rationale:w?"Workflow dipilih eksplisit; routing deterministik, bukan LLM.":"Rute dipilih dengan aturan kata kunci; ini bukan reasoning AI.",createdAt:now()};
}
function sourceList(raw){
 if(!Array.isArray(raw))return [];
 return raw.map((s,i)=>({id:String(s.id||s.doi||s.url||"source-"+i),title:String(s.title||""),sourceType:String(s.sourceType||s.type||"unspecified"),provider:String(s.provider||s.source||""),author:String(s.author||s.authors||""),publicationDate:String(s.publicationDate||s.year||""),doi:String(s.doi||""),url:String(s.url||""),license:String(s.license||""),verificationStatus:String(s.verificationStatus||"NOT_ASSESSED"),metadata:obj(s.metadata)}));
}
function runSymbolic(c){
 const S=window.BeyondLightSymbolic;if(!S)throw new Error("Mesin symbolic browser belum dimuat.");
 const op=String(c.operation||"simplify"),expr=op==="isolate"?"":text(c.expression,"expression",4096),v=String(c.variable||"x");
 let result;
 if(op==="simplify")result=S.print(S.parse(expr));
 else if(op==="differentiate")result=S.print(S.simplify(S.derivative(S.parse(expr),v)));
 else if(op==="integrate")result=S.print(S.simplify(S.integrate(S.parse(expr),v)))+" + C";
 else if(op==="evaluate")result=S.evaluate(S.parse(expr),obj(c.values));
 else if(op==="substitute")result=S.substitute(expr,text(c.variable,"variable",128),text(c.replacement,"replacement",4096));
 else if(op==="isolate")result=S.isolate(text(c.lhs,"lhs",4096),text(c.rhs,"rhs",4096),text(c.variable,"variable",128));
 else throw new Error("Operasi simbolik tidak dikenal: "+op);
 return {status:"SYMBOLIC_OPERATION_COMPLETED",operation:op,inputExpression:expr,variable:v,result};
}
function runBenchmark(c){
 const B=window.BeyondLightResearch?.benchmarks;if(!B)throw new Error("Mesin benchmark browser belum dimuat.");
 const runs=c.benchmarkGroup?B.catalog.filter(x=>x.group===c.benchmarkGroup).map(x=>B.run(x.id,undefined,c.tolerance)): [B.run(text(c.benchmarkId,"benchmarkId"),undefined,c.tolerance)];
 return {status:runs.length&&runs.every(x=>x.status==="PASS"||x.status==="WITHIN_TOLERANCE")?"BENCHMARKS_PASSED":"BENCHMARK_RESULTS_RECORDED",runs,runCount:runs.length};
}
function runFeasibility(c){
 const F=window.BeyondLightFeasibilityAssessment;if(!F)throw new Error("Mesin feasibility assessment browser belum dimuat.");
 const a=F.assess({family:text(c.propulsionFamily||c.family,"propulsionFamily"),dryKg:finite(c.dryMassKg??c.dryKg,"dryMassKg"),payloadKg:finite(c.payloadKg,"payloadKg"),dv:finite(c.deltaVMs??c.dv,"deltaVMs"),isp:finite(c.ispS??c.isp,"ispS"),thrust:finite(c.thrustN??c.thrust,"thrustN"),efficiency:finite(c.efficiency,"efficiency"),duration:finite(c.durationS??c.duration,"durationS"),availablePowerW:finite(c.availablePowerW,"availablePowerW"),coolingW:finite(c.coolingW??c.coolingCapacityW,"coolingW"),assembly:c.assembly||null});
 const D=window.BeyondLightDecision;
 const classification=D?D.classify({assessment:a,benchmarkResults:c.benchmarkResults||[],experimentalEvidence:c.experimentalEvidence||{}}):null;
 return {status:a.overallClassification,assessment:a,evidenceClassification:classification};
}
function runTechnology(c){
 const T=window.BeyondLightTechnologyDesign;if(!T)throw new Error("Mesin technology design browser belum dimuat.");
 return T.explore(text(c.domainId,"domainId"),obj(c.inputs));
}
function runCore(c){
 const op=String(c.operation||""),G0=9.80665;
 if(op==="propulsion"){
  const dry=finite(c.dryMassKg,"dryMassKg"),payload=finite(c.payloadKg,"payloadKg"),dv=finite(c.deltaVMs,"deltaVMs"),isp=finite(c.ispS,"ispS"),thrust=finite(c.thrustN,"thrustN"),eta=finite(c.efficiency,"efficiency");
  if([dry,payload,dv,isp,thrust].some(x=>x<=0)||eta<=0||eta>1)throw new Error("Massa, delta-v, Isp, thrust harus positif dan efficiency 0<eta<=1.");
  const ve=isp*G0,mf=dry+payload,m0=mf*Math.exp(dv/ve),prop=m0-mf,mdot=thrust/ve,pkin=.5*mdot*ve*ve,pe=pkin/eta;
  if(![m0,prop,pkin,pe].every(Number.isFinite))throw new Error("Parameter menghasilkan nilai nonfinite.");
  return {thrustN:thrust,exhaustVelocityMS:ve,massFlowKgS:mdot,deltaVMs:ve*Math.log(m0/mf),propellantKg:prop,kineticPowerW:pkin,electricalPowerW:pe,burnSeconds:prop/mdot,initialMassKg:m0,finalMassKg:mf,scope:"Ideal rocket equation; not hardware design."};
 }
 if(op==="material"){
  const volume=finite(c.volumeM3,"volumeM3"),load=finite(c.loadN,"loadN"),area=finite(c.areaM2,"areaM2"),safety=finite(c.safetyFactor,"safetyFactor"),density=finite(c.densityKgM3,"densityKgM3"),yieldPa=finite(c.yieldPa??0,"yieldPa"),cp=finite(c.specificHeatJkgK??0,"specificHeatJkgK");
  if(volume<=0||area<=0||safety<=0||density<=0||load<0)throw new Error("Volume, area, safety, density harus positif; load nonnegatif.");
  const stress=load/area,mass=volume*density,margin=yieldPa>0?yieldPa/stress:null;
  return {volumeM3:volume,massKg:mass,stressPa:stress,safetyFactor:margin,heatCapacityJPerK:mass*cp,assessment:yieldPa<=0?"Cannot evaluate strength: verified yield-strength data missing":margin>=safety?"Passes supplied static yield screening only":"Fails supplied static yield screening"};
 }
 if(op==="simpson"){
  const S=window.BeyondLightSymbolic,expr=text(c.expression,"expression",4096),a=finite(c.lower,"lower"),b=finite(c.upper,"upper"),n=Math.floor(finite(c.intervals,"intervals"));
  if(n<2||n>1000000)throw new Error("intervals harus 2..1.000.000.");const count=n%2?n+1:n,h=(b-a)/count,ast=S.parse(expr),f=x=>S.evaluate(ast,{x});
  let sum=f(a)+f(b);for(let i=1;i<count;i++)sum+=(i%2===0?2:4)*f(a+i*h);
  return {integral:sum*h/3,intervals:count,method:"composite Simpson 1/3"};
 }
 if(op==="rk4"){
  const S=window.BeyondLightSymbolic,expr=text(c.derivative,"derivative",4096),ast=S.parse(expr),y0=finite(c.initialY,"initialY"),t0=finite(c.startTime,"startTime"),t1=finite(c.endTime,"endTime"),steps=Math.floor(finite(c.steps,"steps"));
  if(steps<1||steps>1000000)throw new Error("steps harus 1..1.000.000.");const h=(t1-t0)/steps,out=[{t:t0,y:y0}],f=(t,y)=>S.evaluate(ast,{t,y});
  let y=y0,t=t0;for(let i=1;i<=steps;i++){const k1=f(t,y),k2=f(t+h/2,y+h*k1/2),k3=f(t+h/2,y+h*k2/2),k4=f(t+h,y+h*k3);y+=h*(k1+2*k2+2*k3+k4)/6;t+=h;if(!Number.isFinite(y))throw new Error("RK4 menghasilkan nilai nonfinite.");out.push({t,y});}
  return {status:"RK4_COMPLETED",steps,finalY:y,trajectory:out};
 }
 if(op==="convert"){
  const factors={m:1,km:1000,s:1,h:3600,kg:1,g:.001,N:1,kN:1000,W:1,kW:1000,J:1,MJ:1e6},value=finite(c.value,"value"),from=text(c.from,"from",16),to=text(c.to,"to",16);
  if(!(from in factors)||!(to in factors))throw new Error("Konversi unit tidak didukung.");return {value,from,to,result:value*factors[from]/factors[to],scope:"Only same-dimension unit conversions listed in the browser table."};
 }
 throw new Error("Core operation tidak dikenal: "+op);
}
function runEngineering(c){
 const F=window.BeyondLightFeasibility;if(!F)throw new Error("Primitive feasibility browser belum dimuat.");
 return F.evaluate(c);
}
function runCatalog(){
 const R=window.BeyondLightResearch;if(!R)throw new Error("Mesin riset browser belum dimuat.");
 const benches=R.benchmarks.runAll(),eq=R.equations.load();
 return {status:"CATALOG_BROWSER_CHECK_COMPLETED",dimensionEngine:"AVAILABLE",benchmarkCount:benches.length,benchmarkPasses:benches.filter(x=>x.status==="PASS").length,benchmarkInconclusive:benches.filter(x=>x.status==="INCONCLUSIVE").length,savedLocalEquations:eq.length,limitations:["Validasi browser hanya mencakup evaluator yang diterjemahkan; bukan audit semua file Java atau semua sumber primer."]};
}
async function runOpenDataDiscovery(question){
 const q=text(question,"question",160);
 const url="https://zenodo.org/api/records?"+new URLSearchParams({q,size:"10"});
 const response=await fetch(url,{headers:{Accept:"application/json"},mode:"cors",credentials:"omit"});
 if(!response.ok)throw new Error("Zenodo HTTP "+response.status);
 const data=await response.json(),hits=Array.isArray(data)?data:(data.hits?.hits||data.results||[]);
 const records=hits.slice(0,10).map(hit=>{const m=hit.metadata||hit;return {recordId:String(hit.id||""),title:String(m.title||"Untitled"),doi:String(m.doi||""),year:String(m.publication_date||"").slice(0,4),authors:(m.creators||[]).slice(0,8).map(x=>x.name||"").filter(Boolean).join("; "),description:String(m.description||"").replace(/<[^>]*>/g," ").slice(0,1200),recordUrl:"https://zenodo.org/records/"+hit.id,files:(hit.files||[]).filter(f=>String(f.key||f.filename||"").toLowerCase().endsWith(".csv")&&Number(f.size||0)<=10000000).map(f=>({name:f.key||f.filename,size:Number(f.size||0)}))};});
 return {status:records.length?"OPEN_DATA_METADATA_FOUND":"NO_OPEN_RECORDS",records,recordCount:records.length,limitations:["Metadata Zenodo saja; artikel dan dataset belum dibaca atau diverifikasi.","Impor CSV dan analisis dataset otomatis tidak dijalankan dalam workflow metadata-only."]};
}
function runRelativity(c){
 const C=299792458,m=finite(c.massKg,"massKg"),v=finite(c.velocityMs,"velocityMs"),t=finite(c.elapsedTimeS??0,"elapsedTimeS"),L=finite(c.lengthM??0,"lengthM");
 if(m<0||Math.abs(v)>=C||t<0||L<0)throw new Error("Relativitas khusus memerlukan massa/waktu/panjang nonnegatif dan |v| < c.");
 const beta=v/C,gamma=1/Math.sqrt(1-beta*beta),energy=gamma*m*C*C,momentum=gamma*m*v;
 return {status:"RELATIVITY_MODEL_EVALUATED",model:"Special relativity, inertial frame, constant velocity",beta,gamma,properTimeS:t/gamma,coordinateTimeS:t,contractedLengthM:L/gamma,properLengthM:L,momentumKgMs:momentum,totalEnergyJ:energy,kineticEnergyJ:(gamma-1)*m*C*C,restEnergyJ:m*C*C,limitations:["Model gerak inersial berkecepatan konstan; tidak mencakup percepatan, gravitasi, atau eksperimen."]};
}
function runUncertainty(c){
 const S=window.BeyondLightSymbolic;if(!S)throw new Error("Symbolic engine belum tersedia.");
 const mode=String(c.mode||"propagate"),expr=text(c.expression,"expression",4096),ast=S.parse(expr),means=obj(c.means),sigmas=obj(c.sigma),names=Object.keys(means);
 if(!names.length)throw new Error("means harus berisi setidaknya satu variabel numerik.");
 for(const k of names){finite(means[k],"means."+k);if(sigmas[k]!==undefined&&finite(sigmas[k],"sigma."+k)<0)throw new Error("Sigma tidak boleh negatif.");}
 const evaluate=values=>S.evaluate(ast,values),base=evaluate(means);
 const derivatives={};for(const k of names){try{derivatives[k]=S.evaluate(S.derivative(ast,k),means);}catch(_){derivatives[k]=null;}}
 if(mode==="propagate"||mode==="sensitivity"){
  const terms=names.map(k=>({variable:k,derivative:derivatives[k],sigma:Number(sigmas[k]??0),contribution:derivatives[k]===null?null:derivatives[k]*Number(sigmas[k]??0)}));
  const variance=terms.every(x=>x.contribution!==null)?terms.reduce((a,x)=>a+x.contribution*x.contribution,0):null;
  return {status:"UNCERTAINTY_FIRST_ORDER_COMPLETED",mode,expression:expr,nominal:base,standardUncertainty:variance===null?null:Math.sqrt(variance),variance,terms,limitations:["Propagasi orde pertama mengasumsikan model lokal linear dan input independen; korelasi tidak dimodelkan."]};
 }
 if(mode==="sweep"){
  const variable=text(c.variable,"variable",64),from=finite(c.from,"from"),to=finite(c.to,"to"),count=Math.floor(finite(c.steps??25,"steps"));
  if(count<2||count>500||from===to)throw new Error("Sweep memerlukan 2..500 langkah dan batas berbeda.");
  const points=Array.from({length:count},(_,i)=>{const x=from+(to-from)*i/(count-1);return {x,y:evaluate({...means,[variable]:x})};});
  return {status:"UNCERTAINTY_SWEEP_COMPLETED",mode,variable,points,limitations:["Sweep adalah evaluasi deterministik rentang parameter, bukan distribusi probabilitas."]};
 }
 if(mode==="monte-carlo"){
  const n=Math.floor(finite(c.samples??10000,"samples"));if(n<100||n>100000)throw new Error("Monte Carlo dibatasi 100..100000 sampel.");
  let seed=(Number(c.seed)||123456789)>>>0;const rand=()=>{seed=(1664525*seed+1013904223)>>>0;return (seed+1)/4294967297;};
  const gaussian=()=>Math.sqrt(-2*Math.log(rand()))*Math.cos(2*Math.PI*rand()),values=[];
  for(let i=0;i<n;i++){const sample={...means};for(const k of names)sample[k]=Number(means[k])+Number(sigmas[k]??0)*gaussian();const y=evaluate(sample);if(!Number.isFinite(y))throw new Error("Monte Carlo menghasilkan nilai nonfinite.");values.push(y);}
  values.sort((a,b)=>a-b);const avg=values.reduce((a,b)=>a+b,0)/n,variance=values.reduce((a,b)=>a+(b-avg)**2,0)/n;
  return {status:"UNCERTAINTY_MONTE_CARLO_COMPLETED",mode,samples:n,seed:Number(c.seed)||123456789,mean:avg,standardDeviation:Math.sqrt(variance),p05:values[Math.floor(.05*(n-1))],median:values[Math.floor(.5*(n-1))],p95:values[Math.floor(.95*(n-1))],min:values[0],max:values[n-1],limitations:["Monte Carlo memakai distribusi normal independen sesuai sigma input; pemilihan distribusi dan korelasi adalah asumsi pengguna."]};
 }
 throw new Error("Mode uncertainty tidak dikenal: "+mode);
}
function runMaterialSelection(c){
 const materials=Array.isArray(c.materials)?c.materials:[],requirements=obj(c.requirements);
 if(!materials.length)throw new Error("Paket materials harus berisi array material yang diimpor pengguna.");
 const keys=Object.keys(requirements);if(!keys.length)throw new Error("requirements harus berisi batas properti.");
 const evaluated=materials.map(m=>{const checks=keys.map(k=>{const v=m?.[k],r=finite(requirements[k],"requirements."+k);return {property:k,value:Number.isFinite(Number(v))?Number(v):null,minimum:r,known:Number.isFinite(Number(v)),pass:Number.isFinite(Number(v))&&Number(v)>=r};});return {id:m.id||m.name||"unknown",name:m.name||m.id||"unknown",checks,status:checks.every(x=>x.known&&x.pass)?"MATCHED":checks.some(x=>!x.known)?"INCOMPLETE_DATA":"BELOW_REQUIREMENT",source:m.source||m.url||"",verificationStatus:m.verificationStatus||"NOT_ASSESSED"};});
 return {status:"MATERIAL_REQUIREMENTS_SCREENED",requirements,materials:evaluated,matched:evaluated.filter(x=>x.status==="MATCHED").length,limitations:["Hanya properti yang disediakan pengguna yang diperiksa; nilai hilang tidak dianggap lulus.","Tidak ada verifikasi sumber, kondisi proses, atau sertifikasi material."]};
}
function runCrossDomain(c){
 const T=window.BeyondLightTechnologyDesign;if(!T)throw new Error("Technology design browser belum tersedia.");
 const x=obj(c.inputs),required=(k)=>finite(x[k],"inputs."+k);
 const energyKeys=["energyJ","minEnergyDensityJkg","maxEnergyDensityJkg","energyDensitySteps","minEfficiency","maxEfficiency","efficiencySteps","maximumStorageMassKg","maximumInputEnergyJ"];
 const thermalKeys=["conductivityWmK","areaM2","deltaTemperatureK","thicknessM","emissivity","radiatorTemperatureK","ambientTemperatureK","minCoolingCapacityW","maxCoolingCapacityW","coolingCapacitySteps"];
 const structureKeys=["tensileLoadN","shearLoadN","baseAreaM2","baseShearAreaM2","baseSecondMomentM4","memberLengthM","youngModulusPa","yieldStrengthPa","densityKgM3","requiredSafetyFactor","effectiveLengthFactor","minSectionScale","maxSectionScale","sectionScaleSteps"];
 const select=keys=>Object.fromEntries(keys.map(k=>[k,required(k)]));
 const best=(run,metric)=>(run.allCandidates||[]).filter(v=>v.candidateFeasible).sort((a,b)=>a[metric]-b[metric])[0]||null;
 const energy=T.explore("energy.storage.envelope",select(energyKeys)),energyCandidate=best(energy,"minimumStorageMassKg");
 if(!energyCandidate)return {status:"ENERGY_STORAGE_NO_FEASIBLE_CANDIDATE",energyStorage:energy,allStagesPassed:false};
 const duration=required("operatingDurationS");if(duration<=0)throw new Error("operatingDurationS harus positif.");
 const derivedHeat=energyCandidate.conversionLossJ/duration;
 const thermalInputs=select(thermalKeys);thermalInputs.requiredHeatW=derivedHeat;
 const thermal=T.explore("thermal.management.steady-state",thermalInputs),thermalCandidate=best(thermal,"coolingCapacityW");
 if(!thermalCandidate)return {status:"THERMAL_MANAGEMENT_NO_FEASIBLE_CANDIDATE",energyStorage:energy,thermalManagement:thermal,allStagesPassed:false,coupling:{storageMassKg:energyCandidate.minimumStorageMassKg,conversionLossJ:energyCandidate.conversionLossJ,operatingDurationS:duration,derivedThermalLoadW:derivedHeat}};
 const acceleration=required("designAccelerationMS2");if(acceleration<0)throw new Error("designAccelerationMS2 tidak boleh negatif.");
 const compression=required("baseCompressiveLoadN")+energyCandidate.minimumStorageMassKg*acceleration;
 const structureInputs=select(structureKeys);structureInputs.compressiveLoadN=compression;
 const structures=T.explore("structures.member.envelope",structureInputs),structureCandidate=best(structures,"estimatedMemberMassKg");
 return {status:structureCandidate?"CROSS_DOMAIN_SCREEN_COMPLETE":"STRUCTURES_NO_FEASIBLE_CANDIDATE",energyStorage:energy,thermalManagement:thermal,structures,allStagesPassed:Boolean(structureCandidate),coupling:{storageMassKg:energyCandidate.minimumStorageMassKg,conversionLossJ:energyCandidate.conversionLossJ,operatingDurationS:duration,derivedThermalLoadW:derivedHeat,derivedStructuralCompressionLoadN:compression,selectedStructuralCandidate:structureCandidate},limitations:["Screening berurutan energi → termal → struktur; bukan solver multiphysics terkopel penuh.","Rugi energi dirata-ratakan selama operatingDurationS dan dipakai sebagai beban termal steady-state.","Massa termal tidak dimasukkan ke beban struktur; seluruh asumsi material/geometri/beban berasal dari pengguna."]};
}
function parseCsv(raw){
 const rows=[];let row=[],field="",quoted=false;
 for(let i=0;i<raw.length;i++){const ch=raw[i];if(quoted){if(ch==='"'&&raw[i+1]==='"'){field+='"';i++;}else if(ch==='"')quoted=false;else field+=ch;}else if(ch==='"')quoted=true;else if(ch===","){row.push(field);field="";}else if(ch==="\n"){row.push(field.replace(/\r$/,""));rows.push(row);row=[];field="";}else field+=ch;}
 if(quoted)throw new Error("CSV memiliki kutip yang tidak ditutup.");if(field.length||row.length){row.push(field.replace(/\r$/,""));rows.push(row);}
 return rows.filter(r=>r.some(x=>x.trim()));
}
const DATASET_KEY="beyond-light.research-datasets.v1";
function loadDatasets(){try{const v=JSON.parse(localStorage.getItem(DATASET_KEY)||"[]");return Array.isArray(v)?v:[];}catch(_){return [];}}
function importDatasetCsv(filename,raw,metadata={}){
 const name=text(filename,"filename",180);if(!name.toLowerCase().endsWith(".csv"))throw new Error("Hanya file CSV yang didukung.");
 if(typeof raw!=="string"||raw.length>2_000_000)throw new Error("CSV harus berupa teks maksimal 2 MB.");
 const parsed=parseCsv(raw),headers=parsed.shift().map(x=>x.trim());if(headers.length<2||headers.some(x=>!x))throw new Error("Header CSV tidak valid.");
 const rows=parsed.filter(r=>r.length===headers.length);if(rows.length<6||rows.length>5000)throw new Error("CSV memerlukan 6..5000 baris data konsisten.");
 const numeric=rows.map((r,i)=>r.map((v,j)=>{const n=Number(v);if(v.trim()===""||!Number.isFinite(n))throw new Error("CSV harus numerik; baris "+(i+2)+", kolom "+headers[j]+" tidak valid.");return n;}));
 const record={id:crypto.randomUUID(),filename:name,headers,rows:numeric,importedAt:now(),source:String(metadata.source||"USER_IMPORTED"),doi:String(metadata.doi||""),license:String(metadata.license||""),units:String(metadata.units||"")};
 const all=loadDatasets();all.push(record);localStorage.setItem(DATASET_KEY,JSON.stringify(all.slice(-20)));return {id:record.id,filename:name,rows:numeric.length,variables:headers,source:record.source,doi:record.doi};
}
function solveLinear(matrix,vector){
 const n=vector.length,a=matrix.map((row,i)=>row.concat(vector[i]));
 for(let i=0;i<n;i++){let pivot=i;for(let r=i+1;r<n;r++)if(Math.abs(a[r][i])>Math.abs(a[pivot][i]))pivot=r;
  if(Math.abs(a[pivot][i])<1e-14)return null;[a[i],a[pivot]]=[a[pivot],a[i]];
  const d=a[i][i];for(let j=i;j<=n;j++)a[i][j]/=d;
  for(let r=0;r<n;r++)if(r!==i){const f=a[r][i];for(let j=i;j<=n;j++)a[r][j]-=f*a[i][j];}
 }
 return a.map(row=>row[n]);
}
function fitCandidate(points,kind,degree=1){
 const transform=kind==="logarithmic"?p=>Math.log(p.x):kind==="reciprocal"?p=>1/p.x:kind==="exponential"||kind==="power law"?p=>p.x:p=>p.x;
 if((kind==="logarithmic"||kind==="reciprocal"||kind==="power law")&&points.some(p=>p.x<=0))return null;
 if((kind==="exponential"||kind==="power law")&&points.some(p=>p.y<=0))return null;
 const xs=points.map(transform),ys=points.map(p=>kind==="exponential"||kind==="power law"?Math.log(p.y):p.y);
 const deg=kind.startsWith("polynomial")?degree:1,n=deg+1,matrix=Array.from({length:n},()=>Array(n).fill(0)),rhs=Array(n).fill(0);
 for(let r=0;r<n;r++){for(let i=0;i<xs.length;i++){rhs[r]+=Math.pow(xs[i],r)*ys[i];for(let c=0;c<n;c++)matrix[r][c]+=Math.pow(xs[i],r+c);}}
 const coefficients=solveLinear(matrix,rhs);if(!coefficients)return null;
 const params=kind==="exponential"||kind==="power law"?[Math.exp(coefficients[0]),coefficients[1]]:coefficients;
 const predict=x=>{if(kind==="polynomial")return params.reduceRight((acc,v)=>acc*x+v,0);if(kind==="logarithmic")return params[0]+params[1]*Math.log(x);if(kind==="reciprocal")return params[0]+params[1]/x;if(kind==="exponential")return params[0]*Math.exp(params[1]*x);if(kind==="power law")return params[0]*Math.pow(x,params[1]);return NaN;};
 let sse=0,mean=points.reduce((a,p)=>a+p.y,0)/points.length,sst=0;for(const p of points){const y=predict(p.x);if(!Number.isFinite(y))return null;sse+=(p.y-y)**2;sst+=(p.y-mean)**2;}
 return {algorithm:kind==="polynomial"?"polynomial degree "+degree:kind,parameters:params,equation:kind==="polynomial"?"polynomial degree "+degree:kind,fitRmse:Math.sqrt(sse/points.length),rSquared:sst?1-sse/sst:null,predict};
}
function searchDatasetModels(points){
 const specs=[];for(let d=1;d<=4;d++)specs.push(["polynomial",d]);specs.push(["logarithmic",1],["reciprocal",1],["exponential",1],["power law",1]);
 const out=[];
 for(const [kind,degree] of specs){const full=fitCandidate(points,kind,degree);if(!full)continue;const folds=Math.min(5,Math.floor(points.length/3));let cv=0,base=0,n=0,valid=true;
  for(let f=0;f<folds;f++){const train=points.filter((_,i)=>i%folds!==f),test=points.filter((_,i)=>i%folds===f),model=fitCandidate(train,kind,degree);if(!model){valid=false;break;}const mean=train.reduce((a,p)=>a+p.y,0)/train.length;for(const p of test){const y=model.predict(p.x);if(!Number.isFinite(y)){valid=false;break;}cv+=(p.y-y)**2;base+=(p.y-mean)**2;n++;}}
  if(!valid||!n)continue;const model={algorithm:full.algorithm,equation:full.equation,parameters:full.parameters,fitRmse:full.fitRmse,rSquared:full.rSquared,crossValidationRmse:Math.sqrt(cv/n),constantBaselineRmse:Math.sqrt(base/n),cvBetterThanConstant:cv<base,classification:cv<base?"PATTERN_OUTPERFORMS_CONSTANT_BASELINE_ON_INTERNAL_CV":"NOT_SUPPORTED_AGAINST_CONSTANT_BASELINE"};
  out.push(model);
 }
 return out.sort((a,b)=>a.crossValidationRmse-b.crossValidationRmse);
}
function runEquationComposition(c){
 const S=window.BeyondLightSymbolic,R=window.BeyondLightResearch;
 if(!S||!R?.dimensions)throw new Error("Mesin symbolic/dimensions browser belum tersedia.");
 const a=obj(c.equationA),b=obj(c.equationB),shared=text(c.sharedVariable,"sharedVariable",128),dims=text(c.variableDimensions,"variableDimensions",4000);
 const lhsA=text(a.lhs,"equationA.lhs",4096),rhsA=text(a.rhs,"equationA.rhs",4096),lhsB=text(b.lhs,"equationB.lhs",4096),rhsB=text(b.rhs,"equationB.rhs",4096);
 const variables=source=>new Set((source.match(/[A-Za-z_][A-Za-z0-9_]*/g)||[]).filter(x=>!["sqrt","sin","cos","ln","exp","pi","e"].includes(x)));
 const va=variables(lhsA+" "+rhsA),vb=variables(lhsB+" "+rhsB);
 if(!va.has(shared)||!vb.has(shared))throw new Error("Variabel bersama yang dipilih harus ada pada kedua persamaan.");
 const first=R.dimensions.validateEquation(lhsA+"="+rhsA,dims),second=R.dimensions.validateEquation(lhsB+"="+rhsB,dims);
 const isolated=S.isolate(lhsA,rhsA,shared),left=S.substitute(lhsB,shared,isolated),right=S.substitute(rhsB,shared,isolated);
 const balanced=R.dimensions.validateEquation(left+"="+right,dims);
 let residual=null,numeric=null;
 const values=obj(c.values);
 if(Object.keys(values).length){const l=S.evaluate(S.parse(left),values),r=S.evaluate(S.parse(right),values);residual=l-r;numeric={left:l,right:r,residual};}
 const derivation="1. Source A: "+String(a.name||"Equation A")+" ("+lhsA+" = "+rhsA+")\n2. Isolate "+shared+": "+shared+" = "+isolated+"\n3. Source B: "+String(b.name||"Equation B")+" ("+lhsB+" = "+rhsB+")\n4. Substitute: "+left+" = "+right+"\n5. SI dimensions balanced: "+balanced.left+(numeric?"\n6. Numeric evaluation: left="+numeric.left+", right="+numeric.right+", residual="+numeric.residual:"");
 return {status:"EQUATIONS_COMPOSED_WITH_DIMENSION_CHECK",equation:left+" = "+right,sharedVariable:shared,isolatedExpression:isolated,derivation,dimensions:{sourceA:first,sourceB:second,result:balanced},numeric,residual,classification:"MATHEMATICALLY_DERIVED",limitations:["Algebraic composition is only valid under the supported invertible operations of the symbolic engine.","Dimension balance does not establish physical validity or experimental support.","When numeric values are supplied, they are a point evaluation only."]};
}
function runAutonomousModel(c){
 const dataset=loadDatasets().find(x=>x.id===c.datasetId);
 if(!dataset)throw new Error("datasetId tidak ditemukan pada penyimpanan browser.");
 const engine=window.BeyondLightAutonomousModel;
 if(!engine)throw new Error("Autonomous model browser engine belum dimuat.");
 return engine.explore(dataset,text(c.target,"target"));
}
function runDataset(c){
 const d=obj(c.dataset||loadDatasets().find(x=>x.id===c.datasetId)),headers=Array.isArray(d.headers)?d.headers.map(String):[],rows=Array.isArray(d.rows)?d.rows:[];
 if(!headers.length||rows.length<6)throw new Error("dataset harus menyediakan headers dan sedikitnya 6 rows.");
 const xi=headers.indexOf(text(c.x,"x")),yi=headers.indexOf(text(c.y,"y"));if(xi<0||yi<0||xi===yi)throw new Error("Kolom x dan y harus berbeda dan ada di dataset.");
 const points=rows.slice(0,5000).map((r,i)=>({x:finite(r[xi],"dataset x["+i+"]"),y:finite(r[yi],"dataset y["+i+"]")}));
 const models=searchDatasetModels(points),bestModels=models.slice(0,8);
 return {status:"INTERNAL_DATASET_SCREENING",datasetId:d.id||"user-supplied",rowsAnalyzed:points.length,x:headers[xi],y:headers[yi],models:bestModels,candidateModelsEvaluated:models.length,crossValidation:{folds:Math.min(5,Math.floor(points.length/3)),bestRmse:bestModels[0]?.crossValidationRmse??null,beatsConstantBaseline:Boolean(bestModels[0]?.cvBetterThanConstant)},limitations:["Port browser menerapkan regresi polinomial, logaritmik, resiprokal, eksponensial, dan power-law satu variabel; bukan seluruh feature grammar Java.","Cross-validation memakai dataset yang sama; bukan replikasi independen.","Kecocokan pola bukan hukum fisika atau hubungan kausal."]};
}
function runIntegratedTechnology(c){
 const d=loadDatasets().find(x=>x.id===c.datasetId);if(!d)throw new Error("datasetId tidak ditemukan pada penyimpanan browser.");
 const target=text(c.target,"target"),power=text(c.powerVariable,"powerVariable"),units=Object.fromEntries(String(d.units||"").split(",").map(p=>p.trim().split(":")).filter(p=>p.length===2));
 const analysis=runDataset({dataset:d,x:power,y:target}),linear=analysis.models.find(m=>m.algorithm==="polynomial degree 1");
 const ix=d.headers.indexOf(power),values=d.rows.map(r=>Number(r[ix])),min=Math.min(...values),max=Math.max(...values);
 const reasons=[];
 if(units[target]!=="N")reasons.push("Kolom target harus memiliki satuan N.");
 if(units[power]!=="W")reasons.push("Kolom powerVariable harus memiliki satuan W.");
 if(d.rows.length<20)reasons.push("Sedikitnya 20 baris dataset diperlukan.");
 if(!linear)reasons.push("Model linear satu variabel tidak ditemukan.");
 let applied=false,lowerAtMin=null,lowerAtMax=null;
 if(linear){
  const [intercept,slope]=linear.parameters,cv=linear.crossValidationRmse,base=linear.constantBaselineRmse;
  if(!(slope>0))reasons.push("Kemiringan thrust terhadap power harus positif.");
  if(!(base>0&&linear.cvBetterThanConstant&&(base-cv)/base>=.1))reasons.push("Cross-validation harus mengungguli baseline konstan sedikitnya 10%.");
  lowerAtMin=intercept+slope*min-cv;lowerAtMax=intercept+slope*max-cv;
  if(!(lowerAtMin>0&&lowerAtMax>0))reasons.push("Prediksi thrust dikurangi CV RMSE harus positif pada seluruh rentang daya.");
  applied=reasons.length===0;
 }
 const T=window.BeyondLightTechnologyDesign;if(!T)throw new Error("Technology design browser belum tersedia.");
 const design=T.explore("propulsion.reaction.ideal",{dryMassKg:finite(c.dryMassKg??900,"dryMassKg"),payloadKg:finite(c.payloadKg??100,"payloadKg"),targetDeltaVMs:finite(c.deltaVMs??9000,"deltaVMs"),availablePowerW:finite(c.availablePowerW??100000,"availablePowerW"),coolingCapacityW:finite(c.coolingCapacityW??50000,"coolingCapacityW"),maximumBurnDays:finite(c.maximumBurnDays??180,"maximumBurnDays")});
 let candidates=Array.isArray(design.allCandidates)?design.allCandidates:[];
 if(applied){const [intercept,slope]=linear.parameters,cv=linear.crossValidationRmse;candidates=candidates.filter(x=>x.inputPowerW>=min&&x.inputPowerW<=max&&x.thrustN>=intercept+slope*x.inputPowerW-cv);}
 const designResult={...design,allCandidates:candidates,candidatesEvaluated:candidates.length,withinEnvelope:candidates.filter(x=>x.candidateFeasible).length,empiricalConstraintApplied:applied};
 return {status:"INTEGRATED_MODEL_DESIGN_FEASIBILITY_SCREEN_COMPLETE",modelExploration:analysis,modelApplication:{status:applied?"APPLIED_AS_EMPIRICAL_SCREENING_CONSTRAINT":"NOT_APPLIED_MODEL_GATE_FAILED",applied,checks:{targetUnitIsNewton:units[target]==="N",predictorUnitIsWatt:units[power]==="W",minimumRowsPassed:d.rows.length>=20,oneTermLinearModelFound:Boolean(linear),crossValidationPassed:Boolean(linear&&linear.cvBetterThanConstant&&linear.constantBaselineRmse>0&&(linear.constantBaselineRmse-linear.crossValidationRmse)/linear.constantBaselineRmse>=.1),positiveSlope:Boolean(linear&&linear.parameters[1]>0),observedPowerRangeAvailable:max>min},reasons,observedPowerRangeW:[min,max],lowerPredictedThrustN:[lowerAtMin,lowerAtMax]},designExploration:designResult,candidatesEvaluated:designResult.candidatesEvaluated,candidatesWithinEnvelope:designResult.withinEnvelope,feasibilityEngineAppliedPerCandidate:true,empiricalConstraintApplied:applied,limitations:["Constraint empiris hanya diterapkan pada kandidat dalam rentang daya yang diamati; tidak ada extrapolation.","Korelasi data bukan hukum fisika atau kausalitas; cross-validation satu dataset bukan replikasi independen.","Model browser memakai regresi satu variabel linear, bukan seluruh AutonomousModelExplorer Java."]};
}
async function runOpenDataCycle(question){
 const discovery=await runOpenDataDiscovery(question),imports=[],analyses=[],failures=[];
 for(const record of discovery.records){if(imports.length>=3)break;
  for(const file of record.files||[]){if(imports.length>=3)break;
   if(!/^[A-Za-z0-9._-]{1,180}\.csv$/i.test(file.name)||file.size>2_000_000)continue;
   try{
    const url="https://zenodo.org/api/records/"+encodeURIComponent(record.recordId)+"/files/"+encodeURIComponent(file.name)+"/content";
    const response=await fetch(url,{mode:"cors",credentials:"omit"});if(!response.ok)throw new Error("CSV HTTP "+response.status);
    const csv=await response.text(),metadata={source:"Zenodo: "+record.title,doi:record.doi,license:"",units:""};
    const saved=importDatasetCsv(file.name,csv,metadata),dataset=loadDatasets().find(x=>x.id===saved.id);
    imports.push({recordId:record.recordId,title:record.title,dataset:saved});
    if(dataset&&dataset.headers.length>=2){
     const x=dataset.headers[0],y=dataset.headers[1];
     try{analyses.push({datasetId:saved.id,x,y,result:runDataset({dataset,x,y})});}
     catch(error){failures.push({recordId:record.recordId,file:file.name,reason:String(error.message||error)});}
    }
    break;
   }catch(error){failures.push({recordId:record.recordId,file:file.name,reason:String(error.message||error)});}
  }
 }
 return {status:imports.length?"AUTOMATED_SCREENING_COMPLETE_NOT_A_DISCOVERY":discovery.recordCount?"NO_NUMERIC_CSV_IMPORTED":"NO_OPEN_RECORDS_FOUND",discovery,imports,analyses,failedImports:failures,limitations:["Sumber pencarian hanya Zenodo dan paling banyak tiga CSV berukuran maksimal 2 MB per file.","Kolom pertama dan kedua dipakai untuk screening awal; hasil tidak membuktikan hubungan kausal atau hukum fisika.","Dataset disimpan di localStorage perangkat ini; data tidak tersinkron ke server atau perangkat lain.","Validasi silang internal bukan replikasi independen."]};
}
const REL_C=299792458,REL_G=6.67430e-11;
const zeros=(n,m=n)=>Array.from({length:n},()=>Array(m).fill(0));
function inverse4(m){
 const a=m.map((r,i)=>r.concat([0,0,0,0].map((_,j)=>i===j?1:0)));
 for(let c=0;c<4;c++){let p=c;for(let r=c+1;r<4;r++)if(Math.abs(a[r][c])>Math.abs(a[p][c]))p=r;if(Math.abs(a[p][c])<1e-20)throw new Error("Metric singular.");[a[c],a[p]]=[a[p],a[c]];const d=a[c][c];for(let j=0;j<8;j++)a[c][j]/=d;for(let r=0;r<4;r++)if(r!==c){const f=a[r][c];for(let j=0;j<8;j++)a[r][j]-=f*a[c][j];}}
 return a.map(r=>r.slice(4));
}
function metricAt(model,p,x){
 if(model==="minkowski")return [[-1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]];
 if(model==="schwarzschild"){const mass=finite(p.massKg,"massKg"),r=x[1],rs=2*REL_G*mass/(REL_C*REL_C);if(mass<0||r<=rs||x[2]<=0||x[2]>=Math.PI)throw new Error("Schwarzschild exterior requires M>=0, r>2GM/c², 0<theta<pi.");const f=1-rs/r;return [[-f,0,0,0],[0,1/f,0,0],[0,0,r*r,0],[0,0,0,r*r*Math.sin(x[2])**2]];}
 if(model==="morris-thorne"){const throat=finite(p.throatRadiusM,"throatRadiusM"),r=x[1],theta=x[2];if(throat<=0||r<=throat||theta<=0||theta>=Math.PI)throw new Error("Morris-Thorne exterior requires r>throat and 0<theta<pi.");return [[-1,0,0,0],[0,1/(1-throat*throat/(r*r)),0,0],[0,0,r*r,0],[0,0,0,r*r*Math.sin(theta)**2]];}
 if(model==="alcubierre"){const beta=finite(p.beta,"beta"),radius=finite(p.radiusM,"radiusM"),sigma=finite(p.sigma,"sigma");if(Math.abs(beta)>=1||radius<=0||sigma<=0)throw new Error("Reduced Alcubierre model requires |beta|<1, R>0, sigma>0.");const xx=x[1]-beta*x[0],rr=Math.sqrt(xx*xx+x[2]*x[2]+x[3]*x[3]),f=(Math.tanh(sigma*(rr+radius))-Math.tanh(sigma*(rr-radius)))/(2*Math.tanh(sigma*radius));return [[-1+beta*beta*f*f,-beta*f,0,0],[-beta*f,1,0,0],[0,0,1,0],[0,0,0,1]];}
 throw new Error("Metric model tidak dikenal: "+model);
}
function analyzeMetric(model,p,x,h){
 const g=metricAt(model,p,x),inv=inverse4(g),dg=zeros(4,4*4);
 const derivative=(point)=>{const d=Array.from({length:4},()=>zeros(4));for(let k=0;k<4;k++){const step=h*Math.max(1,Math.abs(point[k])),xp=point.slice(),xm=point.slice();xp[k]+=step;xm[k]-=step;const gp=metricAt(model,p,xp),gm=metricAt(model,p,xm);for(let i=0;i<4;i++)for(let j=0;j<4;j++)d[k][i][j]=(gp[i][j]-gm[i][j])/(2*step);}return d;};
 const dg0=derivative(x),christ=(at)=>{const gi=inverse4(metricAt(model,p,at)),d=derivative(at),gm=Array.from({length:4},()=>zeros(4));for(let a=0;a<4;a++)for(let b=0;b<4;b++)for(let c=0;c<4;c++)for(let l=0;l<4;l++)gm[a][b][c]+=.5*gi[a][l]*(d[b][c][l]+d[c][b][l]-d[l][b][c]);return gm;};
 const gamma=christ(x),dgam=Array.from({length:4},()=>Array.from({length:4},()=>zeros(4)));
 for(let mu=0;mu<4;mu++){const step=h*Math.max(1,Math.abs(x[mu])),xp=x.slice(),xm=x.slice();xp[mu]+=step;xm[mu]-=step;const gp=christ(xp),gm=christ(xm);for(let a=0;a<4;a++)for(let b=0;b<4;b++)for(let c=0;c<4;c++)dgam[mu][a][b][c]=(gp[a][b][c]-gm[a][b][c])/(2*step);}
 const riemann=Array.from({length:4},()=>Array.from({length:4},()=>Array.from({length:4},()=>Array(4).fill(0))));
 for(let a=0;a<4;a++)for(let b=0;b<4;b++)for(let c=0;c<4;c++)for(let d=0;d<4;d++){let v=dgam[c][a][d][b]-dgam[d][a][c][b];for(let e=0;e<4;e++)v+=gamma[a][c][e]*gamma[e][d][b]-gamma[a][d][e]*gamma[e][c][b];riemann[a][b][c][d]=v;}
 const ric=zeros(4,4);for(let b=0;b<4;b++)for(let d=0;d<4;d++)for(let a=0;a<4;a++)ric[b][d]+=riemann[a][b][a][d];
 let scalar=0,maxRicci=0;for(let a=0;a<4;a++)for(let b=0;b<4;b++){scalar+=inv[a][b]*ric[a][b];maxRicci=Math.max(maxRicci,Math.abs(ric[a][b]));}
 const ein=zeros(4,4);for(let a=0;a<4;a++)for(let b=0;b<4;b++)ein[a][b]=ric[a][b]-.5*g[a][b]*scalar;
 return {metric:g,inverse:inv,christoffel:gamma,riemann,ricci:ric,ricciScalar:scalar,einstein:ein,maxAbsRicci:maxRicci,convention:"signature (-+++); finite-difference Riemann/Ricci convention"};
}
function determinant4(m){const a=m.map(r=>r.slice());let det=1;for(let c=0;c<4;c++){let p=c;for(let r=c+1;r<4;r++)if(Math.abs(a[r][c])>Math.abs(a[p][c]))p=r;if(Math.abs(a[p][c])<1e-300)return 0;if(p!==c){[a[c],a[p]]=[a[p],a[c]];det=-det;}const v=a[c][c];det*=v;for(let r=c+1;r<4;r++){const f=a[r][c]/v;for(let j=c+1;j<4;j++)a[r][j]-=f*a[c][j];}}return det;}
function diagnoseMetric(g){
 let sym=true;for(let i=0;i<4;i++)for(let j=0;j<4;j++)if(Math.abs(g[i][j]-g[j][i])>1e-10*Math.max(1,Math.abs(g[i][j])))sym=false;
 const a=g.map(r=>r.slice());
 for(let it=0;it<100;it++){let p=0,q=1,mx=0;for(let i=0;i<4;i++)for(let j=i+1;j<4;j++)if(Math.abs(a[i][j])>mx){mx=Math.abs(a[i][j]);p=i;q=j;}if(mx<1e-14)break;const phi=.5*Math.atan2(2*a[p][q],a[q][q]-a[p][p]),c=Math.cos(phi),sn=Math.sin(phi),app=c*c*a[p][p]-2*sn*c*a[p][q]+sn*sn*a[q][q],aqq=sn*sn*a[p][p]+2*sn*c*a[p][q]+c*c*a[q][q];for(let k=0;k<4;k++)if(k!==p&&k!==q){const ap=c*a[k][p]-sn*a[k][q],aq=sn*a[k][p]+c*a[k][q];a[k][p]=a[p][k]=ap;a[k][q]=a[q][k]=aq;}a[p][p]=app;a[q][q]=aqq;a[p][q]=a[q][p]=0;}
 const eigenvalues=a.map((r,i)=>r[i]),negative=eigenvalues.filter(v=>v< -1e-12).length,positive=eigenvalues.filter(v=>v>1e-12).length,zero=4-negative-positive;
 return {determinant:determinant4(g),eigenvalues,negativeEigenvalues:negative,positiveEigenvalues:positive,nearZeroEigenvalues:zero,symmetric:sym,signatureStatus:negative===1&&positive===3&&zero===0&&sym?"LORENTZIAN_SIGNATURE_MATCH":"SIGNATURE_MISMATCH",limitation:"Jacobi eigenvalue signature screen; absolute threshold is scale-dependent."};
}
function runGeneralRelativity(c){
 const model=String(c.model||"minkowski"),x=Array.isArray(c.coordinates)?c.coordinates.map(Number):[0,10,Math.PI/2,0],h=finite(c.step??1e-4,"step");
 if(x.length!==4||x.some(v=>!Number.isFinite(v))||h<=0)throw new Error("coordinates harus empat angka finite dan step positif.");
 const op=String(c.operation||"analyze");
 if(op==="diagnose"){const g=metricAt(model,c,x);return diagnoseMetric(g);}
 if(op==="analyze"||op==="convergence"||op==="stress-energy"){
  const result=analyzeMetric(model,c,x,h);
  if(op==="analyze")return result;
  if(op==="convergence"){const half=analyzeMetric(model,c,x,h/2);return {step:h,halfStep:h/2,ricciScalarAtStep:result.ricciScalar,ricciScalarAtHalfStep:half.ricciScalar,scalarDifference:Math.abs(result.ricciScalar-half.ricciScalar),assessment:Math.abs(result.ricciScalar-half.ricciScalar)<=1e-10?"SCALAR_STABLE_ABSOLUTE_1E-10":"NUMERICALLY_INCONCLUSIVE",limitation:"Inspect tensor components and step-size stability; scalar convergence alone is insufficient."};}
  const lambda=finite(c.cosmologicalLambdaPerM2??0,"cosmologicalLambdaPerM2"),tol=finite(c.toleranceJm3??1e-9,"toleranceJm3");
  if(tol<0)throw new Error("toleranceJm3 must be nonnegative.");
  const g=result.metric,E=result.einstein,max=Math.max(1e-300,...E.flat());
  for(let i=0;i<4;i++)for(let j=0;j<4;j++)if(i!==j&&(Math.abs(g[i][j])>1e-12||Math.abs(E[i][j])>1e-6*max))throw new Error("Energy-condition reduction hanya mendukung metrik dan tensor Einstein diagonal.");
  if(g[0][0]>=0||g[1][1]<=0||g[2][2]<=0||g[3][3]<=0)throw new Error("Diperlukan diagonal Lorentzian signature (-+++).");
  const factor=Math.pow(REL_C,4)/(8*Math.PI*REL_G),T=zeros(4,4);for(let i=0;i<4;i++)T[i][i]=factor*(E[i][i]+lambda*g[i][i]);
  const rho=T[0][0]/Math.abs(g[0][0]),pressures=[1,2,3].map(i=>T[i][i]/g[i][i]);
  const nec=pressures.every(v=>rho+v>=-tol),wec=rho>=-tol&&nec,sec=nec&&rho+pressures.reduce((a,b)=>a+b,0)>=-tol,dec=rho>=-tol&&pressures.every(v=>rho>=Math.abs(v)-tol);
  return {covariantTensorPa:T,energyDensityJm3:rho,principalPressuresJm3:pressures,nullEnergyCondition:nec,weakEnergyCondition:wec,strongEnergyCondition:sec,dominantEnergyCondition:dec,numericalToleranceJm3:tol,status:"NUMERICAL_REQUIRED_SOURCE_AND_LOCAL_DIAGONAL_ENERGY_CONDITION_SCREEN",convention:"T_ab=(c^4/8piG)(G_ab+Lambda*g_ab); diagonal local frame only",limitations:["Menghitung tensor sumber yang diperlukan oleh metrik; tidak membuktikan materi tersebut ada.","Hanya tipe-I diagonal; Alcubierre off-diagonal ditolak.","Kurvatur dihitung dengan finite differences dan sensitif terhadap step."]};
 }
 if(op==="field-residual"){const g=c.metric,E=c.einstein,T=c.stress;if(!Array.isArray(g)||!Array.isArray(E)||!Array.isArray(T)||[g,E,T].some(a=>a.length!==4||a.some(r=>!Array.isArray(r)||r.length!==4)))throw new Error("metric, einstein, stress harus matriks 4x4.");const coupling=finite(c.coupling,"coupling"),lambda=finite(c.cosmologicalLambdaPerM2??0,"cosmologicalLambdaPerM2");return {residual:E.map((r,i)=>r.map((v,j)=>v+lambda*g[i][j]-coupling*T[i][j])),equation:"G_ab + Lambda*g_ab - coupling*T_ab",status:"FIELD_EQUATION_RESIDUAL_COMPUTED"};}
 if(op==="energy-conditions"){const rho=finite(c.energyDensityJm3,"energyDensityJm3"),p=c.principalPressuresJm3;if(!Array.isArray(p)||p.length!==3||p.some(v=>!Number.isFinite(v)))throw new Error("principalPressuresJm3 harus berisi tiga angka finite.");const tol=finite(c.toleranceJm3??1e-9,"toleranceJm3"),nec=p.every(v=>rho+v>=-tol),wec=rho>=-tol&&nec,sec=nec&&rho+p.reduce((a,b)=>a+b,0)>=-tol,dec=rho>=-tol&&p.every(v=>rho>=Math.abs(v)-tol);return {nullEnergyCondition:nec,weakEnergyCondition:wec,strongEnergyCondition:sec,dominantEnergyCondition:dec,status:"DIAGONAL_TYPE_I_ENERGY_CONDITIONS_EVALUATED",limitation:"Diagonal orthonormal-frame inequalities only; not derived from a metric."};}
 throw new Error("Operasi general-relativity tidak dikenal: "+op);
}
function run(request,pl){
 const c=request.context,w=String(c.workflow||"");
 if(w==="symbolic")return runSymbolic(c);
 if(w==="benchmark")return runBenchmark(c);
 if(w==="feasibility")return runFeasibility(c);
 if(w==="technology-domain")return runTechnology(c);
 if(w==="engineering-calculation")return runEngineering(c);
 if(w==="core-calculation")return runCore(c);
 if(w==="catalog-validation")return runCatalog();
 if(w==="open-data-discovery"||pl.steps[0].engineId==="research.open-data-discovery")return null;
 if(w==="relativity")return runRelativity(c);
 if(w==="uncertainty")return runUncertainty(c);
 if(w==="material-selection")return runMaterialSelection(c);
 if(w==="cross-domain-technology")return runCrossDomain(c);
 if(w==="dataset-analysis")return runDataset(c);
 if(w==="autonomous-model")return runAutonomousModel(c);
 if(w==="equation-composition")return runEquationComposition(c);
 if(w==="integrated-technology")return runIntegratedTechnology(c);
 if(w==="general-relativity")return runGeneralRelativity(c);
 
 
 throw new Error("Workflow belum didukung: "+w);
}
async function dispatch(input){
 const request=createRequest(input),researchPlan=plan(request),started=now(),engineId=researchPlan.steps[0].engineId;
 let result;
 try{
  const output=engineId==="research.open-data-discovery"?await runOpenDataDiscovery(request.question):engineId==="research.open-data-cycle"?await runOpenDataCycle(request.question):run(request,researchPlan);
  if(output===null)throw new Error("Tidak ada hasil yang dapat diproses.");
  result={id:crypto.randomUUID(),requestId:request.id,engineId,status:String(output.status||"COMPLETED"),startedAt:started,completedAt:now(),output,sources:sourceList(output.sources),limitations:output.limitations||[],error:""};
 }catch(e){
  result={id:crypto.randomUUID(),requestId:request.id,engineId,status:"ENGINE_FAILED",startedAt:started,completedAt:now(),output:{},sources:[],limitations:["Langkah gagal sebelum menghasilkan hasil yang dapat digunakan."],error:String(e?.message||e)};
 }
 const failed=result.status.includes("FAILED")||Boolean(result.error);
 const checks={sourceProvenance:result.sources.length?"SOURCE_METADATA_ATTACHED_NOT_INDEPENDENTLY_VERIFIED":"NO_SOURCE_RECORD_ATTACHED",execution:result.status,completedSteps:failed?0:1,plannedSteps:1,independentReplication:"NOT_PERFORMED",experimentalValidation:"NOT_PERFORMED"};
 const evidence={requestId:request.id,classification:failed?"INCOMPLETE_OR_FAILED":engineId==="research.open-data-discovery"?"OPEN_DATA_METADATA_DISCOVERY":engineId==="mathematics.symbolic"?"SYMBOLIC_MATHEMATICAL_ANALYSIS":engineId==="engineering.feasibility-assessment"||engineId==="engineering.technology-domain"?"PRELIMINARY_ENGINEERING_SCREENING":"INTERNAL_ANALYSIS_RESULT",summary:failed?"Workflow gagal atau belum tersedia di browser; jangan simpulkan hasil.":"Hasil berasal dari workflow browser deterministik dengan cakupan terbatas; bukan replikasi independen atau validasi eksperimen.",checks,uncertainty:["Metadata sumber belum diverifikasi independen.","Tidak ada replikasi independen atau validasi eksperimen dari lapisan ini.","Hasil screening tidak membuktikan hukum fisika atau kelayakan perangkat nyata."],limitations:[...(result.limitations||[]),"Planner berbasis aturan deterministik, bukan LLM."]};
 return {request,plan:researchPlan,analysis:result,evidence,availableEngines:Object.keys(routes),answer:{status:"DISABLED",reason:"Tidak ada layanan LLM/backend pada GitHub Pages."},knowledgeRetrieval:{status:"AVAILABLE_VIA_MNEMOS_BROWSER_ADAPTER",sourceOfTruth:"mnemos-RLI:Knowledge"},runtime:"STATIC_BROWSER_ONLY"};
}
function listEngines(){return Object.entries(routes).map(([workflow,id])=>({workflow,id,description:descriptions[id]}));}
window.BeyondLightResearchCore={createRequest,plan,dispatch,listEngines,runSymbolic,runBenchmark,runFeasibility,runTechnology,runEngineering,runCore,runRelativity,runUncertainty,runMaterialSelection,runCrossDomain,runDataset,runAutonomousModel,runEquationComposition,runIntegratedTechnology,runOpenDataCycle,runGeneralRelativity,importDatasetCsv,listDatasets:()=>loadDatasets().map(({id,filename,headers,rows,importedAt,source,doi,units})=>({id,filename,variables:headers,rows:rows.length,importedAt,source,doi,units}))};
})();
