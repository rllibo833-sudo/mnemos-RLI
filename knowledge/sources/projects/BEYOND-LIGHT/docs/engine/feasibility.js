/* Deterministic feasibility primitives ported from FeasibilityEngine.java.
 * This is a bounded partial port, not the staged propulsion assessment pipeline.
 */
(() => {
"use strict";
const STATUS=Object.freeze({
 MAT_VALID:"MATHEMATICALLY_VALIDATED",MAT_BAD:"MATHEMATICALLY_INCONSISTENT",
 PHYS_OK:"PHYSICALLY_SUPPORTED_WITHIN_MODEL",PHYS_BAD:"PHYSICAL_VIOLATION_DETECTED",
 ENG_OK:"ENGINEERINGALLY_PLAUSIBLE_WITH_AVAILABLE_DATA",ENG_BAD:"ENGINEERINGALLY_INFEASIBLE",
 MISSING:"INSUFFICIENT_DATA",NUMERIC:"NUMERICALLY_INCONCLUSIVE"
});
const C=299792458;
const G0=9.80665;
const finite=(...xs)=>xs.every(Number.isFinite);
const requireFinite=(label,...xs)=>{if(!finite(...xs))throw new Error(label+" harus berupa angka finite.");};
function balance(law,before,after,tolerance,equation){
 if(before===null||before===undefined||after===null||after===undefined)
  return {law,status:STATUS.MISSING,reasoning:"Required initial and final values are missing",equation,inputs:{},residual:null,tolerance:"not evaluated"};
 if(!finite(before,after,tolerance)||tolerance<0)
  return {law,status:STATUS.NUMERIC,reasoning:"Nonfinite input or invalid tolerance",equation,inputs:{},residual:null,tolerance:"invalid"};
 const residual=before-after,limit=tolerance*Math.max(1,Math.abs(before),Math.abs(after)),ok=Math.abs(residual)<=limit;
 return {law,status:ok?STATUS.PHYS_OK:STATUS.PHYS_BAD,reasoning:ok?"Balance closes within configured numerical tolerance":"Balance residual exceeds configured tolerance",equation,inputs:{initial:before,final:after},residual,tolerance:String(limit)};
}
function energyBalance(beforeJ,afterJ,relativeTolerance=1e-9){
 return balance("energy conservation",beforeJ,afterJ,relativeTolerance,"E_initial = E_final; include all stores, fluxes and losses inside the chosen boundary");
}
function chargeBalance(beforeC,afterC,absoluteTolerance){
 const equation="Q_initial = Q_final for an isolated system boundary";
 if(beforeC==null||afterC==null)return {law:"charge conservation",status:STATUS.MISSING,reasoning:"Required initial and final charges are missing",equation,inputs:{},residual:null,tolerance:"not evaluated"};
 if(!finite(beforeC,afterC,absoluteTolerance)||absoluteTolerance<0)return {law:"charge conservation",status:STATUS.NUMERIC,reasoning:"Nonfinite input or invalid absolute tolerance",equation,inputs:{},residual:null,tolerance:"invalid"};
 const residual=beforeC-afterC,ok=Math.abs(residual)<=absoluteTolerance;
 return {law:"charge conservation",status:ok?STATUS.PHYS_OK:STATUS.PHYS_BAD,reasoning:ok?"Charge balance closes within absolute tolerance":"Charge residual exceeds absolute tolerance",equation,inputs:{initial_C:beforeC,final_C:afterC},residual,tolerance:String(absoluteTolerance)};
}
function vectorBalance(law,before,after,tolerance,unit=""){
 const equation="vector_initial = vector_final";
 if(!Array.isArray(before)||!Array.isArray(after))return {law,status:STATUS.MISSING,reasoning:"Initial or final vector missing",equation,inputs:{},residual:null,tolerance:"not evaluated"};
 if(before.length!==3||after.length!==3)return {law,status:STATUS.MAT_BAD,reasoning:"Expected three vector components",equation:"p_initial = p_final",inputs:{},residual:null,tolerance:"invalid vector shape"};
 if(!finite(...before,...after,tolerance))return {law,status:STATUS.NUMERIC,reasoning:"Nonfinite vector component",equation,inputs:{},residual:null,tolerance:"invalid"};
 let sum=0,scale=1;
 for(let i=0;i<3;i++){sum+=(before[i]-after[i])**2;scale=Math.max(scale,Math.abs(before[i]),Math.abs(after[i]));}
 const residual=Math.sqrt(sum),limit=tolerance*scale,ok=residual<=limit;
 return {law,status:ok?STATUS.PHYS_OK:STATUS.PHYS_BAD,reasoning:ok?"Vector balance closes within tolerance":"Vector residual exceeds tolerance",equation,inputs:{unit,initial:before,final:after},residual,tolerance:String(limit)};
}
function relativisticInvariant(massKg,energyJ,momentum,relativeTolerance=1e-12){
 const equation="E²−|p|²c² = m²c⁴";
 if(!Array.isArray(momentum))return {law:"relativistic energy-momentum",status:STATUS.MISSING,reasoning:"Momentum vector missing",equation,inputs:{},residual:null,tolerance:"not evaluated"};
 if(momentum.length!==3||!finite(massKg,energyJ)||massKg<0)return {law:"relativistic energy-momentum",status:STATUS.MAT_BAD,reasoning:"Invalid mass, energy, or momentum vector",equation,inputs:{},residual:null,tolerance:"invalid"};
 if(!finite(...momentum,relativeTolerance))return {law:"relativistic energy-momentum",status:STATUS.NUMERIC,reasoning:"Nonfinite momentum",equation,inputs:{},residual:null,tolerance:"invalid"};
 const p2=momentum.reduce((s,p)=>s+p*p,0),residual=energyJ*energyJ-p2*C*C-massKg*massKg*C**4;
 const limit=relativeTolerance*Math.max(1,energyJ*energyJ),ok=Math.abs(residual)<=limit;
 return {law:"relativistic energy-momentum",status:ok?STATUS.PHYS_OK:STATUS.PHYS_BAD,reasoning:ok?"Invariant matches within tolerance":"Energy-momentum invariant mismatch",equation,inputs:{mass_kg:massKg,energy_J:energyJ,momentum_kg_m_s:momentum},residual,tolerance:String(limit)};
}
function stress(tensileN,compressiveN,shearN,areaM2,shearAreaM2,lengthM,youngPa,yieldPa,safetyRequired){
 requireFinite("Beban, luas, panjang, modulus, dan faktor keselamatan",tensileN,compressiveN,shearN,areaM2,shearAreaM2,lengthM,youngPa,safetyRequired);
 if(tensileN<0||compressiveN<0||shearN<0||areaM2<=0||shearAreaM2<=0||lengthM<0||youngPa<=0||safetyRequired<=0)throw new Error("Beban harus nonnegatif; luas, modulus, dan faktor keselamatan harus positif; panjang tidak negatif.");
 const tensilePa=tensileN/areaM2,compressivePa=compressiveN/areaM2,shearPa=shearN/shearAreaM2;
 const normal=tensilePa-compressivePa,strain=normal/youngPa,axialDeformationM=strain*lengthM,vonMisesPa=Math.sqrt(normal*normal+3*shearPa*shearPa);
 const unknowns=[];let safetyFactor;
 if(yieldPa==null||!Number.isFinite(yieldPa)||yieldPa<=0){unknowns.push("yield strength/allowable unavailable");safetyFactor=null;}
 else safetyFactor=yieldPa/vonMisesPa;
 const status=unknowns.length?STATUS.MISSING:(safetyFactor>=safetyRequired?STATUS.ENG_OK:STATUS.ENG_BAD);
 return {tensilePa,compressivePa,shearPa,vonMisesPa,strain,axialDeformationM,safetyFactor,status,unknowns};
}
function eulerBucklingLoad(youngPa,secondMomentM4,lengthM,effectiveLengthFactor){
 requireFinite("Parameter tekuk Euler",youngPa,secondMomentM4,lengthM,effectiveLengthFactor);
 if(youngPa<=0||secondMomentM4<=0||lengthM<=0||effectiveLengthFactor<=0)throw new Error("Parameter tekuk Euler harus positif.");
 return Math.PI**2*youngPa*secondMomentM4/(effectiveLengthFactor*lengthM)**2;
}
function pressureHoopStress(pressurePa,radiusM,wallM){
 requireFinite("Tekanan dan geometri bejana",pressurePa,radiusM,wallM);
 if(pressurePa<0||radiusM<=0||wallM<=0)throw new Error("Tekanan harus nonnegatif dan radius/ketebalan dinding harus positif.");
 if(wallM/radiusM>.1)throw new Error("Pendekatan dinding tipis hanya berlaku jika wall/radius ≤ 0.1.");
 return pressurePa*radiusM/wallM;
}
function thermalExpansion(alphaPerK,lengthM,deltaK){
 requireFinite("Parameter ekspansi termal",alphaPerK,lengthM,deltaK);
 if(alphaPerK<0||lengthM<0)throw new Error("Koefisien ekspansi dan panjang harus nonnegatif.");
 return alphaPerK*lengthM*deltaK;
}
function electrical(voltage,current,resistance,duration){
 requireFinite("Parameter listrik",voltage,current,resistance,duration);
 if(voltage<0||current<0||resistance<0||duration<0)throw new Error("Parameter listrik harus finite dan nonnegatif.");
 const powerW=voltage*current,jouleHeatW=current*current*resistance,energyJ=powerW*duration;
 const status=resistance===0?STATUS.MISSING:(Math.abs(voltage-current*resistance)<=1e-8*Math.max(1,voltage)?STATUS.PHYS_OK:STATUS.PHYS_BAD);
 return {powerW,currentA:current,voltageV:voltage,resistanceOhm:resistance,jouleHeatW,energyJ,status};
}
function assessEnergyStorage(deliveredEnergyJ,energyDensityJkg,conversionEfficiency){
 requireFinite("Parameter penyimpanan energi",deliveredEnergyJ,energyDensityJkg,conversionEfficiency);
 if(deliveredEnergyJ<0||energyDensityJkg<=0||conversionEfficiency<=0||conversionEfficiency>1)throw new Error("Energi ≥ 0, densitas energi > 0, dan efisiensi 0 < η ≤ 1 diperlukan.");
 const requiredInputEnergyJ=deliveredEnergyJ/conversionEfficiency,conversionLossJ=requiredInputEnergyJ-deliveredEnergyJ,minimumStorageMassKg=deliveredEnergyJ/energyDensityJkg;
 if(!Number.isFinite(requiredInputEnergyJ+conversionLossJ+minimumStorageMassKg))throw new Error("Hasil perhitungan penyimpanan energi melampaui rentang numerik finite.");
 return {deliveredEnergyJ,requiredInputEnergyJ,conversionLossJ,minimumStorageMassKg,status:STATUS.MISSING};
}
function diagonalEnergyConditions(rhoJm3,pressures){
 if(!Array.isArray(pressures)||pressures.length!==3||!Number.isFinite(rhoJm3))throw new Error("Berikan rho finite dan tiga tekanan prinsipal.");
 if(!finite(...pressures))throw new Error("Tekanan prinsipal harus finite.");
 let nec=true,wec=rhoJm3>=0;
 for(const p of pressures)if(rhoJm3+p<0)nec=false;
 wec=wec&&nec;
 return {status:nec&&wec?STATUS.PHYS_OK:STATUS.PHYS_BAD,nullEnergyCondition:nec,weakEnergyCondition:wec,reasoning:"Diagonal orthonormal-frame test only: NEC rho+p_i>=0; WEC rho>=0 and rho+p_i>=0. Not a stress-energy tensor derived from a metric."};
}
const operations={
 energyBalance:p=>energyBalance(p.beforeJ,p.afterJ,p.relativeTolerance??1e-9),
 chargeBalance:p=>chargeBalance(p.beforeC,p.afterC,p.absoluteTolerance),
 vectorBalance:p=>vectorBalance(p.law||"vector conservation",p.before,p.after,p.tolerance??1e-9,p.unit||""),
 relativisticInvariant:p=>relativisticInvariant(p.massKg,p.energyJ,p.momentum,p.relativeTolerance??1e-12),
 stress:p=>stress(p.tensileN,p.compressiveN,p.shearN,p.areaM2,p.shearAreaM2,p.lengthM,p.youngPa,p.yieldPa,p.safetyRequired),
 eulerBuckling:p=>eulerBucklingLoad(p.youngPa,p.secondMomentM4,p.lengthM,p.effectiveLengthFactor),
 pressureHoop:p=>pressureHoopStress(p.pressurePa,p.radiusM,p.wallM),
 thermalExpansion:p=>thermalExpansion(p.alphaPerK,p.lengthM,p.deltaK),
 electrical:p=>electrical(p.voltage,p.current,p.resistance,p.duration),
 energyStorage:p=>assessEnergyStorage(p.deliveredEnergyJ,p.energyDensityJkg,p.conversionEfficiency),
 energyConditions:p=>diagonalEnergyConditions(p.rhoJm3,p.pressures)
};
function evaluate(payload){
 if(!payload||typeof payload!=="object"||Array.isArray(payload))throw new Error("Paket input harus berupa object JSON.");
 const op=payload.operation,fn=operations[op];if(!fn)throw new Error("Operasi tidak dikenal: "+String(op));
 return {operation:op,result:fn(payload),scope:"Deterministic feasibility primitive only; not the complete staged FeasibilityEngine assessment."};
}
window.BeyondLightFeasibility={STATUS,energyBalance,chargeBalance,vectorBalance,relativisticInvariant,stress,eulerBucklingLoad,pressureHoopStress,thermalExpansion,electrical,assessEnergyStorage,diagonalEnergyConditions,evaluate};
})();
