# Living Knowledge Network — Knowledge branch scope

## Product boundary

The Living Knowledge Network is the shared knowledge-graph direction maintained on the separate `Knowledge` branch. It is intended for agent-neutral shared memory and knowledge relationships, with local and server-backed components where implemented. This document describes that product direction; it is **not** the architecture contract for `main`.

Do not treat this plan as evidence that online synchronization, cloud reconciliation, or shared-graph behavior is shipped on `main`. Do not move Knowledge-branch implementation into `main` implicitly, and do not modify the `Knowledge` branch as part of work scoped to `main`.

## Main branch boundary

The `main` branch is the offline integrity-evidence and system-reconstruction product. Its current canonical references are:

- `README.md` — user-facing capabilities, commands, and limitations.
- `CONCEPT.md` — product promise and boundaries.
- `docs/architecture.md` — implemented components and evidence flow.
- `ROADMAP.md` — current baseline and planned work for `main`.

For `main`, the authoritative flow is explicit-path collection → local evidence records and snapshots → like-for-like integrity comparison → provenance-preserving analysis and reports. The core does not require a server, does not execute inspected artifacts, and must not claim full filesystem coverage when the mapper only identifies recognized binary candidates.

## Knowledge-branch direction

The shared-knowledge product may use a local store, graph relationships, agent adapters, and a separately authenticated server implementation. Each capability must be verified against the code on `Knowledge` before being described as implemented. A deployed endpoint by itself does not establish synchronization, conflict resolution, ownership isolation, or reliable reconciliation.

When work is performed on `Knowledge`, audit its own entry points, data model, local/cloud boundary, authentication, synchronization semantics, and tests in that branch. Preserve its identity as the shared knowledge graph; do not substitute the offline forensic workflow for it.

## Documentation rule

Keep this document as a scope boundary and planning reference for the Knowledge product. Record shipped behavior only after inspecting the relevant branch and implementation. Keep `main` documentation about the offline evidence product, and update existing canonical documents rather than creating overlapping Markdown files.
