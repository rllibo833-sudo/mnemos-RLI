# Mnemos as an independent local-first memory tool

## Product boundary

Mnemos is an independent knowledge-memory tool/plugin and agent interface. It is not the LynOS APK and must not import LynOS Android UI classes or depend on PusingCuk. LynOS is one possible local client; CLI, MCP, other agents, and future clients remain first-class consumers.

## Offline-first behavior

The local SQLite store is authoritative while offline. Capture, lexical search, explicit links, graph rendering, and local MCP must work without a network or model API. Cloud storage is a separate optional capability; a deployed cloud endpoint is not synchronization.

## Memory lifecycle

- Treat captured information as durable evidence with provenance: source URI/path when available, capture time, content kind, tags, and stable ID.
- Prefer append-first observations and revisions over destructive in-place replacement when preserving history matters.
- Keep source evidence distinct from generated summaries, hypotheses, and conclusions.
- Model typed, directed relationships with provenance and confidence where supported. Never silently turn lexical overlap into a verified semantic link.
- Reconciliation records contradictions and supersession explicitly instead of silently erasing older evidence.
- A synthesis must link to the evidence it used and distinguish direct facts, inferences, unresolved conflicts, and uncertainty.
- Search remains explainable. Semantic retrieval or LLM synthesis is optional and must clearly report when the engine is unavailable; the core local tool must not pretend lexical search is AI reasoning.

## Storage scanning is a client capability

Mnemos core must not recursively scan a host's entire disk by default. A client explicitly grants roots or supplies files. Indexing must honor exclusions, file-size/type limits, symlinks and permission errors; store source fingerprints and indexed timestamps; support incremental re-indexing and stale-source detection; never upload local content implicitly. On Android, the LynOS client must use Android's Storage Access Framework and granted URI permissions, not request broad access without a concrete need.

## Deletion, export, and recovery

Export is portability/recovery, not the primary memory workflow. Snapshot import must not be mistaken for synchronization. Deletion and retention controls remain explicit privacy features; where policy permits, a tombstone can preserve sync correctness without retaining deleted content. Never claim that all copies are erased unless every index, cache, backup, and remote replica is accounted for.

## Client contract for LynOS

Keep a versioned, documented local interface that can expose:
- index granted folders/files, status, and progress;
- search and retrieve source snippets with provenance;
- traverse explicit relationships and show evidence-backed matches;
- submit a synthesis request and return a traceable result;
- report unsupported files, permission failures, stale index entries, and unavailable optional engines.

Do not couple this contract to Compose UI or assume Python is available inside an Android APK. A future Android implementation may use a native adapter while preserving portable data formats.

## Delivery status

This document defines the target architecture, not a claim that all features already exist. Current SQLite lexical search, explicit links, local MCP, graph rendering, and separate cloud endpoint are the existing foundation. Automatic disk scanning, semantic matching, evidence-grounded synthesis, and local/cloud synchronization require implementation and acceptance tests.
