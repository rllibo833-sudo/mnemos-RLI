# Mnemos Knowledge Layers v1

The `Knowledge` branch is the canonical, inspectable graph. This layer contract classifies why a node exists and what kind of relationship an edge expresses without creating a second graph store.

## Five connected layers

| ID | Layer | What it connects |
|---|---|---|
| `historical` | Historical Knowledge | Events, dates, discoveries, people, institutions, and historical developments |
| `philosophical` | Philosophical Knowledge | Questions, assumptions, principles, arguments, ethics, and consequences |
| `scientific` | Scientific Knowledge | Claims, theories, laws, research, observations, methods, and evidence |
| `cross-disciplinary` | Cross-Disciplinary Relations | Concepts, models, and methods across two or more disciplines |
| `experimental` | Experimental Knowledge | Hypotheses, protocols, simulations, measurements, outcomes, replications, and failures |

## Storage contract

Layer classification is additive metadata on the existing graph node:

```json
{
  "id": "stable-node-id",
  "kind": "knowledge_concept",
  "title": "Human-readable title",
  "content": "The actual claim, event, question, or experiment record.",
  "source": { "type": "document", "ref": "stable-source-reference" },
  "metadata": {
    "knowledge_layer": "scientific",
    "knowledge": {
      "claim_type": "empirical",
      "evidence_status": "supported",
      "sources": [
        {
          "type": "paper",
          "ref": "https://example.org/paper",
          "title": "Source title",
          "published_at": "2025-01-01"
        }
      ],
      "limitations": ["Scope and uncertainty remain explicit."]
    }
  }
}
```

The example is a shape demonstration, not a factual claim. Replace the illustrative source before creating a real record.

Edges retain the existing `source`, `target`, and `relation` shape. Layer-aware edges add `metadata.knowledge_layer`, `metadata.provenance`, and optional numeric `metadata.confidence` between 0 and 1. The canonical relation vocabulary is in `manifest.json`.

## Validation rules

- Unclassified legacy nodes and edges remain valid; existing audit findings are not silently reinterpreted.
- Once a node declares `metadata.knowledge_layer`, its layer-specific required fields are enforced.
- Historical and scientific records require source references.
- Philosophical records must expose at least one question, assumption, principle, argument, ethical consideration, or consequence.
- Cross-disciplinary records must name at least two distinct disciplines and explain the mapping.
- Experimental records must state a hypothesis, method, and outcome status. `inconclusive` and `failed` are valid outcomes, not records to hide.
- Layer-aware edges must use a relation declared for that layer. Legacy edge relations remain untouched.
- Confidence is never fabricated. Omit it when it is not known.

## Beyond-Light mapping

Beyond-Light remains the research and exploration client; Mnemos `Knowledge` branch remains the durable graph. Its existing research records can map as follows:

| Beyond-Light record | Mnemos layer | Required preservation |
|---|---|---|
| `research_source` | `historical` or `scientific` | Publisher, publication date, URL/identifier, retrieval time |
| `research_run` | `experimental` when it contains a hypothesis/method/run; otherwise `scientific` | Inputs, method/engine, parameters, run ID, outputs, limits |
| `evidence_report` | `scientific` and/or `experimental` | Evidence status, supporting/refuting sources, uncertainty, replication and validation status |
| Assumption, ethical analysis, or conceptual argument | `philosophical` | Explicit assumptions, principles, question, argument, and consequences |
| A justified relation between domains | `cross-disciplinary` | At least two disciplines, shared concept, mapping rationale, and transfer limits |

A research run is not automatically a successful experiment. A simulation, analytical benchmark, and physical measurement must remain distinguishable. Do not invent evidence records or auto-promote a source's claim to fact.

## Validation

The canonical manifest is `knowledge/layers/manifest.json`. The graph publisher invokes `scripts/validate-knowledge-layers.ts` before generating the snapshot manifest. A malformed typed record blocks publication; existing untyped graph records remain backward-compatible.
