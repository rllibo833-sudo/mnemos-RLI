# Mnemos-RLI architecture

## Product direction

Mnemos-RLI on `main` is an **offline integrity-evidence and reconstruction tool**. Its core workflow is scoped collection → immutable observation history → baseline comparison → evidence-backed analysis. It is not the online shared-memory product represented by the separate `Knowledge` branch, and LynOS is not a runtime dependency.

## Current components

- **Local store:** Python standard-library SQLite, selected by `--db` or `MNEMOS_DB`.
- **Device mapper:** traverses only explicitly supplied paths and extracts bounded static metadata from recognized binaries and executable files.
- **Artifact evidence:** stores paths, metadata, full SHA-256 where permitted by the size limit, sampled fingerprints for larger files, and parser status.
- **Snapshots:** device inventory observations with scan scope, environment metadata, completeness, and a fingerprint used to avoid redundant snapshots.
- **Release manifests:** compare observed artifact hashes with an expected set from a selected snapshot.
- **Evolution and analysis:** reconcile artifact/dependency history and aggregate evidence into findings.
- **Hash cache:** caches full hashes against resolved path and filesystem identity metadata; a cache miss or stale identity triggers recomputation.
- **Live evidence viewer:** reads the store and compares the latest complete scan with the previous complete scan for the same device and scope. It does not initiate scans.
- **Database diagnostics:** SQLite integrity and foreign-key checks.

## Evidence model

A result should distinguish at least:

- **Match:** full hashes match the chosen baseline.
- **Hash mismatch:** full hashes differ; the cause is not inferred.
- **Missing:** a previously observed artifact is absent from a later complete scan of the same scope.
- **New/unexpected:** an artifact is present outside the baseline set.
- **Unknown:** scan completeness, hash quality, parsing, or scope is insufficient.
- **Environment drift:** observations differ by OS, architecture, sandbox, or another environment property and therefore need explicit comparison policy.

A sampled fingerprint is not interchangeable with a full SHA-256. An incomplete scan cannot prove an artifact is missing. A release manifest proves only the comparison against its contents; it does not authenticate the manifest author.

## Artifact Coverage & Scope Limitations

Coverage has separate event and integrity layers:

- The device mapper recognizes a bounded set of binary formats and records binary artifact evidence. SHA-256 comparison applies only to recognizable binary artifacts for which a full hash is available; sampled fingerprints are not full SHA-256 values.
- Text files and files that do not match a recognized binary format are **not currently tracked**. Metadata-only change tracking is not implemented, so the monitoring API must report `metadata_tracking: false`.
- Filesystem event monitoring can report activity such as access/open, create, modify, move, or delete where the active OS backend exposes those event types. Backend capabilities differ; an event record is not proof that content integrity was checked.
- Integrity-check coverage is consequently a subset of filesystem-event coverage. An event can concern a non-binary file that has no integrity-comparison record.
- `/api/monitoring-status` reports `artifact_coverage.total_paths_monitored` as the number of configured scope roots, `binary_artifacts_tracked` as binary artifacts linked to the latest device snapshot, and `integrity_check_capable_percent` as the percentage of files examined in that snapshot that were recognized as binary artifacts. This percentage is approximate and is not a score or proof of full filesystem coverage.

## Trust boundaries

- The scanner treats inspected files as untrusted data and never executes them.
- File parsing is bounded and may return unsupported/unknown for formats it cannot safely inspect.
- The live HTTP server binds to loopback by default and accepts only local bind addresses through its API.
- The live viewer uses DOM text nodes rather than injecting stored paths or reasons as HTML.
- The SQLite store and local cache are mutable local state; their contents are evidence inputs, not cryptographic attestations of provenance.
- OS detection, sandbox identification, and native signature verification are incomplete. Reports must not overstate them.

## Known gaps

The mapper does not constitute a complete filesystem audit. Cross-OS metadata normalization and native signature verification need further work. The current live viewer is a bounded comparison list rather than a complete impact graph with clustering and interactive dependency traversal. A viewer refresh rereads stored evidence; a separate scan is required to collect a new observation.

## Development rule

Implement the evidence path first, then update documentation. Do not describe a planned capability as shipped. Keep the offline integrity product separate from online memory synchronization and avoid adding duplicate documentation when an existing canonical file can be updated.
