# First-run guide

This guide takes a new user from a clean checkout to a first saved observation without requiring a cloud account, external service, or API key.

## Requirements

- Python 3.11 or newer.
- Git.
- A terminal.
- A directory whose contents you are authorized to inspect.

Mnemos-RLI is an offline-first local tool. It does not execute inspected files. Its current integrity inventory is limited to recognized binary/executable artifacts; it is not a complete filesystem scanner, malware detector, or vulnerability scanner.

## 1. Install

```sh
git clone https://github.com/rllibo833-sudo/mnemos-RLI.git
cd mnemos-RLI
python -m venv .venv
```

Linux/macOS:

```sh
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Windows PowerShell: activate with `.venv\\Scripts\\Activate.ps1`, then run `python -m pip install .`.

## 2. Check the installation

```sh
mnemos --help
mnemos doctor
```

The CLI help is the source of truth for supported commands. `doctor` reports local SQLite and relationship diagnostics. On Linux it can also report a missing user-level systemd service as a failure; that is relevant only if you intend to run the background service. A one-shot scan does not require enabling the service.

## 3. Record an observation

Choose one small directory first. Do not point the tool at the entire root filesystem for a first run.

```sh
mnemos map-device --path ./directory-to-inspect
```

The JSON output includes `snapshot_id`, scan scope, completeness, and artifact counts. Keep the snapshot ID if you need to compare it later. Only paths explicitly passed with `--path` are in scope.

## 4. Compare later evidence

Run the same command again after a meaningful change or at a later time:

```sh
mnemos map-device --path ./directory-to-inspect
mnemos analyze
```

Compare the two JSON outputs and their snapshot IDs. The live terminal view can be opened with `mnemos live-graph`; the browser view is opt-in with `mnemos live-graph --web`. Both read stored observations and do not initiate a scan themselves.

Interpret results conservatively:

- A full-hash mismatch means the bytes differ from the selected baseline; it does not explain why.
- A missing artifact is meaningful only when both observations cover the same scope and the later scan is complete.
- A sampled fingerprint is not a full SHA-256.
- An unrecognized file may not have an integrity record at all.
- A passing diagnostic or CI run does not prove that every file type or platform behavior is covered.

## 5. Optional release manifest

A manifest can be created only from a complete snapshot with at least one recognized binary artifact and a full SHA-256 for each included entry:

```sh
mnemos map-device --path ./release-directory
# Copy snapshot_id from the first JSON result:
mnemos release-manifest --snapshot-id SNAPSHOT_ID --release-id RELEASE_ID --output release-manifest.json
mnemos map-device --path ./release-directory
# Copy snapshot_id from the second JSON result:
mnemos verify-release --manifest release-manifest.json --snapshot-id CURRENT_SNAPSHOT_ID
```

Replace uppercase placeholders with actual IDs and choose a meaningful release ID. A manifest records expected hashes; it is not signed and does not establish the identity of its creator. Store and distribute it through a separate trusted channel.

## Troubleshooting

- **`mnemos: command not found`:** activate the virtual environment again, confirm installation succeeded, and run `python -m pip show mnemos-rli`.
- **No recognized artifacts:** the chosen path may contain only formats the current mapper does not recognize. This is a coverage limitation, not proof the directory is empty or safe.
- **`doctor` reports a service problem on Linux:** if you only want a one-shot scan, continue with `mnemos map-device`; service registration is for the optional daemon.
- **The browser viewer does not start:** run `mnemos live-graph --web --port 8765` and check whether another local process already uses that port. Keep the server bound to loopback; do not expose it publicly.

## What is not required

No cloud service, Supabase project, API key, marketplace registration, or public account is required to use the local integrity workflow.
