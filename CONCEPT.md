# Mnemos-RLI: Product concept

**Tagline:** Evidence before conclusions.

## Product promise

Mnemos-RLI is an offline integrity and reconstruction tool for engineers. It records scoped observations of binary artifacts and their metadata, compares those observations against historical scans or a trusted release manifest, and helps explain which components may be affected by a change.

It does not claim that every difference is damage. A reliable result identifies the baseline, scan scope, hash method, and limitations so an engineer can distinguish byte-level evidence from interpretation.

## Signature experience

The central visual is an evidence graph: artifact nodes, dependency relationships, scan provenance, and explicit status labels. Every finding should lead back to the observation that supports it. Unknown evidence stays visibly unknown; unsupported signature checks are never presented as valid.

## Product principles

- Offline by default; no cloud service is required for core integrity work.
- Inspect files statically; never execute an artifact to analyze it.
- Scan only explicitly selected paths.
- Compare like with like; cross-device and cross-OS differences require explicit context.
- Treat full hashes, sampled fingerprints, metadata, and signatures as different evidence classes.
- Preserve a clear distinction between observed facts and diagnostic conclusions.
- Keep the implementation independent from LynOS and from the online shared-memory product on the `Knowledge` branch.

## Out of scope for the current product

- Online shared memory synchronization and AI-agent memory services.
- Automatic malware verdicts or vulnerability certification.
- Claims of complete cross-OS coverage or universal signature verification.
- Unauthenticated remote exposure of the live viewer.
