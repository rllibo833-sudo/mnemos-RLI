# Mnemos-RLI Knowledge → Beyond-Light browser flow

## Purpose

Beyond-Light reads the public canonical `mnemos-RLI:Knowledge` branch directly from the browser. This is a read-only static integration: no Beyond-Light API server, proxy, Supabase outbox, LLM backend, runtime secret, or GitHub token is involved.

## Request flow

1. The browser loads `docs/index.html` and `docs/engine/mnemos-knowledge.js`.
2. The Knowledge module fetches `knowledge/manifest.json` from the public `Knowledge` branch on GitHub Raw.
3. It loads the manifest-declared node and edge files with bounded concurrency.
4. It performs bounded lexical matching in the browser and returns matching nodes, evidence labels, source links, and related graph nodes.
5. `docs/engine/research-core.js` routes supported research workflows to local browser engines. Calculations remain deterministic and execute on the current device.
6. The UI presents the retrieved Knowledge context separately from calculations and evidence limitations.

## Source and privacy boundary

- Canonical read-only source: `https://raw.githubusercontent.com/rllibo833-sudo/mnemos-RLI/Knowledge/knowledge/`
- No token or private credential is embedded in the website.
- Knowledge data must be treated as public because the browser reads a public branch.
- User-imported datasets and equation records remain local to the browser; there is no server-side account sync or research outbox.
- Retrieval depends on network access, GitHub Raw availability, and browser CORS behavior.

## Evidence boundaries

- Graph matching is lexical, not semantic/vector retrieval.
- A graph match is not proof. Synthetic fixtures, model outputs, failed benchmarks, theoretical estimates, and unverified records retain their evidence labels.
- The browser workflow router is deterministic. It is not an LLM and does not claim hidden AI reasoning.
- Engine outputs retain their assumptions and limitations. A calculation or screening result is not experimental validation.

## Verification

- Check that `docs/engine/mnemos-knowledge.js` loads the public manifest and reports missing node/edge files.
- Run `node docs/engine/research-core.test.cjs` and the other browser regression suites listed in the root README.
- Verify the website with the GitHub Pages preview after static build.
