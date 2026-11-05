"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const context = { window: {} };
vm.runInNewContext(fs.readFileSync("docs/engine/knowledge-explorer.js", "utf8"), context);
const engine = context.window.BeyondLightKnowledgeExplorer;
const nodes = [
  {id:"n1",title:"Solar energy storage materials",kind:"dataset",content:"Thermal energy storage material efficiency",source:{uri:"https://example.org/solar"},metadata:{knowledge_layer:"scientific",knowledge:{evidence_status:"source_verified"}}},
  {id:"n2",title:"Thermal energy storage experiment",kind:"experiment",content:"Solar energy storage material testing",metadata:{knowledge_layer:"experimental",knowledge:{evidence_status:"unverified",sources:[{title:"Experiment record",ref:"https://example.org/experiment"}]}}},
  {id:"n3",title:"Ancient trade history",kind:"historical_record",content:"Maritime routes and exchange",metadata:{knowledge_layer:"historical",knowledge:{evidence_status:"unknown"}}},
  {id:"n4",title:"Isolated philosophy note",kind:"note",content:"Ethics and knowledge",metadata:{knowledge_layer:"philosophical"}}
];
const edges = [
  {source:"n1",target:"n3",relation:"related_to"},
  {source:"n2",target:"n3",relation:"mentions"}
];
const first = engine.analyze(nodes,edges,null);
assert.equal(first.metrics.nodes,4);
assert.equal(first.metrics.edges,2);
assert.equal(first.metrics.connectedComponents,2);
assert.equal(first.metrics.isolatedNodes,1);
const pair=first.candidates.find(x=>x.sourceId==="n1"&&x.targetId==="n2");
assert.ok(pair,"lexically related pair should be proposed");
assert.equal(pair.sharedNeighbors.length,1,"graph common-neighbor context should be included");
assert.equal(pair.sourceReferences.length,2,"source provenance should be included");
assert.ok(first.metrics.structuralCandidates>=1);
assert.ok(first.candidates.every(x=>x.classification==="UNVERIFIED_RELATION_CANDIDATE"));
const prior = {candidates:first.candidates};
const second = engine.analyze(nodes,[...edges,{source:"n1",target:"n2",relation:"tests"}],prior);
assert.ok(second.cycleComparison.resolvedByNewGraphEdges>=1);
assert.ok(!second.candidates.some(x=>x.sourceId==="n1"&&x.targetId==="n2"));
assert.ok(engine.tokens("Thermal energy storage").includes("thermal"));

const benchmarkContext={window:{}};
vm.runInNewContext(fs.readFileSync("docs/engine/symbolic.js","utf8"),benchmarkContext);
vm.runInNewContext(fs.readFileSync("docs/engine/research.js","utf8"),benchmarkContext);
const benchmarkResults=benchmarkContext.window.BeyondLightResearch.benchmarks.runAll();
assert.ok(benchmarkResults.length>0,"registered browser benchmark catalog should not be empty");
assert.ok(benchmarkResults.every(x=>["PASS","FAIL","INCONCLUSIVE"].includes(x.status)));
assert.equal(benchmarkResults.length,benchmarkResults.filter(x=>x.status==="PASS"||x.status==="FAIL"||x.status==="INCONCLUSIVE").length);
console.log("knowledge graph exploration and browser benchmark tests passed");
