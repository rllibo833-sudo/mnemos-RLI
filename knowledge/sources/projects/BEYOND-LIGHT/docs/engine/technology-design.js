/* Browser translation of TechnologyDesignEngine and its four registered domains.
 * Java remains canonical. The browser implementation is deterministic and bounded.
 */
(() => {
"use strict";
const G0=9.80665, SIGMA=5.670374419e-8;
const STATUS=window.BeyondLightFeasibility?.STATUS||{};
const finite=(...v)=>v.every(Number.isFinite);
const val=(r,k)=>{const v=r.inputs[k];if(!Number.isFinite(v))throw new Error("Input tidak finite: "+k);return v;};
const num=(o,k)=>{const v=o[k];if(typeof v!=="number"||!Number.isFinite(v))throw new Error("Kandidat kehilangan nilai finite: "+k);return v;};
const grid=(a,b,n)=>n===1?[a]:Array.from({length:n},(_,i)=>a+(b-a)*i/(n-1));
const stepCount=(n,label)=>{if(!Number.isInteger(n)||n<1||n>30)throw new Error(label+" harus bilangan bulat 1–30.");return n;};
const objective=(metric,direction)=>({metric,direction});
const domains={
 "propulsion.reaction.ideal":{
  title:"Pendorong reaksi ideal",model:"Persamaan roket ideal, aliran momentum, daya, dan screening FeasibilityEngine.",
  defaults:{dryMassKg:800,payloadKg:200,targetDeltaVMs:3000,availablePowerW:1e9,coolingCapacityW:1e8,maximumBurnDays:180},
  fields:[
   ["dryMassKg","Massa kering","kg",800,0,1e8],["payloadKg","Muatan","kg",200,0,1e8],["targetDeltaVMs","Target perubahan kecepatan","m/s",3000,0,1e7],
   ["availablePowerW","Daya tersedia","W",1e9,0,1e15],["coolingCapacityW","Kapasitas pendinginan","W",1e8,0,1e15],["maximumBurnDays","Durasi pembakaran maksimum","hari",180,0,36500]
  ],
  objectives:[objective("propellantKg","MINIMIZE"),objective("inputPowerW","MINIMIZE"),objective("burnDurationDays","MINIMIZE")],sortMetric:"inputPowerW",
  generate(r){
   const dry=val(r,"dryMassKg"),payload=val(r,"payloadKg"),dv=val(r,"targetDeltaVMs"),power=val(r,"availablePowerW"),heat=val(r,"coolingCapacityW"),days=val(r,"maximumBurnDays");
   if(dry<=0||payload<0||dv<=0||power<=0||heat<0||days<=0||dry>1e8||payload>1e8||dv>1e7||power>1e15||heat>1e15||days>36500)throw new Error("Batas misi di luar rentang eksplorasi.");
   const durations=[1,3,7,30,90,180].filter(x=>x<=days);durations.push(days);
   return [...new Set(durations)].flatMap(burnDurationDays=>[250,450,900,1500,3000,6000].flatMap(specificImpulseS=>[.5,.7,.85,.95].map(efficiency=>({specificImpulseS,efficiency,burnDurationDays}))));
  },
  evaluate(r,c){
   const dry=val(r,"dryMassKg"),payload=val(r,"payloadKg"),dv=val(r,"targetDeltaVMs"),maxPower=val(r,"availablePowerW"),maxHeat=val(r,"coolingCapacityW");
   const isp=num(c,"specificImpulseS"),eta=num(c,"efficiency"),days=num(c,"burnDurationDays"),mf=dry+payload,ve=isp*G0,ratio=dv/ve;
   if(ratio>700)throw new Error("rocket equation overflow limit");
   const prop=mf*Math.expm1(ratio),wet=mf+prop,duration=days*86400,mdot=prop/duration,thrust=mdot*ve,pkin=.5*mdot*ve*ve,pin=pkin/eta,heat=pin-pkin;
   if(!finite(prop,wet,mdot,thrust,pkin,pin,heat))throw new Error("hasil nonfinite");
   const assessment=window.BeyondLightFeasibilityAssessment?.assess({family:"electric",dryKg:dry,payloadKg:payload,dv,isp,thrust,efficiency:eta,duration,availablePowerW:maxPower,coolingW:maxHeat,assembly:null});
   const powerPass=pin<=maxPower,heatPass=heat<=maxHeat;
   const crossProp=mf*Math.exp(ratio)-mf,crossMdot=prop/duration,crossThrust=crossMdot*ve,crossPkin=.5*crossMdot*ve*ve,crossPin=crossPkin/eta;
   const massResidual=prop-crossProp,momentumResidual=thrust-crossThrust,energyResidual=pin-crossPkin-heat;
   const equationCheck=Math.abs(massResidual)<=1e-8*Math.max(1,prop)&&Math.abs(momentumResidual)<=1e-9*Math.max(1,thrust)&&Math.abs(energyResidual)<=1e-9*Math.max(1,pin);
   const feasible=powerPass&&heatPass&&equationCheck;
   return {feasible,metrics:{specificImpulseS:isp,efficiency:eta,burnDurationDays:days,propellantKg:prop,initialMassKg:wet,thrustN:thrust,massFlowKgS:mdot,exhaustVelocityMS:ve,inputPowerW:pin,idealizedWasteHeatW:heat,powerConstraintPass:powerPass,heatConstraintPass:heatPass,equationCrossChecksPass:equationCheck,feasibilityClassification:assessment?.overallClassification||"NOT_ASSESSED",engineeringStage:assessment?.engineering?.status||"NOT_ASSESSED",screenStatus:feasible?"WITHIN_USER_ENVELOPE_SCREEN":"OUTSIDE_USER_ENVELOPE_OR_CHECK_FAILED"},checks:{powerConstraintPass:powerPass,heatConstraintPass:heatPass,equationCrossChecksPass:equationCheck}};
  },
  equations:["vₑ = Isp × g₀","m propelan = m akhir × (e^(Δv/vₑ) − 1)","F = ṁ × vₑ","P masuk = ½ × ṁ × vₑ² / efisiensi"],
  sources:[{title:"NASA Glenn — Ideal Rocket Equation",url:"https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/ideal-rocket-equation/"}],
  limitations:["Rentang Isp dan efisiensi adalah grid asumsi, bukan kurva performa mesin terukur.","Lolos hanya berarti memenuhi batas daya/panas dan pemeriksaan persamaan ideal.","Geometri ruang bakar/nozel, material, kontrol, manufaktur, eksperimen, dan lintasan tidak divalidasi.","Constraint performa empiris opsional pada facade Java belum disertakan dalam port browser."]
 },
 "structures.member.envelope":{
  title:"Struktur batang / prismatic member",model:"Tegangan von Mises, tekuk Euler elastis, dan penyapuan skala penampang.",
  defaults:{tensileLoadN:100000,compressiveLoadN:50000,shearLoadN:20000,baseAreaM2:.01,baseShearAreaM2:.01,baseSecondMomentM4:8.33e-6,memberLengthM:2,youngModulusPa:110.5e9,yieldStrengthPa:800e6,densityKgM3:4430,requiredSafetyFactor:1.5,effectiveLengthFactor:1,minSectionScale:.5,maxSectionScale:3,sectionScaleSteps:15},
  fields:[
   ["tensileLoadN","Beban tarik","N",100000,0,1e12],["compressiveLoadN","Beban tekan","N",50000,0,1e12],["shearLoadN","Beban geser","N",20000,0,1e12],
   ["baseAreaM2","Luas penampang dasar","m²",.01,0,1e4],["baseShearAreaM2","Luas geser dasar","m²",.01,0,1e4],["baseSecondMomentM4","Momen inersia area dasar","m⁴",8.33e-6,0,1e4],
   ["memberLengthM","Panjang batang","m",2,0,1e6],["youngModulusPa","Modulus Young","Pa",110.5e9,0,1e15],["yieldStrengthPa","Kekuatan luluh input","Pa",800e6,0,1e15],
   ["densityKgM3","Densitas","kg/m³",4430,0,1e6],["requiredSafetyFactor","Faktor keselamatan wajib","—",1.5,0,1e4],["effectiveLengthFactor","Faktor panjang efektif K","—",1,0,1e4],
   ["minSectionScale","Skala penampang minimum","—",.5,0,1e4],["maxSectionScale","Skala penampang maksimum","—",3,0,1e4],["sectionScaleSteps","Jumlah variasi skala","langkah",15,1,30]
  ],
  objectives:[objective("estimatedMemberMassKg","MINIMIZE"),objective("minimumSafetyMargin","MAXIMIZE")],sortMetric:"estimatedMemberMassKg",
  generate(r){
   const keys=["tensileLoadN","compressiveLoadN","shearLoadN","baseAreaM2","baseShearAreaM2","baseSecondMomentM4","memberLengthM","youngModulusPa","yieldStrengthPa","densityKgM3","requiredSafetyFactor","effectiveLengthFactor","minSectionScale","maxSectionScale"];
   const v=keys.map(k=>val(r,k));if(!finite(...v)||v.slice(0,3).some(x=>x<0)||v.slice(3,12).some(x=>x<=0)||v[13]<v[12])throw new Error("Beban, material, geometri, atau rentang skala struktur tidak valid.");
   const n=stepCount(val(r,"sectionScaleSteps"),"Jumlah langkah skala");
   return grid(v[12],v[13],n).map(sectionScale=>({sectionScale}));
  },
  evaluate(r,c){
   const scale=num(c,"sectionScale");if(scale<=0)throw new Error("Skala harus positif.");
   const area=val(r,"baseAreaM2")*scale,shearArea=val(r,"baseShearAreaM2")*scale,I=val(r,"baseSecondMomentM4")*scale*scale,L=val(r,"memberLengthM"),E=val(r,"youngModulusPa"),yieldPa=val(r,"yieldStrengthPa"),required=val(r,"requiredSafetyFactor"),K=val(r,"effectiveLengthFactor");
   const stress=window.BeyondLightFeasibility.stress(val(r,"tensileLoadN"),val(r,"compressiveLoadN"),val(r,"shearLoadN"),area,shearArea,L,E,yieldPa,required);
   const critical=Math.PI**2*E*I/(K*L)**2,compression=val(r,"compressiveLoadN"),bucklingSf=compression===0?Infinity:critical/compression,margin=critical-compression*required;
   const stressPass=stress.status===STATUS.ENG_OK,bucklingPass=Number.isFinite(critical)&&margin>=0,feasible=stressPass&&bucklingPass,mass=val(r,"densityKgM3")*area*L;
   const stressSf=stress.safetyFactor==null?NaN:stress.safetyFactor,stressMargin=Number.isFinite(stressSf)?stressSf-required:NaN,minMargin=Number.isFinite(stressMargin)?Math.min(stressMargin,bucklingSf-required):NaN;
   return {feasible,metrics:{sectionScale:scale,areaM2:area,shearAreaM2:shearArea,secondMomentM4:I,estimatedMemberMassKg:mass,vonMisesStressPa:stress.vonMisesPa,stressSafetyFactor:stressSf,stressMargin,stressStatus:stress.status,criticalEulerLoadN:critical,appliedCompressionLoadN:compression,bucklingSafetyFactor:bucklingSf,bucklingMarginN:margin,minimumSafetyMargin:minMargin,unknowns:stress.unknowns,screenStatus:feasible?"WITHIN_STRUCTURAL_MEMBER_ENVELOPE":"OUTSIDE_STRUCTURAL_ENVELOPE_OR_MISSING_DATA"},checks:{stressCheck:stress.status,stressSafetyFactorPass:stressPass,eulerBucklingPass:bucklingPass,requiredSafetyFactor:required}};
  },
  equations:["A = A dasar × skala; I = I dasar × skala²","σ von Mises = √[(F tarik/A − F tekan/A)² + 3(F geser/A geser)²]","P kritis Euler = π²EI/(KL)²"],
  sources:[{title:"Model rekayasa deterministik internal",url:""}],
  limitations:["Penyaringan batang saja; tidak mencakup sambungan, tekuk lokal, fatigue, fracture, getaran, impak, atau FEA.","Skala mengasumsikan bentuk penampang serupa; area linear dan momen inersia kuadrat terhadap skala.","Euler mengasumsikan kolom lurus, elastis, ideal; imperfection dan tekuk inelastis tidak dimodelkan.","Kekuatan luluh dan semua input material adalah nilai yang dimasukkan pengguna, bukan otomatis data terverifikasi."]
 },
 "thermal.management.steady-state":{
  title:"Manajemen termal steady-state",model:"Konduksi, radiasi Stefan–Boltzmann, dan margin kapasitas pendinginan.",
  defaults:{conductivityWmK:15,areaM2:2,deltaTemperatureK:30,thicknessM:.05,emissivity:.8,radiatorTemperatureK:500,ambientTemperatureK:300,requiredHeatW:10000,minCoolingCapacityW:20000,maxCoolingCapacityW:60000,coolingCapacitySteps:12},
  fields:[
   ["conductivityWmK","Konduktivitas termal","W/(m·K)",15,0,1e6],["areaM2","Luas perpindahan panas","m²",2,0,1e8],["deltaTemperatureK","Selisih suhu konduksi","K",30,0,1e6],["thicknessM","Ketebalan jalur konduksi","m",.05,0,1e6],
   ["emissivity","Emisivitas","0–1",.8,0,1],["radiatorTemperatureK","Suhu radiator","K",500,0,1e5],["ambientTemperatureK","Suhu lingkungan","K",300,0,1e5],["requiredHeatW","Beban panas sistem","W",10000,0,1e15],
   ["minCoolingCapacityW","Kapasitas pendinginan minimum","W",20000,0,1e15],["maxCoolingCapacityW","Kapasitas pendinginan maksimum","W",60000,0,1e15],["coolingCapacitySteps","Jumlah variasi kapasitas","langkah",12,1,30]
  ],
  objectives:[objective("coolingCapacityW","MINIMIZE"),objective("marginW","MAXIMIZE")],sortMetric:"coolingCapacityW",
  generate(r){
   const k=val(r,"conductivityWmK"),a=val(r,"areaM2"),dt=val(r,"deltaTemperatureK"),t=val(r,"thicknessM"),e=val(r,"emissivity"),tr=val(r,"radiatorTemperatureK"),ta=val(r,"ambientTemperatureK"),heat=val(r,"requiredHeatW"),lo=val(r,"minCoolingCapacityW"),hi=val(r,"maxCoolingCapacityW"),n=stepCount(val(r,"coolingCapacitySteps"),"Jumlah langkah pendinginan");
   if(!finite(k,a,dt,t,e,tr,ta,heat,lo,hi)||k<=0||a<=0||dt<=0||t<=0||e<0||e>1||ta<0||tr<=ta||heat<0||lo<=0||hi<lo)throw new Error("Batas pencarian termal tidak valid.");
   return grid(lo,hi,n).map(coolingCapacityW=>({coolingCapacityW}));
  },
  evaluate(r,c){
   const cap=num(c,"coolingCapacityW"),k=val(r,"conductivityWmK"),a=val(r,"areaM2"),dt=val(r,"deltaTemperatureK"),t=val(r,"thicknessM"),e=val(r,"emissivity"),tr=val(r,"radiatorTemperatureK"),ta=val(r,"ambientTemperatureK"),heat=val(r,"requiredHeatW");
   const conduction=k*a*dt/t,radiation=e*SIGMA*a*(tr**4-ta**4),rejected=conduction+radiation,margin=cap-rejected-heat,status=cap===0?STATUS.MISSING:(margin>=0?STATUS.ENG_OK:STATUS.ENG_BAD),feasible=status===STATUS.ENG_OK&&Number.isFinite(margin)&&margin>=0;
   return {feasible,metrics:{coolingCapacityW:cap,conductionW:conduction,radiationW:radiation,netRejectedW:rejected,requiredHeatW:heat,marginW:margin,feasibilityClassification:status,unknowns:cap===0?["cooling system capacity not supplied"]:[],screenStatus:feasible?"WITHIN_STEADY_STATE_THERMAL_ENVELOPE":"OUTSIDE_THERMAL_ENVELOPE_OR_MISSING_DATA"},checks:{coolingCapacitySupplied:cap>0,thermalMarginNonnegative:margin>=0,thermalModelStatus:status}};
  },
  equations:["Q konduksi = k × A × ΔT / tebal","Q radiasi = ε × σSB × A × (T radiator⁴ − T lingkungan⁴)","Margin = kapasitas pendinginan − Q konduksi − Q radiasi − beban panas"],
  sources:[{title:"Stefan–Boltzmann constant (NIST CODATA)",url:"https://physics.nist.gov/cgi-bin/cuu/Value?sigma%7Csearch_for=stefan+boltzmann"}],
  limitations:["Model steady-state; tidak menghitung transien, distribusi temperatur 3D, aliran coolant, heat-pipe, atau kontrol.","Konduktivitas, geometri, emisivitas, suhu, beban panas, dan kapasitas adalah input, bukan hasil pengukuran.","Tidak mencakup view factor, shielding, massa radiator, konsumsi daya, kontak termal, atau manufaktur."]
 },
 "energy.storage.envelope":{
  title:"Penyimpanan energi ideal",model:"Energi tersimpan, densitas energi spesifik, efisiensi konversi; tanpa model kimia.",
  defaults:{energyJ:3.6e9,minEnergyDensityJkg:5e5,maxEnergyDensityJkg:2e6,energyDensitySteps:8,minEfficiency:.7,maxEfficiency:.95,efficiencySteps:8,maximumStorageMassKg:10000,maximumInputEnergyJ:5e9},
  fields:[
   ["energyJ","Energi yang harus disalurkan","J",3.6e9,0,1e18],["minEnergyDensityJkg","Densitas energi minimum","J/kg",5e5,0,1e15],["maxEnergyDensityJkg","Densitas energi maksimum","J/kg",2e6,0,1e15],["energyDensitySteps","Variasi densitas energi","langkah",8,1,30],
   ["minEfficiency","Efisiensi minimum","0–1",.7,0,1],["maxEfficiency","Efisiensi maksimum","0–1",.95,0,1],["efficiencySteps","Variasi efisiensi","langkah",8,1,30],["maximumStorageMassKg","Batas massa penyimpanan (0 = tanpa batas)","kg",10000,0,1e12],["maximumInputEnergyJ","Batas energi input (0 = tanpa batas)","J",5e9,0,1e20]
  ],
  objectives:[objective("minimumStorageMassKg","MINIMIZE"),objective("requiredInputEnergyJ","MINIMIZE"),objective("conversionLossJ","MINIMIZE")],sortMetric:"minimumStorageMassKg",
  generate(r){
   const energy=val(r,"energyJ"),lo=val(r,"minEnergyDensityJkg"),hi=val(r,"maxEnergyDensityJkg"),emin=val(r,"minEfficiency"),emax=val(r,"maxEfficiency"),mass=val(r,"maximumStorageMassKg"),input=val(r,"maximumInputEnergyJ"),ns=stepCount(val(r,"energyDensitySteps"),"Variasi densitas"),ne=stepCount(val(r,"efficiencySteps"),"Variasi efisiensi");
   if(!finite(energy,lo,hi,emin,emax,mass,input)||energy<=0||lo<=0||hi<lo||hi>1e15||emin<=0||emax>1||emax<emin||mass<0||input<0)throw new Error("Batas penyimpanan energi tidak valid.");
   return grid(lo,hi,ns).flatMap(energyDensityJkg=>grid(emin,emax,ne).map(efficiency=>({energyDensityJkg,efficiency})));
  },
  evaluate(r,c){
   const energy=val(r,"energyJ"),density=num(c,"energyDensityJkg"),eff=num(c,"efficiency");if(energy<0||density<=0||eff<=0||eff>1)throw new Error("Parameter energi tidak valid.");
   const input=energy/eff,loss=input-energy,mass=energy/density,massLimit=val(r,"maximumStorageMassKg"),inputLimit=val(r,"maximumInputEnergyJ"),massPass=massLimit===0||mass<=massLimit,inputPass=inputLimit===0||input<=inputLimit,residual=input-energy-loss,balance=Math.abs(residual)<=1e-10*Math.max(1,input),feasible=massPass&&inputPass&&balance;
   return {feasible,metrics:{energyDensityJkg:density,efficiency:eff,deliveredEnergyJ:energy,minimumStorageMassKg:mass,requiredInputEnergyJ:input,conversionLossJ:loss,massConstraintPass:massPass,inputEnergyConstraintPass:inputPass,energyBalancePass:balance,feasibilityClassification:STATUS.MISSING||"INSUFFICIENT_DATA",screenStatus:feasible?"WITHIN_USER_ENVELOPE_SCREEN":"OUTSIDE_USER_ENVELOPE_OR_CHECK_FAILED"},checks:{massConstraintPass:massPass,inputEnergyConstraintPass:inputPass,energyBalancePass:balance}};
  },
  equations:["Massa minimum = energi tersalur / densitas energi","Energi input = energi tersalur / efisiensi","Rugi konversi = energi input − energi tersalur"],
  sources:[{title:"Batas densitas energi dan efisiensi yang dimasukkan pengguna",url:""}],
  limitations:["Model ini tidak memilih baterai, kapasitor, fuel cell, atau kimia tertentu.","Densitas energi dan efisiensi adalah asumsi pencarian, bukan properti perangkat tervalidasi.","Tidak menghitung power delivery, C-rate, umur siklus, thermal behavior, packaging, kontrol, keselamatan, atau manufaktur."]
 }
};
function dominates(a,b,objectives){let strict=false;for(const o of objectives){const av=num(a,o.metric),bv=num(b,o.metric);if(o.direction==="MINIMIZE"){if(av>bv)return false;if(av<bv)strict=true;}else{if(av<bv)return false;if(av>bv)strict=true;}}return strict;}
function explore(domainId,inputs){
 const d=domains[domainId];if(!d)throw new Error("Domain desain tidak dikenal.");
 const request={inputs};const proposals=d.generate(request),all=[];let invalid=0;
 proposals.forEach((proposal,index)=>{try{const ev=d.evaluate(request,proposal),candidate={...proposal,...ev.metrics,candidateFeasible:ev.feasible,assessmentChecks:ev.checks,candidateId:"K-"+String(index+1).padStart(3,"0")};all.push(candidate);}catch(e){invalid++;}});
 const passing=all.filter(x=>x.candidateFeasible),front=passing.filter(a=>!passing.some(b=>a!==b&&dominates(b,a,d.objectives)));
 front.sort((a,b)=>num(a,d.sortMetric)-num(b,d.sortMetric));
 return {domainId,title:d.title,model:d.model,inputs:{...inputs},candidatesGenerated:proposals.length,candidatesEvaluated:all.length,invalidOrUnsolvableCandidates:invalid,withinEnvelope:passing.length,paretoCandidates:front.slice(0,20),allCandidates:all,objectives:d.objectives,sortMetric:d.sortMetric,equations:d.equations,sources:d.sources,limitations:d.limitations,status:passing.length?"CANDIDATE_DESIGNS_WITHIN_MODEL_ENVELOPE":"NO_DESIGN_WITHIN_GIVEN_ENVELOPE",scope:"Browser translation of the four registered Java domains and shared TechnologyDesignEngine; model screening only."};
}
window.BeyondLightTechnologyDesign={domains,explore};
})();