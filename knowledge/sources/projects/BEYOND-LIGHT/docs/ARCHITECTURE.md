# Beyond-Light architecture

**Last reviewed:** 2026-11-04  
**Canonical branch:** `main`  
**Public site:** https://rllibo833-sudo.github.io/Beyond-Light/

## Runtime boundary

Beyond-Light's user-facing application is a static browser application:

- `docs/index.html` provides the UI.
- `docs/engine/*.js` provides deterministic browser-side computation and orchestration.
- `docs/data/` contains public JSONL/CSV and scientific catalog files.
- `docs/engine/mnemos-knowledge.js` reads the public `mnemos-RLI:Knowledge` branch directly using browser fetch.

The website does not call a Beyond-Light HTTP server. It does not require SnapDeploy, Docker, Node.js application hosting, a Java application server, Supabase credentials, or a private GitHub token. GitHub Pages is only static file hosting. Node.js in CI is a test runner, not a production runtime.

Java source is retained as an implementation reference and regression-test target while browser ports are developed. It is not part of the website runtime. The former Java container recipe and local server launcher have been removed; do not restore them as a deployment dependency. Android source is a separate experimental target.

## Browser data flow

1. Browser loads `docs/index.html` and its local JavaScript modules.
2. Browser engines perform the operations they explicitly support.
3. Public static records are read from `docs/data/`.
4. Mnemos retrieval fetches the Knowledge manifest, node files, and edge files from `https://raw.githubusercontent.com/rllibo833-sudo/mnemos-RLI/Knowledge/knowledge/`.
5. Browser-side lexical matching ranks loaded graph nodes and displays source metadata and related nodes.
6. User datasets and equation records remain on the current device using browser storage or explicit import/export.

There is no private request proxy, hidden remote execution, server-side persistence, or implicit sync. The chat composer routes recognized calculation commands to local browser engines; it does not call an application backend or LLM endpoint. A public Knowledge branch is public data; never place secrets or private records there.

## Browser engines and source mapping

- `symbolic.js`: bounded symbolic expression operations, including substitution and invertible equation isolation.
- `research-core.js` equation-composition workflow: isolate a shared variable, substitute into a second relation, and re-check SI dimensions.
- `research.js`: scientific catalog, dimensional checks, equation registry, and numerical benchmarks.
- `decision.js`: evidence classification and candidate ranking.
- `feasibility.js`: deterministic physics and engineering primitives.
- `feasibility-assessment.js`: staged feasibility assessment and imported component/material aggregation.
- `technology-design.js`: four browser domain candidate generators/evaluators and Pareto orchestration.
- `research-core.js`: browser request/plan contracts, deterministic routing, engine registry, workflow execution, and evidence reporting.
- `autonomous-model.js`: bounded multivariable feature-grammar search with one-/two-term candidate fits and deterministic internal cross-validation.
- `mnemos-knowledge.js`: direct read-only Knowledge graph retrieval and engine adapter.
- `chat-commands.js`: deterministic explicit-command routing from the chat composer into browser workflows; non-command questions remain on Mnemos Knowledge.

`docs/catalog.json` maps Java source modules to their browser counterpart and declares coverage. It is an internal maintainer catalog, not a user-facing feature list. A browser counterpart may be partial. Do not label a module fully ported until its operations, edge cases, input limits, errors, numerical conventions, and regression coverage have been checked against the Java source.

## Porting contract

For every Java-to-browser port:

1. Read the Java implementation and its regression checks.
2. Port deterministic behavior that can run without filesystem, server, or privileged network access.
3. Preserve supported operations, limits, errors, units, assumptions, and status semantics.
4. Add browser regression tests for normal cases, boundaries, invalid inputs, and known limitations.
5. Link the browser implementation to the exact source in `docs/catalog.json`.
6. Keep the catalog status partial until parity is demonstrated.
7. Never imply mathematical consistency or a benchmark pass is experimental validation.

## Current limits

- Graph search is bounded lexical matching, not semantic/vector retrieval.
- Knowledge and GitHub Raw availability depends on the network and browser CORS.
- User datasets are device-local; browser storage may be cleared or quota-limited.
- Open-data import depends on provider CORS and browser limits.
- General-relativity curvature uses finite differences and is numerically sensitive.
- Some Java modules have only bounded browser translations; consult `docs/catalog.json` and `docs/STATUS.md`.
- Autonomous-model feature normalization currently follows the Java reference by using full-dataset statistics before folds; this can leak distribution information into cross-validation and must not be interpreted as independent validation.
- A successful calculation or benchmark is not experimental validation or engineering certification.

## Evidence vocabulary

- **Mathematical consistency:** the implemented expression or relation is internally evaluable.
- **Physical consistency:** selected conservation or physical checks close within stated assumptions and tolerances.
- **Engineering screening:** reduced calculations pass within the supplied model and known data.
- **Numerical benchmark:** output agrees with an analytical/reference case within a declared tolerance.
- **Experimental support:** requires matched raw measurement data and test conditions.

These categories are not interchangeable. Unknown values remain unknown.

## Verification

Browser engine regression checks run in the Pages workflow. Java source regression checks run in the separate Java workflow. Neither workflow requires a hosted Java service. A successful static-site deployment only means the static artifact was published; it does not validate every scientific model.
