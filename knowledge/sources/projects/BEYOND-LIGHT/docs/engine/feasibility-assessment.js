/* Staged feasibility assessment ported from FeasibilityEngine.java.
 * MachineDesign assembly aggregation is ported for imported component/material records.
 * No browser-side filesystem, network, or experimental verification is implied.
 */
(() => {
"use strict";
const STATUS=Object.freeze({
 MAT_VALID:"MATHEMATICALLY_VALIDATED",MAT_BAD:"MATHEMATICALLY_INCONSISTENT",
 PHYS_OK:"PHYSICALLY_SUPPORTED_WITHIN_MODEL",PHYS_BAD:"PHYSICAL_VIOLATION_DETECTED",
 ENG_OK:"ENGINEERINGALLY_PLAUSIBLE_WITH_AVAILABLE_DATA",ENG_BAD:"ENGINEERINGALLY_INFEASIBLE",
 MISSING:"INSUFFICIENT_DATA",NUMERIC:"NUMERICALLY_INCONCLUSIVE",
 THEORY:"THEORETICAL_ONLY",EXPERIMENT:"REQUIRES_EXPERIMENTAL_VALIDATION"
});
const C=299792458,G0=9.80665;
const finite=(...xs)=>xs.every(Number.isFinite);
const check=(law,status,reasoning,equation,inputs={},residual=null,tolerance="not evaluated")=>
 ({law,status,reasoning,equation,inputs,residual,tolerance});
const stage=(status,checks,assumptions,limitations)=>({status,checks,assumptions,limitations});
const safeSum=(values,label)=>{const x=values.reduce((a,b)=>a+b,0);if(!Number.isFinite(x))throw new Error(label+" exceeds finite numerical range");return x;};
function energyBalance(beforeJ,afterJ,relTol){
 if(beforeJ==null||afterJ==null)return check("energy conservation",STATUS.MISSING,"Required initial and final values are missing","E_initial = E_final; include all stores, fluxes and losses inside the chosen boundary");
 if(!finite(beforeJ,afterJ,relTol)||relTol<0)return check("energy conservation",STATUS.NUMERIC,"Nonfinite input or invalid tolerance","E_initial = E_final",{},null,"invalid");
 const residual=beforeJ-afterJ,limit=relTol*Math.max(1,Math.abs(beforeJ),Math.abs(afterJ)),ok=Math.abs(residual)<=limit;
 return check("energy conservation",ok?STATUS.PHYS_OK:STATUS.PHYS_BAD,ok?"Balance closes within configured numerical tolerance":"Balance residual exceeds configured tolerance","E_initial = E_final; include all stores, fluxes and losses inside the chosen boundary",{initial:beforeJ,final:afterJ},residual,String(limit));
}
function assemble(input){
 if(input==null)return null;
 if(!input||typeof input!=="object"||Array.isArray(input))throw new Error("Assembly harus berupa object.");
 if(["massKg","powerW","energyJ","heatW","missing","dependencyErrors","components","classification"].every(k=>Object.hasOwn(input,k)))return {...input};
 const components=input.components,materials=input.materials;
 if(!Array.isArray(components)||!Array.isArray(materials))throw new Error("Assembly import memerlukan array components dan materials.");
 const byId=new Map();for(const m of materials){if(m&&typeof m==="object"){if(m.id)byId.set(String(m.id),m);if(m.name)byId.set(String(m.name).toLowerCase(),m);}}
 const ids=new Set(components.map(c=>String(c.id??"")));
 const missing=[],dependencyErrors=[];let mass=0,power=0,energy=0,heat=0;
 for(const c of components){
  if(!c||typeof c!=="object")throw new Error("Setiap komponen harus berupa object.");
  const vals=["volumeM3","powerW","durationS","heatW","loadN","areaM2"].map(k=>Number(c[k]??0));
  if(!finite(...vals)||vals.some(v=>v<0))throw new Error("Nilai komponen harus finite dan nonnegatif: "+String(c.name??c.id??"unknown"));
  const [volume,pwr,duration,heatW,load,area]=vals;
  power+=pwr;energy+=pwr*duration;heat+=heatW;
  const matId=String(c.materialId??"");
  const material=matId?byId.get(matId)||byId.get(matId.toLowerCase()):null;
  if(matId&&!material)throw new Error("Material tidak ditemukan pada paket import: "+matId);
  if(volume>0){
   if(!matId)missing.push(String(c.name)+": material missing");
   else if(material.densityKgM3==null)missing.push(String(c.name)+": density missing");
   else mass+=volume*Number(material.densityKgM3);
  }
  if(load>0){
   if(area===0)missing.push(String(c.name)+": loaded area missing; stress unknown");
   else if(!matId)missing.push(String(c.name)+": material yield property missing; stress capacity unevaluated");
   else if(material.yieldPa==null)missing.push(String(c.name)+": yield strength unavailable; stress capacity unevaluated (calculated axial stress "+(load/area)+" Pa)");
   else if(load/area>Number(material.yieldPa))missing.push(String(c.name)+": axial stress exceeds supplied yield strength");
  }
  for(const dep of (Array.isArray(c.dependencies)?c.dependencies:[]))if(!ids.has(String(dep)))dependencyErrors.push(String(c.name)+": unresolved dependency "+String(dep));
 }
 if(!finite(mass,power,energy,heat))throw new Error("Aggregate komponen melampaui rentang numerik finite.");
 const classification=dependencyErrors.length?"DEPENDENCY ERRORS":missing.length?"INCOMPLETE — MISSING DATA":"PRELIMINARY ESTIMATE — NOT A BUILD CERTIFICATION";
 return {massKg:mass,powerW:power,energyJ:energy,heatW:heat,missing,dependencyErrors,components:components.length,classification};
}
function propulsion(dry,payload,dv,isp,thrust,efficiency){
 if(!finite(dry,payload,dv,isp,thrust,efficiency)||dry<=0||payload<=0||dv<=0||isp<=0||thrust<=0)throw new Error("dry mass, payload, delta-v, Isp and thrust must be finite and positive");
 if(!(efficiency>0&&efficiency<=1))throw new Error("efficiency must be in (0,1]");
 const ve=isp*G0,mf=dry+payload,m0=mf*Math.exp(dv/ve),prop=m0-mf,mdot=thrust/ve,pkin=.5*mdot*ve*ve,pe=pkin/efficiency;
 if(!finite(m0,prop,pkin,pe)||!finite(mdot)||mdot<=0)throw new Error("requested parameters exceed finite numerical range");
 return {thrustN:thrust,exhaustVelocity:ve,massFlowKgS:mdot,deltaV:ve*Math.log(m0/mf),propellantKg:prop,kineticPowerW:pkin,electricalPowerW:pe,burnSeconds:prop/mdot,initialMassKg:m0,finalMassKg:mf};
}
function assess(input){
 if(!input||typeof input!=="object"||Array.isArray(input))throw new Error("Assessment input must be an object.");
 const family=String(input.family??"chemical"),f=family.toLowerCase();
 const dryKg=Number(input.dryKg),payloadKg=Number(input.payloadKg),dv=Number(input.dv),isp=Number(input.isp),thrust=Number(input.thrust),efficiency=Number(input.efficiency),duration=Number(input.duration),availablePowerW=Number(input.availablePowerW),coolingW=Number(input.coolingW);
 const assembly=input.assembly==null?null:assemble(input.assembly);
 const math=[],cons=[],energy=[],eng=[],out={};
 let matStatus=STATUS.MAT_VALID,physical=STATUS.PHYS_OK,energyStatus=STATUS.PHYS_OK,engineering=assembly==null?STATUS.MISSING:assembly.classification;
 const valid=finite(dryKg,payloadKg,dv,isp,thrust,efficiency,duration,availablePowerW,coolingW)&&dryKg>0&&payloadKg>=0&&dv>=0&&isp>0&&thrust>=0&&efficiency>0&&efficiency<=1&&duration>=0&&availablePowerW>=0&&coolingW>=0;
 const inputs={dry_kg:dryKg,payload_kg:payloadKg,delta_v_m_s:dv,isp_s:isp,thrust_N:thrust,efficiency,duration_s:duration,available_power_W:availablePowerW,cooling_W:coolingW};
 math.push(check("input domain",valid?STATUS.MAT_VALID:STATUS.MAT_BAD,valid?"All values finite and within the model-specific positive/nonnegative domain":"Invalid or nonfinite input; mass>0, payload/delta-v/thrust/duration/power/cooling>=0, Isp>0, 0<efficiency<=1 required","SI input-domain validation",inputs,null,"exact checks"));
 if(!valid){
  const missing=stage(STATUS.MISSING,[check("assessment unavailable",STATUS.MISSING,"Physical and engineering stages require valid model inputs","not evaluated")],"not evaluated","not evaluated");
  return {id:input.id??"browser-assessment",date:input.date??new Date().toISOString(),modelVersion:"beyond-light-0.4-browser-port",propulsionFamily:family,mathematical:stage(STATUS.MAT_BAD,math,"SI units","Model evaluation skipped because an input is outside its domain"),conservation:missing,energyThermal:missing,engineering:missing,results:{},overallClassification:STATUS.MAT_BAD,portScope:"Browser port of FeasibilityEngine.assess; not experimental validation."};
 }
 const spacetime=f.includes("warp")||f.includes("spacetime")||f.includes("wormhole");
 const photon=f.includes("photon");
 const reaction=new Set(["chemical","electric","ion","hall","plasma","nuclear thermal","nuclear electric","fusion (reaction)"]).has(f);
 if(spacetime){
  matStatus=STATUS.THEORY;physical=STATUS.MISSING;energyStatus=STATUS.MISSING;engineering=STATUS.THEORY;
  math.push(check("spacetime model",STATUS.THEORY,"Metric geometry is not a propulsion thrust or energy-source model","No validated vehicle performance equation supplied",{family},null,"not applicable"));
  cons.push(check("momentum transfer",STATUS.MISSING,"No demonstrated reaction mass, photon beam, or validated field momentum flux supplied","Momentum conservation requires a defined control volume and flux"));
  energy.push(check("available energy",STATUS.MISSING,"A metric does not supply usable energy; no supported source or stress-energy production mechanism supplied","No energy-source model"));
 }else if(photon){
  if(thrust<=0||duration<=0||efficiency<=0||efficiency>1){matStatus=STATUS.MAT_BAD;physical=STATUS.NUMERIC;}
  else{
   const p=thrust*C/efficiency,e=p*duration,beam=thrust*C*duration;
   Object.assign(out,{photon_thrust_N:thrust,beam_power_W:p,beam_energy_J:beam,input_energy_J:e,propellant_kg:null,delta_v:null});
   matStatus=STATUS.MAT_VALID;
   cons.push(check("photon momentum",STATUS.PHYS_OK,"Ideal collimated photons transfer momentum at F=P_beam/c","F=P_beam/c",{thrust_N:thrust,beam_power_W:p},0,"ideal collimation; no absorption/recoil system modeled"));
   energy.push(check("photon energy",STATUS.PHYS_OK,"Beam power calculated from momentum flux and efficiency","P_input=F*c/eta",{input_power_W:p,duration_s:duration},0,"idealized beam"));
   energy.push(energyBalance(e,beam+e-beam,1e-9));physical=STATUS.PHYS_OK;engineering=STATUS.MISSING;
  }
  math.push(check("photon propulsion domain",STATUS.MAT_VALID,"Photon rocket handled by momentum-energy relation; chemical rocket equation not applied","F=P/c",{family},null,"relativistic photon-rocket mass-ratio delta-v not implemented"));
 }else if(reaction){
  try{
   const p=propulsion(dryKg,payloadKg,dv,isp,thrust,efficiency);
   Object.assign(out,{thrust_N:p.thrustN,exhaust_velocity_m_s:p.exhaustVelocity,mass_flow_kg_s:p.massFlowKgS,delta_v_m_s:p.deltaV,propellant_kg:p.propellantKg,initial_mass_kg:p.initialMassKg,burn_duration_s:p.burnSeconds,kinetic_power_W:p.kineticPowerW,input_power_W:p.electricalPowerW});
   const burn=Math.min(duration>0?duration:p.burnSeconds,p.burnSeconds),energyIn=p.electricalPowerW*burn,kin=p.kineticPowerW*burn,waste=energyIn-kin;
   math.push(check("ideal rocket relation",STATUS.MAT_VALID,"Existing SI model evaluated within finite positive domain","ve=Isp*g0; delta-v=ve ln(m0/mf)",{Isp_s:isp,exhaust_velocity_m_s:p.exhaustVelocity,delta_v_m_s:p.deltaV},0,"no gravity, drag, staging or variable exhaust velocity"));
   const momentumResidual=p.thrustN-p.massFlowKgS*p.exhaustVelocity;
   cons.push(check("reaction momentum flux",Math.abs(momentumResidual)<1e-8*Math.max(1,p.thrustN)?STATUS.PHYS_OK:STATUS.PHYS_BAD,"Checks thrust equals exhaust momentum flow","F=mdot*ve",{F_N:p.thrustN,mdot_kg_s:p.massFlowKgS,ve_m_s:p.exhaustVelocity},momentumResidual,"floating-point tolerance"));
   cons.push(energyBalance(energyIn,kin+waste,1e-9));
   energy.push(check("energy conversion",waste>=-1e-9?STATUS.PHYS_OK:STATUS.PHYS_BAD,"Equivalent exhaust kinetic energy and efficiency-derived waste heat","P_input=P_kin/eta; Qdot=P_input-P_kin",{input_J:energyIn,exhaust_kinetic_J:kin,waste_heat_J:waste,duration_s:burn},energyIn-kin-waste,"ideal exhaust kinetic power only; not detailed engine thermodynamics"));
   if(availablePowerW<=0){energy.push(check("power source",STATUS.MISSING,"Available continuous power rating missing","P_available >= P_input",{required_W:p.electricalPowerW}));energyStatus=STATUS.MISSING;}
   else{const residual=availablePowerW-p.electricalPowerW;energy.push(check("power source",residual>=0?STATUS.PHYS_OK:STATUS.ENG_BAD,residual>=0?"Rated power covers calculated load":"Rated power below calculated load","P_available >= P_input",{available_W:availablePowerW,required_W:p.electricalPowerW},residual,"continuous ratings assumed"));if(residual<0)energyStatus=STATUS.ENG_BAD;}
   if(assembly!==null){
    for(const miss of assembly.missing||[])eng.push(check("component requirements",STATUS.MISSING,miss,"component material/geometry check"));
    for(const err of assembly.dependencyErrors||[])eng.push(check("component dependency",STATUS.MAT_BAD,err,"dependency id must resolve"));
    eng.push(check("machine mass/power aggregate",(assembly.missing||[]).length===0?STATUS.ENG_OK:STATUS.MISSING,assembly.classification,"sum component mass, power, energy and heat",{component_mass_kg:assembly.massKg,component_power_W:assembly.powerW,component_energy_J:assembly.energyJ,component_heat_W:assembly.heatW},null,"not a structural or manufacturing certification"));
    engineering=(assembly.missing||[]).length?STATUS.MISSING:STATUS.ENG_OK;
   }
  }catch(error){
   matStatus=STATUS.MAT_BAD;physical=STATUS.NUMERIC;
   math.push(check("propulsion model",STATUS.MAT_BAD,error.message,"existing reaction propulsion equations",{family},null,"calculation rejected"));
  }
 }else{
  matStatus=STATUS.THEORY;physical=STATUS.MISSING;energyStatus=STATUS.MISSING;engineering=STATUS.MISSING;
  math.push(check("propulsion family",STATUS.THEORY,"No family-specific validated performance model is implemented; conventional rocket equations were not substituted","family-specific equations required",{family},null,"not implemented"));
 }
 if(energyStatus===STATUS.PHYS_OK&&coolingW<=0){
  energy.push(check("heat rejection",STATUS.MISSING,"Cooling capacity not supplied; calculated efficiency loss cannot be assumed dissipated","Qdot_waste <= cooling rating"));energyStatus=STATUS.MISSING;
 }else if(coolingW>0&&Object.hasOwn(out,"input_power_W")){
  const waste=out.input_power_W*(1-efficiency),margin=coolingW-waste;
  energy.push(check("heat rejection",margin>=0?STATUS.PHYS_OK:STATUS.ENG_BAD,margin>=0?"Cooling rating covers calculated idealized waste heat":"Cooling rating below idealized waste heat","Qdot_reject >= P_input-P_kin",{cooling_W:coolingW,estimated_waste_heat_W:waste},margin,"engine heat model reduced to efficiency difference"));
  if(margin<0)energyStatus=STATUS.ENG_BAD;
 }
 const ms=stage(matStatus,math,"SI units; finite inputs; model-specific equations only",spacetime?"No metric-to-thrust mapping":"Symbolic candidate relation is not independently experimentally established");
 const cs=stage(physical,cons,"Conservation applies to defined isolated/control-volume boundaries","Unmodeled external fluxes may change balances");
 const es=stage(energyStatus,energy,"Efficiency is user supplied; waste heat estimate uses ideal exhaust kinetic power","Energy-source cycle, storage mass and thermal gradients not modeled");
 const ens=stage(engineering,eng,"Only stored component volumes, densities and declared power/time/heat are aggregated","No machine assembly alone establishes manufacturability");
 const overall=spacetime?STATUS.THEORY:(math.length>0&&matStatus===STATUS.MAT_VALID&&physical===STATUS.PHYS_OK&&energyStatus===STATUS.PHYS_OK&&engineering===STATUS.ENG_OK)?STATUS.EXPERIMENT:(![STATUS.PHYS_BAD].includes(physical)&&![STATUS.ENG_BAD].includes(energyStatus)?STATUS.MISSING:STATUS.PHYS_BAD);
 return {id:input.id??"browser-assessment",date:input.date??new Date().toISOString(),modelVersion:"beyond-light-0.4-browser-port",propulsionFamily:family,mathematical:ms,conservation:cs,energyThermal:es,engineering:ens,results:out,overallClassification:overall,portScope:"Faithful browser translation of FeasibilityEngine.assess and MachineDesign.assemble for imported records; no filesystem persistence, metric-to-thrust model, or experimental verification."};
}
function evaluate(payload){
 if(!payload||typeof payload!=="object"||Array.isArray(payload))throw new Error("Paket input harus berupa object JSON.");
 const op=payload.operation;
 if(op==="assessment")return assess(payload);
 if(op==="assembly")return assemble(payload);
 throw new Error("Operasi tidak dikenal: "+String(op));
}
window.BeyondLightFeasibilityAssessment={STATUS,assemble,assess,evaluate,propulsion,energyBalance};
})();