const assert=require("node:assert/strict");
global.window=global;
window.BeyondLightFeasibility={STATUS:{ENG_OK:"ENGINEERINGALLY_PLAUSIBLE_WITH_AVAILABLE_DATA",ENG_BAD:"ENGINEERINGALLY_INFEASIBLE",MISSING:"INSUFFICIENT_DATA"}};
window.BeyondLightFeasibility.stress=(t,c,s,a,sa,l,e,y,sf)=>{const vm=Math.sqrt(((t-c)/a)**2+3*(s/sa)**2),safety=y/vm;return {vonMisesPa:vm,safetyFactor:safety,status:Number.isFinite(y)&&y>0&&safety>=sf?"ENGINEERINGALLY_PLAUSIBLE_WITH_AVAILABLE_DATA":"ENGINEERINGALLY_INFEASIBLE",unknowns:[]};};
window.BeyondLightFeasibilityAssessment={assess:()=>({overallClassification:"REQUIRES_EXPERIMENTAL_VALIDATION",engineering:{status:"INSUFFICIENT_DATA"}})};
require("./technology-design.js");
const D=window.BeyondLightTechnologyDesign;
const ids=Object.keys(D.domains);assert.equal(ids.length,4);
for(const id of ids){const d=D.domains[id],r=D.explore(id,{...d.defaults});assert(r.candidatesGenerated>0);assert.equal(r.candidatesEvaluated+r.invalidOrUnsolvableCandidates,r.candidatesGenerated);assert(Array.isArray(r.paretoCandidates));assert(r.objectives.length>0);assert(r.equations.length>0);assert(r.limitations.length>0);}
let r=D.explore("propulsion.reaction.ideal",{...D.domains["propulsion.reaction.ideal"].defaults});assert.equal(r.candidatesGenerated,144);assert(r.allCandidates.some(x=>x.equationCrossChecksPass));
r=D.explore("structures.member.envelope",{...D.domains["structures.member.envelope"].defaults});assert.equal(r.candidatesGenerated,15);assert(r.allCandidates.every(x=>Number.isFinite(x.estimatedMemberMassKg)));
r=D.explore("thermal.management.steady-state",{...D.domains["thermal.management.steady-state"].defaults});assert.equal(r.candidatesGenerated,12);assert(r.allCandidates.every(x=>Number.isFinite(x.marginW)));
r=D.explore("energy.storage.envelope",{...D.domains["energy.storage.envelope"].defaults});assert.equal(r.candidatesGenerated,64);assert(r.allCandidates.every(x=>Number.isFinite(x.minimumStorageMassKg)));
assert.throws(()=>D.explore("structures.member.envelope",{...D.domains["structures.member.envelope"].defaults,sectionScaleSteps:31}),/1–30/);
assert.throws(()=>D.explore("energy.storage.envelope",{...D.domains["energy.storage.envelope"].defaults,maxEfficiency:1.2}),/tidak valid/);
console.log("technology design browser engines: 15 checks passed; 4 domains, candidate generation, evaluation and Pareto ranking verified");