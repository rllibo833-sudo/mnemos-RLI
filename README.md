# Mnemos-RLI — offline integrity evidence and system reconstruction

Mnemos-RLI is an offline-first engineer's tool for recording scoped binary inventories, comparing observations, and preserving evidence about changes. It does not execute inspected files and does not require a cloud service.

Its identity is **evidence before conclusions**: a changed hash is a comparison result, not by itself proof of malicious tampering. Conclusions must retain their baseline, scan scope, and limitations.

## Current capabilities

- **Scoped device mapping:** inspect explicitly selected files/directories and collect bounded static metadata for recognized binaries and executable files.
- **Artifact evidence:** record paths, portable file metadata (file type, permissions, timestamps, ownership and filesystem identifiers where the host exposes them), full SHA-256 within the configured hashing limit, sampled fingerprints for larger files, and parser status. Platform-specific timestamp and ownership semantics remain explicit rather than being treated as universally equivalent.
- **Dependency impact:** connect changed/missing artifacts to potential downstream consumers using exact case-insensitive dependency basenames; reports preserve snapshot provenance and clearly mark the result as potential impact, not proof of runtime resolution or breakage.
- **Hash-cache safeguards:** reuse a full hash only when device/inode identity, size, modification time, and change time still match; malformed cache entries are ignored and cache writes are atomic with owner-only file permissions where supported. Files that change while being hashed are reported without a trusted digest.
- **Local history:** persist device snapshots and artifact relationships in SQLite for later comparison.
- **Release baseline:** create a manifest from a complete scan and compare another snapshot against it.
- **Graph analysis:** evolve artifact/dependency records and aggregate evidence into traceable findings.
- **Live evidence graph:** on refresh, compare stored snapshots and derive dependency-impact traces from changed evidence → candidate runtime dependency → active consumer artifacts. Each trace carries snapshot provenance, dependency source evidence, and explicit limitations; cross-device/scope and historical consumers are excluded. The loopback-only viewer computes analysis without writing results or running a new scan.
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

Cached SHA-256 values are an optimization, not a cryptographic attestation of the filesystem. Cache reuse checks file identity plus size, modification time, and change time; files observed changing during inspection lose their trusted digest. Privileged changes that preserve all available metadata cannot be ruled out by a metadata-keyed cache, so use a fresh trusted baseline or force a full re-hash when that threat model matters.

## Artifact Coverage & Scope Limitations

Mnemos-RLI separates filesystem event visibility from content-integrity evidence:

- **Hash comparison is limited to recognizable binary artifacts** detected by the device mapper. It is not a hash audit of every file in the selected roots.
- **Text and other unrecognized files are not currently tracked**, either by content hash or by metadata-only change detection. The current monitoring API therefore reports `metadata_tracking: false`. A metadata-only mode would need to be implemented and explicitly enabled before this can be reported as true.
- **Event monitoring is not an integrity verdict.** Depending on the operating-system backend, the daemon can record filesystem events such as access/open, create, modify, move, and delete under watched roots. Those events describe observed activity; they do not prove that file contents were hashed or validated.
- **Integrity-check coverage is a subset of event-monitor coverage.** A file event may be observed for a path that is not a recognized binary artifact and therefore has no corresponding binary hash comparison. Periodic scans can also miss short-lived changes between scans when the OS event backend is unavailable.
- The `/api/monitoring-status` response exposes `artifact_coverage`: watched root count, binary artifacts linked to the latest device snapshot, whether metadata-only tracking is active, and the approximate share of files examined that were recognized as binary artifacts. The percentage is a coverage indicator, not a security score; it can be zero when no scan denominator is available.

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


## Background daemon and startup service

Run a foreground daemon for an explicitly selected scan scope:

```sh
mnemos daemon --path ./path-to-inspect --interval 300
```

On Linux with systemd, register and start a **user-level** service (no root privileges):

```sh
mnemos daemon --path ./path-to-inspect --interval 300 --enable-service
systemctl --user status mnemos
systemctl --user is-enabled mnemos
mnemos doctor
```

The generated unit is `~/.config/systemd/user/mnemos.service`. It runs as the current user and is managed with `systemctl --user`; it is not a system-wide service. To allow user services to start at boot without an interactive login, the host administrator may separately enable lingering with `loginctl enable-linger USER`. Mnemos does not change this administrator-level policy automatically.

To stop and remove the user-level service:

```sh
mnemos daemon --path ./path-to-inspect --disable-service
```

A system-level service is a separate administrator-managed installation, typically at `/etc/systemd/system/mnemos.service`, managed with `sudo systemctl`. Mnemos' enable/disable flags manage only the current user's service and never edit or disable a system-level unit.
