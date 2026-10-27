import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

async function main() {
const root = "knowledge";
const nodesDir = join(root, "nodes");
const edgesDir = join(root, "edges");
const jsonFiles = async (dir: string) => (await readdir(dir)).filter((f) => f.endsWith(".json")).sort();
const nodes = [];
for (const file of await jsonFiles(nodesDir)) nodes.push(JSON.parse(await readFile(join(nodesDir, file), "utf8")));
const ids = new Set(nodes.map((n: any) => n.id));
if (ids.size !== nodes.length) throw new Error("Duplicate node IDs");
const edges = [];
for (const file of (await readdir(edgesDir)).filter((f) => f.endsWith(".links.json")).sort()) {
  const rows = JSON.parse(await readFile(join(edgesDir, file), "utf8"));
  if (!Array.isArray(rows)) throw new Error(file + ": edge file must be an array");
  for (const e of rows) {
    if (!e.source || !e.target || !e.relation) throw new Error(file + ": malformed edge");
    if (!ids.has(e.source) || !ids.has(e.target)) throw new Error(file + ": dangling edge " + e.source + " -> " + e.target);
    edges.push(e);
  }
}
const reposAnalyzed = new Set(nodes.filter((n: any) => n.kind === "repository_audit").map((n: any) => n.source?.repository_url).filter(Boolean)).size;
const manifest = { schema_version: 1, source_of_truth: "mnemos-RLI:Knowledge", generated_at: new Date().toISOString(), nodes_count: nodes.length, edges_count: edges.length, repos_analyzed: reposAnalyzed, node_files: await jsonFiles(nodesDir), edge_files: (await readdir(edgesDir)).filter((f) => f.endsWith(".links.json")).sort(), workspaces: ["steadfast-living-shared"] };
await writeFile(join(root, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n", "utf8");
console.log(JSON.stringify({ ok: true, nodes: nodes.length, edges: edges.length, manifest: "knowledge/manifest.json" }));

}
main().catch(error => { console.error(error); process.exitCode = 1; });
