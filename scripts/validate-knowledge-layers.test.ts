import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { validateKnowledgeLayers } from "./validate-knowledge-layers";

const contract = JSON.parse(await readFile("knowledge/layers/manifest.json", "utf8"));
const source = [{ type: "paper", ref: "https://example.org/paper", title: "Example paper" }];
const node = (id: string, layer: string, knowledge: Record<string, unknown>) => ({
  id, metadata: { knowledge_layer: layer, knowledge }
});
const nodes = [
  node("history", "historical", { sources: source, date: "1900-01-01" }),
  node("philosophy", "philosophical", { assumptions: ["A model has a boundary."] }),
  node("science", "scientific", { claim_type: "research_run", evidence_status: "unknown", sources: source }),
  node("bridge", "cross-disciplinary", { disciplines: ["physics", "materials"], mapping_rationale: "Material properties constrain a physical model." }),
  node("experiment", "experimental", { hypothesis: "H", method: "Controlled comparison", outcome_status: "inconclusive", results: ["Simulation did not distinguish candidates."] })
];
const edges = [
  { source: "history", target: "science", relation: "influenced_by", metadata: { knowledge_layer: "historical", provenance: { request_id: "test" } } },
  { source: "philosophy", target: "science", relation: "questions", metadata: { knowledge_layer: "philosophical" } },
  { source: "science", target: "experiment", relation: "supports", metadata: { knowledge_layer: "scientific", confidence: 0.5 } },
  { source: "bridge", target: "science", relation: "maps_to", metadata: { knowledge_layer: "cross-disciplinary" } },
  { source: "experiment", target: "science", relation: "tests", metadata: { knowledge_layer: "experimental" } }
];
const result = validateKnowledgeLayers(nodes, edges, contract);
assert.equal(result.ok, true);
assert.equal(result.typed_nodes, 5);
assert.equal(result.typed_edges, 5);
assert.throws(() => validateKnowledgeLayers(
  [node("bad", "scientific", { claim_type: "claim", evidence_status: "confirmed", sources: source })], [], contract
), /invalid scientific evidence_status/);
assert.throws(() => validateKnowledgeLayers(
  [], [{ source: "a", target: "b", relation: "auto_match", metadata: { knowledge_layer: "scientific" } }], contract
), /not valid for layer/);
assert.throws(() => validateKnowledgeLayers(
  [node("unsupported-evidence", "experimental", {
    hypothesis: "H", method: "Controlled test", outcome_status: "supported", results: ["Observed result"]
  })], [], contract
), /supported experiments require results and raw_data_refs or sources/);
assert.throws(() => validateKnowledgeLayers(
  [node("missing-replication", "experimental", {
    hypothesis: "H", method: "Replication test", outcome_status: "replicated", results: ["Observed result"]
  })], [], contract
), /replicated experiments require results and replication_of/);
const legacy = validateKnowledgeLayers(
  [{ id: "legacy", kind: "audit_finding", metadata: {} }],
  [{ source: "legacy", target: "legacy-2", relation: "auto_match" }],
  contract
);
assert.equal(legacy.typed_nodes, 0);
assert.equal(legacy.typed_edges, 0);
console.log("Knowledge layer contract checks passed.");
