import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const base = process.env.SUPABASE_URL?.replace(/\/$/, "");
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!base || !key) throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required");
const headers = { apikey: key, Authorization: "Bearer " + key, Accept: "application/json" };
const response = await fetch(base + "/rest/v1/mnemos_outbox?select=id,workspace_id,event_type,payload,payload_sha256,created_at&delivered_at=is.null&order=created_at.asc,id.asc&limit=100", { headers });
if (!response.ok) throw new Error("Outbox read failed HTTP " + response.status + ": " + (await response.text()).slice(0, 500));
const events = await response.json();
const canonical = (v: any): string => v === null || typeof v !== "object" ? JSON.stringify(v) : Array.isArray(v) ? "[" + v.map(canonical).join(",") + "]" : "{" + Object.keys(v).sort().map(k => JSON.stringify(k) + ":" + canonical(v[k])).join(",") + "}";
const sha = (v: unknown) => createHash("sha256").update(canonical(v)).digest("hex");
const safe = (v: string) => v.replace(/[^a-z0-9._-]/gi, "-").slice(0, 180);
const nodeDir = "knowledge/nodes", edgeDir = "knowledge/edges";
await mkdir(nodeDir, { recursive: true }); await mkdir(edgeDir, { recursive: true });
const acknowledgements: { id: string; payload_sha256: string }[] = [];
for (const event of events) {
  if (!event.id || !event.payload || sha(event.payload) !== event.payload_sha256) throw new Error("Outbox event checksum mismatch: " + event.id);
  if (event.event_type !== "knowledge.graph.upsert.v1") throw new Error("Unsupported outbox event type: " + event.event_type);
  const nodes = event.payload.nodes;
  const edges = event.payload.edges;
  if (!Array.isArray(nodes) || !Array.isArray(edges) || (nodes.length === 0 && edges.length === 0)) throw new Error("Malformed graph event: " + event.id);
  const ids = new Set(nodes.map((n: any) => n.id));
  if (ids.size !== nodes.length || nodes.some((n: any) => !n.id || !n.kind || typeof n.content !== "string")) throw new Error("Invalid/duplicate nodes in event " + event.id);
  for (const edge of edges) if (!edge.source || !edge.target || !edge.relation || (!ids.has(edge.source) && !edge.external_source) || (!ids.has(edge.target) && !edge.external_target)) throw new Error("Malformed edge in event " + event.id);
  for (const node of nodes) {
    const path = join(nodeDir, safe(String(node.id)) + ".json");
    let existing: any = null;
    try { existing = JSON.parse(await readFile(path, "utf8")); } catch {}
    const merged = { ...(existing || {}), ...node, workspace_id: event.workspace_id, source: { ...(existing?.source || {}), ...(node.source || {}), transport_event_id: event.id } };
    await writeFile(path, JSON.stringify(merged, null, 2) + "\n");
  }
  if (edges.length) {
    const filename = "transport-" + safe(event.id) + ".links.json";
    await writeFile(join(edgeDir, filename), JSON.stringify(edges, null, 2) + "\n");
  }
  const attempt = await fetch(base + "/rest/v1/mnemos_outbox?id=eq." + encodeURIComponent(event.id) + "&delivered_at=is.null", { method: "PATCH", headers: { ...headers, "Content-Type": "application/json", Prefer: "return=minimal" }, body: JSON.stringify({ attempts: Number(event.attempts || 0) + 1, last_error: null }) });
  if (!attempt.ok) throw new Error("Could not record outbox attempt for " + event.id);
  acknowledgements.push({ id: event.id, payload_sha256: event.payload_sha256 });
}
await writeFile(".mnemos-outbox-acks.json", JSON.stringify(acknowledgements, null, 2) + "\n");
console.log(JSON.stringify({ pending_events: events.length, imported_nodes: events.reduce((n: number, e: any) => n + e.payload.nodes.length, 0), imported_edges: events.reduce((n: number, e: any) => n + e.payload.edges.length, 0) }));
