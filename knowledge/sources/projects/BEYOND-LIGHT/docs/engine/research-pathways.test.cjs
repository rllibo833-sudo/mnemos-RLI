"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const context={window:{}};
vm.runInNewContext(fs.readFileSync("docs/engine/knowledge-explorer.js","utf8"),context);
vm.runInNewContext(fs.readFileSync("docs/engine/research-pathways.js","utf8"),context);
const E=context.window.BeyondLightKnowledgeExplorer,P=context.window.BeyondLightResearchPathways;
const nodes=[
{id:"a",title:"Solar thermal energy storage",kind:"dataset",content:"Thermal energy storage efficiency material results",source:{uri:"https://example.org/a"},metadata:{knowledge_layer:"scientific",knowledge:{evidence_status:"source_verified"}}},
{id:"b",title:"Thermal energy storage experiment",kind:"experiment",content:"Solar thermal energy storage material test",metadata:{knowledge_layer:"experimental",knowledge:{evidence_status:"unverified",sources:[{title:"Experiment",ref:"https://example.org/b"}]}}},
{id:"c",title:"Solar thermal materials review",kind:"review",content:"Solar thermal energy storage review",metadata:{knowledge_layer:"review",knowledge:{evidence_status:"not_recorded"}}}
];
const edges=[{source:"a",target:"c",relation:"mentions"},{source:"b",target:"c",relation:"mentions"}];
const report=E.analyze(nodes,edges,null),candidate=report.candidates.find(x=>x.sourceId==="a"&&x.targetId==="b");
assert.ok(candidate);
assert.equal(candidate.evidenceDossier.nodes.length,2);
assert.equal(candidate.evidenceDossier.sharedContext.length,1);
assert.ok(candidate.evidenceDossier.knownSourceCount>=2);
const path=P.create(candidate);
assert.equal(path.route.workflow,"open-data-discovery");
assert.ok(path.question.length<=160);
assert.equal(path.hypothesis,"PROPOSED_QUESTION_ONLY");
assert.equal(path.executionStatus,"READY_FOR_METADATA_SEARCH");
assert.equal(path.testability.status,"NEEDS_DATA");
assert.ok(path.testability.engineCandidates.includes("dataset.deterministic-analysis"));
const methodPath=P.create({id:"non-science",sourceTitle:"Ancient trade networks",targetTitle:"Ethical traditions",sharedConcepts:["history"],evidenceDossier:{nodes:[{id:"h",kind:"historical_record",layer:"historical"},{id:"p",kind:"text",layer:"philosophical"}]}});
assert.equal(methodPath.testability.status,"NEEDS_METHOD");
const summary=P.summarize({analysis:{status:"OPEN_DATA_METADATA_FOUND",output:{records:[{title:"Paper",doi:"10.1/test",recordUrl:"https://zenodo.org/records/1"}]}},evidence:{classification:"OPEN_DATA_METADATA_DISCOVERY"}});
assert.equal(summary.recordCount,1);
assert.equal(summary.records[0].title,"Paper");
console.log("autonomous evidence dossier and research pathway tests passed");
