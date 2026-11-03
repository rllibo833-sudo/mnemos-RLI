type JsonObject = Record<string, any>;

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

export function validateKnowledgeLayers(nodes: JsonObject[], edges: JsonObject[], contract: JsonObject) {
  if (!isObject(contract) || contract.schema_version !== 1 || !isObject(contract.layers)) {
    fail("layer manifest must use schema_version 1 and define layers");
  }
  const layerIds = new Set(Object.keys(contract.layers));
  let typedNodes = 0;
  let typedEdges = 0;

  for (const node of nodes) {
    if (!isObject(node) || !nonEmpty(node.id)) fail("every graph node must have a non-empty id");
    const metadata = isObject(node.metadata) ? node.metadata : {};
    const layer = metadata.knowledge_layer;
    if (layer === undefined || layer === null || layer === "") continue;
    typedNodes++;
    if (typeof layer !== "string" || !layerIds.has(layer)) fail("node " + node.id + " has unknown knowledge_layer " + String(layer));
    const knowledge = metadata.knowledge;
    if (!isObject(knowledge)) fail("node " + node.id + " requires metadata.knowledge for layer " + layer);
    const spec = contract.layers[layer];

    if (layer === "historical" || layer === "scientific") {
      if (!hasSources(knowledge)) fail("node " + node.id + ": " + layer + " requires non-empty source references (ref or title)");
    }
    if (layer === "philosophical") {
      const fields = spec.requires_any as string[];
      if (!fields.some(field => stringArray(knowledge[field]).length > 0)) {
        fail("node " + node.id + ": philosophical layer requires at least one of " + fields.join(", "));
      }
    }
    if (layer === "scientific") {
      if (!nonEmpty(knowledge.claim_type)) fail("node " + node.id + ": scientific layer requires claim_type");
      if (!spec.evidence_status.includes(knowledge.evidence_status)) {
        fail("node " + node.id + ": invalid scientific evidence_status");
      }
    }
    if (layer === "cross-disciplinary") {
      const disciplines = [...new Set(stringArray(knowledge.disciplines).map(value => value.toLowerCase()))];
      if (disciplines.length < spec.minimum_disciplines) fail("node " + node.id + ": cross-disciplinary layer requires at least two distinct disciplines");
      if (!nonEmpty(knowledge.mapping_rationale)) fail("node " + node.id + ": cross-disciplinary layer requires mapping_rationale");
    }
    if (layer === "experimental") {
      for (const field of ["hypothesis", "method"]) {
        if (!nonEmpty(knowledge[field])) fail("node " + node.id + ": experimental layer requires " + field);
      }
      if (!spec.outcome_status.includes(knowledge.outcome_status)) {
        fail("node " + node.id + ": invalid experimental outcome_status");
      }
      const results = stringArray(knowledge.results);
      const failures = stringArray(knowledge.failure_modes);
      const rawDataRefs = stringArray(knowledge.raw_data_refs);
      if (knowledge.outcome_status === "supported" && (!results.length || (!rawDataRefs.length && !hasSources(knowledge)))) {
        fail("node " + node.id + ": supported experiments require results and raw_data_refs or sources");
      }
      if (knowledge.outcome_status === "replicated" && (!results.length || !nonEmpty(knowledge.replication_of))) {
        fail("node " + node.id + ": replicated experiments require results and replication_of");
      }
      if (["not_supported", "inconclusive"].includes(knowledge.outcome_status) && !results.length && !failures.length) {
        fail("node " + node.id + ": not_supported and inconclusive experiments require results or failure_modes");
      }
      if (knowledge.outcome_status === "failed" && !failures.length && !results.length) {
        fail("node " + node.id + ": failed experiments require failure_modes or results");
      }
    }
  }

  for (const edge of edges) {
    if (!isObject(edge)) fail("every graph edge must be an object");
    const metadata = isObject(edge.metadata) ? edge.metadata : {};
    const layer = metadata.knowledge_layer;
    if (layer === undefined || layer === null || layer === "") continue;
    typedEdges++;
    if (typeof layer !== "string" || !layerIds.has(layer)) fail("edge has unknown knowledge_layer " + String(layer));
    const allowed = contract.layers[layer].relations as string[];
    if (!allowed.includes(edge.relation)) {
      fail("edge relation '" + String(edge.relation) + "' is not valid for layer '" + layer + "'");
    }
    if (metadata.confidence !== undefined && metadata.confidence !== null &&
        (typeof metadata.confidence !== "number" || !Number.isFinite(metadata.confidence) || metadata.confidence < 0 || metadata.confidence > 1)) {
      fail("edge confidence must be a number from 0 to 1");
    }
    if (metadata.provenance !== undefined && !isObject(metadata.provenance)) fail("edge metadata.provenance must be an object");
  }

  return { ok: true, layers: [...layerIds], typed_nodes: typedNodes, typed_edges: typedEdges, legacy_records_preserved: true };
}
