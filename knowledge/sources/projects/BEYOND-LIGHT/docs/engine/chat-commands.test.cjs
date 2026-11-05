"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const calls=[];
const context={window:{BeyondLightResearchCore:{
 dispatch:async request=>{calls.push(request);return {analysis:{engineId:"test.engine",status:"TEST_COMPLETED",output:{received:request.context}},evidence:{summary:"test only"}};},
 listDatasets:()=>[{id:"local-1",filename:"sample.csv",rows:10}]
}}};
vm.runInNewContext(fs.readFileSync("docs/engine/chat-commands.js","utf8"),context);
(async()=>{
 const C=context.window.BeyondLightChatCommands;
 assert.equal(await C.execute("apa itu gravitasi?"),null);
 assert.match((await C.execute("bantuan mesin")).text,/turunkan/);
 const derivative=await C.execute("turunkan x^2 terhadap x");
 assert.equal(derivative.result.analysis.output.received.operation,"differentiate");
 assert.equal(derivative.result.analysis.output.received.expression,"x^2");
 assert.equal(derivative.result.analysis.output.received.variable,"x");
 const integral=await C.execute("integralkan: x^2 terhadap x");
 assert.equal(integral.result.analysis.output.received.operation,"integrate");
 const simplify=await C.execute("sederhanakan: x + 0");
 assert.equal(simplify.result.analysis.output.received.operation,"simplify");
 const evaluate=await C.execute("evaluasi: x^2; x=3");
 assert.equal(evaluate.result.analysis.output.received.values.x,3);
 const isolate=await C.execute("isolasi x dari 2*x+3=11");
 assert.equal(isolate.result.analysis.output.received.lhs,"2*x+3");
 assert.equal(isolate.result.analysis.output.received.rhs,"11");
 const benchmark=await C.execute("benchmark semua");
 assert.equal(benchmark.result.analysis.output.received.workflow,"catalog-validation");
 const search=await C.execute("cari dataset: rocket propulsion");
 assert.equal(search.result.analysis.output.received.workflow,"open-data-discovery");
 const cycle=await C.execute("siklus riset: rocket propulsion");
 assert.equal(cycle.result.analysis.output.received.workflow,"open-data");
 const datasetAnalysis=await C.execute("analisis dataset: local-1; x=power; y=thrust");
 assert.equal(datasetAnalysis.result.analysis.output.received.workflow,"dataset-analysis");
 assert.equal(datasetAnalysis.result.analysis.output.received.datasetId,"local-1");
 assert.equal(datasetAnalysis.result.analysis.output.received.x,"power");
 const modelSearch=await C.execute("model dataset: local-1; target=thrust");
 assert.equal(modelSearch.result.analysis.output.received.workflow,"autonomous-model");
 assert.equal(modelSearch.result.analysis.output.received.target,"thrust");
 assert.match((await C.execute("daftar dataset")).text,/local-1/);
 assert.match((await C.execute("evaluasi: x; x=tidak-angka")).text,/Nilai harus/);
 assert.equal(calls.length,10);
 console.log("chat command bridge tests passed");
})().catch(e=>{console.error(e);process.exitCode=1;});
