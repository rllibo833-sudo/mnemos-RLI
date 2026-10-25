# Contributing to Mnemos-RLI

Mnemos-RLI on `main` is the offline integrity-evidence and system-reconstruction product. The online shared-memory direction on `Knowledge` and LynOS are separate scopes; changes here must not silently introduce dependencies on either.

## Ground rules

- Keep core scanning, evidence storage, snapshot comparison, analysis, and reporting usable offline.
- Follow the existing evidence path before adding a module, abstraction, command, or document. Reuse existing code when responsibilities overlap.
- Preserve evidence provenance, scan scope, completeness, hash quality, parser limitations, and uncertainty in every conclusion.
- Never execute inspected files during static analysis or claim a clean result when coverage is incomplete.
- Preserve compatibility with existing SQLite databases and exported data; avoid destructive schema changes.
- Never commit memory databases, exports containing personal data, credentials, or API keys.
- Update the existing canonical documentation when behavior changes; do not create duplicate documents for the same contract.

## Development

Requires Python 3.11+.

```bash
python -m unittest discover -s tests -v
python -m pip install --no-deps -e .
mnemos --help
```

Run the existing regression suite after implementation changes. Do not treat a successful import, CLI startup, or one smoke test as proof that the full evidence workflow is correct.

## Review expectations

A change should explain the user-visible problem, the existing execution path affected, compatibility implications, and verification actually performed. Prefer a coherent end-to-end correction over a chain of wrapper functions or unrelated small commits. Documentation must describe shipped behavior separately from planned work.
