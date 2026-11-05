const assert=require("node:assert/strict");
global.window=global;require("./decision.js");
const D=global.BeyondLightDecision;
const base={overallClassification:"REQUIRES_EXPERIMENTAL_VALIDATION",mathematical:{status:"MATHEMATICALLY_VALIDATED"},conservation:{status:"PHYSICALLY_SUPPORTED_WITHIN_MODEL"},energyThermal:{status:"PHYSICALLY_SUPPORTED_WITHIN_MODEL"},engineering:{status:"INSUFFICIENT_DATA",checks:[]},results:{deltaV:1200}};
let r=D.classify({assessment:base,benchmarkResults:[{status:"PASS"}]});
assert(r.classifications.includes("MATHEMATICALLY_CONSISTENT"));
assert(r.classifications.includes("PHYSICALLY_CONSISTENT"));
assert(r.classifications.includes("ENGINEERING_ESTIMATE"));
assert(r.classifications.includes("INSUFFICIENT_DATA"));
assert(!r.experimentallySupported);
r=D.classify({assessment:base,benchmarkResults:[{status:"PASS"}],experimentalEvidence:{recordId:"EXP-1",rawDataReference:"data/exp.csv",testConditions:"ambient 20 C",measurementUnits:"SI"}});
assert(r.classifications.includes("EXPERIMENTALLY_SUPPORTED"));
assert.equal(r.experimentallySupported,true);
r=D.classify({assessment:{...base,conservation:{status:"PHYSICAL_VIOLATION_DETECTED"}}});
assert(r.classifications.includes("PHYSICALLY_INCONSISTENT"));
r=D.classify({assessment:{...base,overallClassification:"THEORETICAL_ONLY",mathematical:{status:"THEORETICAL_ONLY"}}});
assert(r.classifications.includes("THEORETICAL_ONLY"));
assert(!r.classifications.includes("ENGINEERING_ESTIMATE"));
const candidates=[
 {id:"A",candidateFeasible:true,mass:10,power:100},
 {id:"B",candidateFeasible:true,mass:8,power:120},
 {id:"C",candidateFeasible:true,mass:12,power:90},
 {id:"D",candidateFeasible:true,mass:12,power:80},
 {id:"X",candidateFeasible:false,mass:1,power:1}
];
r=D.rankCandidates({allCandidates:candidates,objectives:[{metric:"mass",direction:"MINIMIZE"},{metric:"power",direction:"MINIMIZE"}],invalidOrUnsolvableCandidates:2});
assert.equal(r.candidatesEvaluated,5);
assert.equal(r.withinEnvelope,4);
assert.deepEqual(r.paretoCandidates.map(x=>x.id),["B","A","D"]);
assert.equal(r.invalidOrUnsolvableCandidates,2);
assert.throws(()=>D.rankCandidates({allCandidates:candidates}),/objectives/);
console.log("decision engines: 18 checks passed; conservative evidence labels and Pareto ranking verified");
