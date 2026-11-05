"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const context={window:{}};
vm.runInNewContext(fs.readFileSync("docs/engine/autonomous-model.js","utf8"),context);
const engine=context.window.BeyondLightAutonomousModel;
const rows=[];
for(let i=0;i<48;i++){
 const x=(i%8)-3.5,z=Math.floor(i/8)-2.5;
 rows.push([x,z,7+2*x*x+3*z+0.7*x*z]);
}
const dataset={id:"fixture",filename:"fixture.csv",headers:["x","z","target"],rows,units:"x:m,z:s,target:N",source:"test fixture"};
const result=engine.explore(dataset,"target");
assert.equal(result.recordType,"AUTONOMOUS_MODEL_EXPLORATION");
assert.equal(result.inputs.rowsAnalyzed,48);
assert.equal(result.inputs.folds,5);
assert.ok(result.inputs.featureStructuresGenerated>=8);
assert.ok(result.inputs.candidateStructuresFitted>0);
assert.ok(result.result.bestModels.length>0);
assert.ok(result.result.bestModels.length<=8);
assert.ok(result.result.bestModels.every(m=>Number.isFinite(m.crossValidationRmse)));
assert.ok(result.result.bestModels.every(m=>m.termDefinitions.length>=1&&m.termDefinitions.length<=2));
assert.equal(result.sources[0].source,"test fixture");
assert.throws(()=>engine.explore(dataset,"missing"),/Target column/);
assert.throws(()=>engine.explore({...dataset,rows:rows.slice(0,5)},"target"),/six rows/);
assert.throws(()=>engine.explore({...dataset,rows:rows.map((r,i)=>i===0?[r[0],r[1],"NaN"]:r)},"target"),/finite/);
console.log("autonomous model browser tests passed");
