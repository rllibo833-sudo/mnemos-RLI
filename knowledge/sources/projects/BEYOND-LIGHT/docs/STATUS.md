# Beyond-Light implementation status

**Snapshot date:** 2026-11-04  
**Runtime:** static browser application  
**Website:** https://rllibo833-sudo.github.io/Beyond-Light/  
**Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)

## Runtime status

The user-facing Beyond-Light website is static. It does not require SnapDeploy, a container, a Node.js application server, a Java HTTP server, a database service, or private API credentials. GitHub Pages serves the static files. CI may use Node.js to execute tests; this is not a production server.

Mnemos integration reads the public `mnemos-RLI/Knowledge` branch directly from the browser. The integration is read-only and uses no GitHub token. Local user datasets and equation records are stored in browser storage or imported/exported as files; there is no server synchronization.

The Java source tree remains in the repository as a reference and regression-test target for porting. The container recipe and local server launcher are removed. Java source is not loaded by the website.

## Browser capability inventory

- Static layered UI: Beranda, Fisika & matematika, Material & kimia, Riset & data.
- Browser symbolic mathematics: simplification, evaluation, differentiation, bounded integration, substitution, and bounded equation isolation.
- Dimensional equation composition: isolate a shared variable, substitute it into a second equation, and verify SI dimensional balance.
- Scientific catalog, SI dimensional checks, local equation registry, and analytical benchmarks.
- Physics and engineering primitives, including conservation, stress, buckling, thermal, electrical, and energy-condition screening.
- Staged propulsion feasibility assessment and imported component/material aggregation.
- Four browser technology-design domains with bounded candidate generation/evaluation and Pareto comparison.
- Browser research workflow registry, deterministic routing, local dataset analysis, bounded multivariable autonomous-model exploration, uncertainty analysis, integrated technology screening, and bounded open-data discovery/import.
- Chat command bridge for explicit browser calculations (symbolic operations, equation isolation, benchmark validation, local dataset analysis, multivariable model exploration, and Zenodo metadata search/research cycle); ordinary questions continue through Mnemos Knowledge.
- Direct Knowledge graph loading, lexical search, related-node lookup, and source display.

## Coverage and limitations

`docs/catalog.json` is the authoritative per-module coverage map. It deliberately distinguishes full browser counterparts, data-backed views, partial ports, Android-only code, and Java source references.

Known limitations include:

- Several Java algorithms are only bounded browser ports; exact parity is not claimed.
- Autonomous model exploration now searches bounded one- and two-term feature combinations across up to four selected predictors. Its normalization-before-folding behavior mirrors the Java reference and can leak distribution information across folds; results remain unverified candidates.
- The benchmark inventory contains 27 Java reference cases; 25 have browser evaluators and 2 remain inconclusive/unsupported.
- General-relativity curvature uses finite differences and is sensitive to coordinates and step size.
- Graph retrieval is lexical, not semantic/vector search.
- Open-data retrieval/import depends on provider availability, CORS, and browser storage limits.
- Browser storage is device-local and can be cleared by the user.
- No browser calculation, model screen, or analytical benchmark establishes experimental validation or build readiness.

## Verification

- Browser engine regression suites are run by `.github/workflows/pages.yml`.
- Java reference regression suites are run by `.github/workflows/java-research-core.yml`.
- Neither workflow starts or deploys a Beyond-Light application server.
- GitHub Pages publishes only the static `docs/` artifact.

See [README.md](../README.md) for the repository map and test commands.
