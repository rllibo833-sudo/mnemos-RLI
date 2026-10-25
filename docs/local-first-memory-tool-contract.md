# Local-first memory tool contract — Knowledge product scope

## Product boundary

This contract describes the shared knowledge-memory tool and agent interface associated with the separate `Knowledge` branch. It is not the product contract for `main`, whose focus is offline integrity evidence and system reconstruction. Keep the two product directions separate: do not treat this target contract as proof that a feature is implemented on `main`, and do not modify the `Knowledge` branch while working on `main`.

The shared knowledge product is independent of the LynOS APK and must not depend on PusingCuk. LynOS may be a client; CLI, MCP, other agents, and future clients can remain consumers where implemented.

## Offline-first behavior

For the Knowledge product, the local SQLite store is authoritative while offline. Capture, lexical search, explicit links, graph rendering, and local MCP should work without a network or model API. Cloud storage is a separate optional capability; a deployed cloud endpoint alone is not synchronization.

## Memory lifecycle

- Treat captured information as durable evidence with provenance: source URI/path when available, capture time, content kind, tags, and stable ID.
- Prefer append-first observations and revisions over destructive in-place replacement when preserving history matters.
- Keep source evidence distinct from generated summaries, hypotheses, and conclusions.
- Model typed, directed relationships with provenance and confidence where supported. Never silently turn lexical overlap into a verified semantic link.
- Reconciliation records contradictions and supersession explicitly instead of silently erasing older evidence.
- A synthesis must link to the evidence it used and distinguish direct facts, inferences, unresolved conflicts, and uncertainty.
- Search remains explainable. Semantic retrieval or LLM synthesis is optional and must clearly report when the engine is unavailable; lexical search must not be presented as AI reasoning.

## Storage scanning is a client capability

The shared-memory core must not recursively scan a host's entire disk by default. A client explicitly grants roots or supplies files. Indexing must honor exclusions, file-size/type limits, symlinks and permission errors; store source fingerprints and indexed timestamps; support incremental re-indexing and stale-source detection; never upload local content implicitly. On Android, a client must use Android's Storage Access Framework and granted URI permissions rather than request broad access without a concrete need.

## Deletion, export, and recovery

Export is portability/recovery, not the primary memory workflow. Snapshot import must not be mistaken for synchronization. Deletion and retention controls remain explicit privacy features; where policy permits, a tombstone can preserve sync correctness without retaining deleted content. Never claim that all copies are erased unless every index, cache, backup, and remote replica is accounted for.

## Client contract

A future client interface may expose:
- index granted folders/files, status, and progress;
- search and retrieve source snippets with provenance;
- traverse explicit relationships and show evidence-backed matches;
- submit a synthesis request and return a traceable result;
- report unsupported files, permission failures, stale index entries, and unavailable optional engines.

Do not couple this contract to Compose UI or assume Python is available inside an Android APK. A native adapter may preserve portable data formats.

## Delivery status

This is a target contract for the Knowledge product, not a claim that every capability exists on either branch. Verify the relevant branch and implementation before describing behavior as shipped. Automatic disk scanning, semantic matching, evidence-grounded synthesis, and reliable local/cloud synchronization require implementation and acceptance evidence.
