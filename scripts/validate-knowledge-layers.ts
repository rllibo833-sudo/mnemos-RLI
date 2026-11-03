import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

type JsonObject = Record<string, any>;
const root = "knowledge";
const contract = JSON.parse(await readFile(join(root, "layers", "manifest.json"), "utf8"));
const layerIds = new Set(Object.keys(contract.layers));

function fail(message: string): never {
  throw new Error("Knowledge layer validation: " + message);
}
function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function nonEmpty(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}
function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter(nonEmpty).map((item: string) => item.trim()) : [];
}
function hasSources(knowledge: JsonObject): boolean {
  return Array.isArray(knowledge.sources) && knowledge.sources.length > 0 &&
    knowledge.sources.every((source: unknown) => isObject(source) &&
      (nonEmpty(source.ref) || nonEmpty(source.title)));
}
function validateNode(node: JsonObject, file: string): void {
  const metadata = isObject(node.metadata) ? node.metadata : {};
  const layer = metadata.knowledge_layer;
  if (layer === undefined || layer === null || layer === "") return;
  if (typeof layer !== "string" || !layerIds.has(layer)) fail(file + ": unknown metadata.knowledge_layer " + String(layer));
  const knowledge = metadata.knowledge;
  if (!isObject(knowledge)) fail(file + ": metadata.knowledge must be an object for layer " + layer);
  const spec = contract.layers[layer];

  if (layer === "historical" || layer === "scientific") {
    if (!hasSources(knowledge)) fail(file + ": " + layer + " records require non-empty source references (ref or title)");
  }
  if (layer === "philosophical") {
    const fields = spec.requires_any as string[];
    if (!fields.some(field => stringArray(knowledge[field]).length > 0)) {
      fail(file + ": philosophical records require at least one of " + fields.join(", "));
    }
  }
  if (layer === "scientific") {
    if (!nonEmpty(knowledge.claim_type)) fail(file + ": scientific records require knowledge.claim_type");
    if (!spec.evidence_status.includes(knowledge.evidence_status)) {
      fail(file + ": scientific evidence_status must be one of " + spec.evidence_status.join(", "));
    }
  }
  if (layer === "cross-disciplinary") {
    const disciplines = [...new Set(stringArray(knowledge.disciplines).map(value => value.toLowerCase()))];
    if (disciplines.length < spec.minimum_disciplines) fail(file + ": cross-disciplinary records require at least two distinct disciplines");
    if (!nonEmpty(knowledge.mapping_rationale)) fail(file + ": cross-disciplinary records require knowledge.mapping_rationale");
  }
  if (layer === "experimental") {
    for (const field of ["hypothesis", "method"]) {
      if (!nonEmpty(knowledge[field])) fail(file + ": experimental records require knowledge." + field);
    }
    if (!spec.outcome_status.includes(knowledge.outcome_status)) {
      fail(file + ": experimental outcome_status must be one of " + spec.outcome_status.join(", "));
    }
  }
}
function validateEdge(edge: JsonObject, file: string): void {
  const metadata = isObject(edge.metadata) ? edge.metadata : {};
  const layer = metadata.knowledge_layer;
  if (layer === undefined || layer === null || layer === "") return;
  if (typeof layer !== "string" || !layerIds.has(layer)) fail(file + ": unknown edge metadata.knowledge_layer " + String(layer));
  const allowed = contract.layers[layer].relations as string[];
  if (!allowed.includes(edge.relation)) {
    fail(file + ": relation '" + String(edge.relation) + "' is not valid for layer '" + layer + "'");
  }
  if (edge.confidence !== undefined && edge.confidence !== null &&
      (typeof edge.confidence !== "number" || !Number.isFinite(edge.confidence) || edge.confidence < 0 || edge.confidence > 1)) {
    fail(file + ": confidence must be a number from 0 to 1");
  }
  if (edge.provenance !== undefined && !isObject(edge.provenance)) fail(file + ": provenance must be an object");
}

const nodeDir = join(root, "nodes");
const edgeDir = join(root, "edges");
const nodeFiles = (await readdir(nodeDir)).filter(file => file.endsWith(".json")).sort();
const edgeFiles = (await readdir(edgeDir)).filter(file => file.endsWith(".links.json")).sort();
let typedNodes = 0;
let typedEdges = 0;

for (const file of nodeFiles) {
  const parsed = JSON.parse(await readFile(join(nodeDir, file), "utf8"));
  const rows = Array.isArray(parsed) ? parsed : [parsed];
  for (const node of rows) {
    if (!isObject(node) || !nonEmpty(node.id)) fail(file + ": each node requires an id");
    if (isObject(node.metadata) && node.metadata.knowledge_layer) typedNodes++;
    validateNode(node, file);
  }
}
for (const file of edgeFiles) {
  const parsed = JSON.parse(await readFile(join(edgeDir, file), "utf8"));
  if (!Array.isArray(parsed)) fail(file + ": edge file must contain an array");
  for (const edge of parsed) {
    if (!isObject(edge)) fail(file + ": each edge must be an object");
    if (isObject(edge.metadata) && edge.metadata.knowledge_layer) typedEdges++;
    validateEdge(edge, file);
  }
}
console.log(JSON.stringify({
  ok: true,
  layers: [...layerIds],
  typed_nodes: typedNodes,
  typed_edges: typedEdges,
  legacy_records_preserved: true
}));
