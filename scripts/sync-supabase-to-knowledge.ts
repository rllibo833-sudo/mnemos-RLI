import { createClient } from "@supabase/supabase-js";
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
const url = process.env.SUPABASE_URL!, key = process.env.SUPABASE_SERVICE_ROLE_KEY!, workspace = process.env.MNEMOS_WORKSPACE_ID!;
if (!url || !key || !workspace) throw new Error("Missing Supabase sync secrets");
const db = createClient(url, key, { auth: { persistSession: false } });
const [nr, er] = await Promise.all([
  db.from("knowledge_nodes").select("*").eq("workspace_id", workspace).is("deleted_at", null),
  db.from("knowledge_links").select("*").eq("workspace_id", workspace).is("deleted_at", null)
]);
if (nr.error || er.error) throw new Error(nr.error?.message || er.error?.message);
const nodes = nr.data || [], links = er.data || [], ids = new Set(nodes.map(n => n.id));
const sourceOf = (e: any) => e.source_id ?? e.source_node_id;
const targetOf = (e: any) => e.target_id ?? e.target_node_id;
if (links.some(e => !ids.has(sourceOf(e)) || !ids.has(targetOf(e)))) throw new Error("Supabase contains dangling graph edges");
const nd = "knowledge/nodes", ed = "knowledge/edges";
await mkdir(nd, { recursive: true }); await mkdir(ed, { recursive: true });
for (const f of await readdir(nd)) if (f.endsWith(".json")) await rm(join(nd, f));
for (const f of await readdir(ed)) if (f.endsWith(".links.json")) await rm(join(ed, f));
const safe = (s: string) => s.replace(/[^a-z0-9._-]/gi, "-").slice(0, 160);
for (const n of nodes) {
  const repo = n.kind === "repository_audit" && n.source?.repository_url;
  const name = repo ? "repo_" + safe(new URL(n.source.repository_url).pathname.split("/").filter(Boolean).join("-").toLowerCase()) : "finding_" + safe(n.id);
  await writeFile(join(nd, name + ".json"), JSON.stringify(n, null, 2) + "\n");
}
const grouped = new Map<string, any[]>();
for (const e of links) {
  const node = nodes.find(n => n.id === sourceOf(e));
  const repo = node?.source?.repository_url;
  const key = repo ? safe(new URL(repo).pathname.split("/").filter(Boolean).join("-").toLowerCase()) : "shared-knowledge";
  const arr = grouped.get(key) || [];
  arr.push({ source: sourceOf(e), target: targetOf(e), relation: e.relation, created_at: e.created_at, metadata: { ...(e.metadata || {}), provenance: e.provenance || null, confidence: e.confidence ?? null } });
  grouped.set(key, arr);
}
for (const [name, rows] of grouped) await writeFile(join(ed, name + ".links.json"), JSON.stringify(rows, null, 2) + "\n");
const reposAnalyzed = new Set(nodes.filter(n => n.kind === "repository_audit").map(n => n.source?.repository_url).filter(Boolean)).size;
const manifest = { schema_version: 1, source_of_truth: "mnemos-RLI:Knowledge", generated_at: new Date().toISOString(), nodes_count: nodes.length, edges_count: links.length, repos_analyzed: reposAnalyzed, workspace_id: workspace };
await writeFile("knowledge/manifest.json", JSON.stringify(manifest, null, 2) + "\n");
console.log(JSON.stringify({ nodes: nodes.length, edges: links.length }));
