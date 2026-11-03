# Beyond-Light source archive

This directory is a verbatim archive of research and experiment data imported from the Beyond-Light repository into the canonical Mnemos-RLI `Knowledge` branch.

## Provenance

- Source repository: https://github.com/rllibo833-sudo/Beyond-Light
- Source branch: `main`
- Source commit: `8fac43391796e3c61b2faa9ae42eb29415190c1f`
- Import date: 2026-11-04
- Original files are preserved as-is. The archive is additive; Beyond-Light originals were not deleted or rewritten.

## Imported records

| File | Records | Notes |
|---|---:|---|
| `benchmarks.jsonl` | 110 | 89 PASS, 15 FAIL, 6 theoretical engineering estimates. Computational checks, not physical experiments. |
| `datasets.jsonl` | 5 | Three unverified/synthetic fixtures and two NASA-linked RL10 transcriptions. |
| `experiments.jsonl` | 1 | Cross-source predictive screen; result did not outperform baseline and is not strict replication. |
| `material_curves.jsonl` | 27 | NIST polynomial/log-polynomial curve-fit records. |
| `materials.jsonl` | 18 | NASA/NIST-linked material reference records; not automatically design allowables. |
| `published_experiments.jsonl` | 8 | Published experiment summaries; not raw measurements unless explicitly stated. |
| `research_runs.jsonl` | 9 | Computational research/design runs; not physical measurement records. |
| `rl10_derivative_ii_1989_nasa_cr_179595.csv` | — | Source-linked RL10 derivative dataset transcription. |
| `rl10a_3_3b_1987_nasa_cr_183200.csv` | — | Source-linked RL10A dataset transcription. |
| `scientific-catalog.json` | 29 | Scientific constants and equation references with source/uncertainty notes. |

## Graph index

The collection-level graph nodes are in `knowledge/nodes/bl-*-v1.json`. They include searchable record indexes, source provenance, evidence classifications, and links to the verbatim archive files. Relationships are in `knowledge/edges/beyond-light-source-import.links.json`.

## Evidence rules

- Preserve source identity, source URLs, reported dates, units, uncertainty, conditions, and limitations.
- Do not relabel synthetic fixtures as official datasets.
- Do not treat a benchmark PASS as physical validation.
- Do not treat a simulation, model fit, or engineering estimate as a measured experiment.
- Preserve failed, inconclusive, and baseline-beating outcomes; do not hide failures or promote them to discoveries.
- Published-report summaries remain summaries until their underlying reports/raw data are separately ingested and checked.
