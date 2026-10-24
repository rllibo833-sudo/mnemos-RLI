# Mnemos-RLI — offline integrity evidence and system reconstruction

Mnemos-RLI is an offline-first engineer's tool for recording scoped binary inventories, comparing observations, and preserving evidence about changes. It does not execute inspected files and does not require a cloud service.

Its identity is **evidence before conclusions**: a changed hash is a comparison result, not by itself proof of malicious tampering. Conclusions must retain their baseline, scan scope, and limitations.

## Current capabilities

- **Scoped device mapping:** inspect explicitly selected files/directories and collect bounded static metadata for recognized binaries and executable files.
- **Artifact evidence:** record paths, file metadata, full SHA-256 where within the configured hashing limit, sampled fingerprints for larger files, and parser status.
- **Local history:** persist device snapshots and artifact relationships in SQLite for later comparison.
- **Release baseline:** create a manifest from a complete scan and compare another snapshot against it.
- **Graph analysis:** evolve artifact/dependency records and aggregate evidence into traceable findings.
- **Live evidence view:** compare the latest complete scan with the previous complete scan for the same device and scope. The server binds to loopback by default and reads stored records only.
- **Offline operation:** scanning, storage, comparison, and viewing do not need network access.

## Quick start

Install from the repository using your preferred Python environment, then run:

```sh
mnemos doctor
mnemos map-device --path ./path-to-inspect
mnemos live-graph
```

Open the local URL printed by `live-graph`. Repeat `map-device` with the same scope to create a second observation for comparison. A single scan is a baseline, not enough evidence to conclude that an artifact is damaged.

Create and verify a trusted release manifest:

```sh
mnemos map-device --path ./release-directory
mnemos release-manifest --snapshot-id SNAPSHOT_ID --release-id RELEASE_ID --output release-manifest.json
mnemos map-device --path ./release-directory
mnemos verify-release --manifest release-manifest.json --snapshot-id SNAPSHOT_ID
```

Replace the example IDs with values printed by the actual command. A manifest's hash list does not authenticate who created it; protect the manifest through a separate trusted distribution or signing process.

## Evidence semantics

- **MATCH:** the full SHA-256 matches the selected comparison baseline.
- **HASH_MISMATCH / different:** full hashes differ. This proves byte differences, not their cause.
- **MISSING:** an artifact seen in the prior complete scan is absent from the latest complete scan of the same scope.
- **NEW_FILE / unexpected:** an artifact appears that was not in the baseline. This is not automatically damage.
- **UNKNOWN:** evidence is incomplete, a full hash is unavailable, or the scan cannot support a reliable conclusion.
- **Environment variation:** observations from different devices or scopes must not be treated as directly comparable merely because their paths match.

Sampled fingerprints are not full-content hashes. A scan covers only the explicitly selected scope and detected artifact types; it is not a full filesystem audit, malware verdict, vulnerability scanner, or proof of code-signing validity.

## Safety and boundaries

- Only scan paths you are authorized to inspect.
- Inspection is static: Mnemos-RLI does not execute the files it analyzes.
- The live viewer is loopback-only by default. Do not expose it to a LAN or public network without a deliberate authenticated access design.
- Platform recognition and signature verification are incomplete; unknown signature status must remain unknown.
- No remote sync is required for the offline integrity workflow.

## Product boundary

The `main` branch is the offline integrity/reconstruction product. The separate `Knowledge` branch represents the online shared-memory direction and is not part of this main-branch product contract. LynOS is a separate future consumer, not a runtime dependency of Mnemos-RLI.

## Development status

This is an evolving engineering tool. The current CI suite passing means the existing automated checks passed; it does not establish complete cross-OS coverage or guarantee every diagnostic path. Changes should improve real evidence handling rather than add placeholder output, duplicate documentation, or tests that substitute for implementation.
