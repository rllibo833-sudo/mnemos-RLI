# Mnemos-RLI roadmap — offline integrity and reconstruction

## Product identity

Mnemos-RLI is an offline engineer's tool for collecting scoped artifact evidence, comparing trusted or historical observations, and tracing the consequences of system changes. Its design principle is **evidence before conclusions**. It is inspired by the general problem space of integrity diagnostics, but maintains its own implementation, data model, workflow, and product identity.

This roadmap applies to `main` only. The online shared-memory direction on `Knowledge` and the future LynOS APK are separate scopes.

## Current baseline

Implemented in the current codebase:

- Local SQLite records and explicit graph relationships.
- Explicit-path device mapping with bounded static binary inspection.
- Full SHA-256 for files within the configured size limit and sampled fingerprints for larger files.
- Device snapshots, artifact history, and release manifest generation/verification.
- Graph evolution and evidence aggregation commands.
- A loopback live viewer that compares the latest two complete scans for the same device and scope.
- An active metadata-keyed hash cache for repeat scans.
- Local database diagnostics.

Known limitations that remain real:

- The mapper inventories detected binaries/executables in selected paths, not every filesystem object.
- OS and sandbox identification is partial; cross-platform metadata parity is not complete.
- Signature status may be unknown; complete Authenticode/codesign verification is not implemented.
- A hash mismatch proves byte difference against a baseline, not malicious modification.
- Dependency tracing and impact conclusions still depend on the completeness and correctness of extracted metadata.
- The live view is a bounded evidence list, not yet a full dependency-impact graph with clustering and advanced filters.
- The live viewer compares stored observations; it does not itself trigger a fresh scan.
- No local checkout was used to run manual validation during the latest repository change; CI is the automated validation source.

## Work sequence

### 1. Make evidence semantics trustworthy

- Keep incomplete scans from proving absence.
- Compare only compatible device/scope observations unless an explicit cross-environment comparison policy exists.
- Distinguish hash mismatch, missing artifact, new artifact, unknown evidence, and expected environment variation.
- Preserve baseline identity and scan provenance in every report.
- Treat sampled hashes as fingerprints, never as full SHA-256.

### 2. Improve collection quality

- Normalize OS, architecture, sandbox/container identity, ownership, permissions, timestamps, and file type consistently.
- Add platform-specific signature verification only where the platform tool is available and the result can be represented honestly.
- Make parser limits and unsupported formats explicit.
- Ensure cache invalidation follows file identity and metadata changes, with a safe fallback to recomputation.

### 3. Reconstruct dependency impact

- Validate extracted dependency edges before relying on them.
- Trace affected artifacts from an observed change to dependent components.
- Explain each conclusion with the source observations and edge path.
- Keep incomplete or ambiguous paths labelled unknown rather than inferring certainty.

### 4. Complete the engineer workflow

- Make CLI, daemon, and viewer share one evidence contract.
- Add explicit full-scan and scope-comparison workflows only when they actually trigger scans and report completion.
- Build the advanced graph view from stored evidence: affected nodes, one-hop context, folder clustering, and useful filters.
- Keep local HTTP access loopback-only unless a deliberate authentication boundary is added.
- Improve large-graph performance without sacrificing deterministic, inspectable output.

### 5. Product and repository hygiene

- Remove dead or misleading public CLI surfaces while preserving internal APIs that remain useful.
- Keep README, architecture, and roadmap aligned with shipped behavior; never document planned capabilities as complete.
- Keep `main` focused on offline integrity. Do not merge the online `Knowledge` branch wholesale.
- Avoid placeholder fixtures, duplicate docs, and repeated small commits. Prefer coherent, reviewable implementation units.

## Completion criteria

Mnemos-RLI is ready for a dependable first release when a user can scan a declared scope, reproduce the baseline comparison, distinguish change from damage, trace affected dependencies, inspect the supporting evidence, and export a report whose limits are explicit—all without network access or executing inspected artifacts.
