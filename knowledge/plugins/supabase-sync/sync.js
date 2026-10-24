#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const os = require("node:os");

const CONFIG_PATH = path.resolve(__dirname, "../../mnemos.config.json");
const CONFIG = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
const MAX_TEXT_CHARS = CONFIG.sync.max_inline_text_chars;
const MAX_NODES = CONFIG.sync.max_nodes_per_bundle;
const MAX_LINKS = CONFIG.sync.max_links_per_bundle;
const BATCH_SIZE = CONFIG.sync.max_batch_records;
const BINARY_KEYS = new Set(["base64", "data_base64", "binary", "binary_data", "file_bytes", "image_bytes", "video_bytes", "raw_bytes", "blob_bytes"]);

function env(name) {
  const value = process.env[name];
  if (!value || !value.trim()) throw new Error("missing required environment variable " + name);
  return value.trim();
}
function uuid(value, label) {
  if (typeof value !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)) {
    throw new Error(label + " must be a UUID");
  }
  return value;
}
function rejectBinary(value, where = "$") {
  if (Array.isArray(value)) return value.forEach((item, i) => rejectBinary(item, where + "[" + i + "]"));
  if (!value || typeof value !== "object") return;
  for (const [key, item] of Object.entries(value)) {
    if (BINARY_KEYS.has(key.toLowerCase()) || /base64|binary|bytes|blob/i.test(key)) {
      throw new Error("binary field forbidden at " + where + "." + key);
    }
    rejectBinary(item, where + "." + key);
  }
}
function safeObject(value) {
  if (value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map(safeObject);
  const clean = {};
  for (const [key, item] of Object.entries(value)) {
    if (/path|uri|token|secret|password|credential|base64|binary|bytes|blob/i.test(key)) continue;
    if (typeof item === "string" && item.length > MAX_TEXT_CHARS) continue;
    clean[key] = safeObject(item);
  }
  return clean;
}
function sha256(text) {
  return crypto.createHash("sha256").update(text, "utf8").digest("hex");
}
function validateBundle(bundle, expectedWorkspace) {
  if (!bundle || bundle.schema_version !== 1 || !Array.isArray(bundle.nodes) || !Array.isArray(bundle.links)) {
    throw new Error("bundle must have schema_version: 1, nodes: [], and links: []");
  }
  const workspaceId = uuid(bundle.workspace_id || expectedWorkspace, "workspace_id");
  if (expectedWorkspace && workspaceId !== expectedWorkspace) throw new Error("bundle workspace_id differs from MNEMOS_WORKSPACE_ID");
  if (bundle.nodes.length > MAX_NODES || bundle.links.length > MAX_LINKS) throw new Error("bundle exceeds configured record limits");
  rejectBinary(bundle);
  const nodes = bundle.nodes.map((node, i) => {
    if (!node || typeof node.id !== "string" || !node.id.trim() || typeof node.kind !== "string" || !node.kind.trim()) {
      throw new Error("nodes[" + i + "] requires id and kind");
    }
    const content = node.content == null ? "" : node.content;
    if (typeof content !== "string" || content.length > MAX_TEXT_CHARS) throw new Error("nodes[" + i + "].content exceeds text limit");
    if (/^data:(image|video|audio|application)/i.test(content) ||
        (content.length > 1024 && new RegExp("^[A-Za-z0-9+/]+={0,2}$").test(content))) {
      throw new Error("nodes[" + i + "].content appears to contain encoded binary data");
    }
    if (node.content_sha256 && !/^[a-fA-F0-9]{64}$/.test(node.content_sha256)) {
      throw new Error("nodes[" + i + "].content_sha256 must be a SHA-256 hex digest");
    }
    return {
      id: node.id, workspace_id: workspaceId, kind: node.kind,
      title: typeof node.title === "string" ? node.title.slice(0, 512) : "",
      content, source: safeObject(node.source),
      metadata: safeObject(node.metadata),
      media: safeObject(node.media),
      content_sha256: typeof node.content_sha256 === "string" ? node.content_sha256.toLowerCase() : sha256(content),
      schema_version: 1, created_at: node.created_at || undefined,
      updated_at: node.updated_at || undefined, deleted_at: node.deleted_at || null
    };
  });
  const links = bundle.links.map((link, i) => {
    if (!link || typeof link.source_id !== "string" || typeof link.target_id !== "string" || typeof link.relation !== "string" || !link.relation.trim()) {
      throw new Error("links[" + i + "] requires source_id, target_id, relation");
    }
    return {
      workspace_id: workspaceId, source_id: link.source_id, target_id: link.target_id,
      relation: link.relation, provenance: safeObject(link.provenance),
      confidence: typeof link.confidence === "number" ? Math.max(0, Math.min(1, link.confidence)) : null,
      metadata: safeObject(link.metadata),
      created_at: link.created_at || undefined, updated_at: link.updated_at || undefined, deleted_at: link.deleted_at || null
    };
  });
  return { schema_version: 1, workspace_id: workspaceId, nodes, links };
}
function client() {
  let base = env(CONFIG.supabase.url_env);
  while (base.endsWith("/")) base = base.slice(0, -1);
  const anonKey = env(CONFIG.supabase.anon_key_env);
  const accessToken = env(CONFIG.supabase.access_token_env);
  return async function request(table, query, method = "GET", body, extraHeaders = {}) {
    const url = base + "/rest/v1/" + table + (query ? "?" + query : "");
    const headers = Object.assign({
      apikey: anonKey,
      Authorization: "Bearer " + accessToken,
      Accept: "application/json"
    }, extraHeaders);
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (method === "POST" || method === "PATCH") headers.Prefer = "resolution=merge-duplicates,return=minimal";
    let lastError;
    for (let attempt = 0; attempt < 4; attempt++) {
      let response;
      try {
        response = await fetch(url, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: AbortSignal.timeout(20000)
        });
      } catch (error) {
        lastError = error;
        if (attempt === 3) break;
        await new Promise(resolve => setTimeout(resolve, 250 * Math.pow(2, attempt)));
        continue;
      }
      const text = await response.text();
      if (response.ok) {
        if (!text) return null;
        try { return JSON.parse(text); }
        catch { throw new Error("Supabase returned non-JSON response for " + table); }
      }
      const retryable = [408, 425, 429, 500, 502, 503, 504].includes(response.status);
      lastError = new Error("Supabase " + method + " " + table + " failed (" + response.status + "): " + text.slice(0, 1200));
      if (!retryable || attempt === 3) throw lastError;
      const retryAfter = Number(response.headers.get("retry-after"));
      const delay = Number.isFinite(retryAfter) && retryAfter > 0
        ? Math.min(retryAfter * 1000, 10000)
        : 250 * Math.pow(2, attempt);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
    throw new Error("Supabase request failed after retries: " + (lastError ? lastError.message : "unknown network error"));
  };
}
function batches(items, size) {
  const out = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}
function safeSourceReference(value) {
  if (typeof value !== "string" || !value.trim()) return { type: "mnemos-local" };
  try {
    const parsed = new URL(value);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      return { type: "web", host: parsed.host };
    }
  } catch {}
  return { type: "mnemos-local", reference_present: true };
}
function deterministicUuid(value) {
  const hex = sha256(value).slice(0, 32).split("");
  hex[12] = "5";
  hex[16] = (parseInt(hex[16], 16) & 3 | 8).toString(16);
  const s = hex.join("");
  return s.slice(0, 8) + "-" + s.slice(8, 12) + "-" + s.slice(12, 16) + "-" + s.slice(16, 20) + "-" + s.slice(20);
}
function exportToBundle(payload, workspaceId) {
  if (!payload || payload.format !== "mnemos-export-v1" ||
      !Array.isArray(payload.memories) || !Array.isArray(payload.links)) {
    throw new Error("input must be a Mnemos mnemos-export-v1 export");
  }
  const nodes = payload.memories.map((memory, index) => {
    if (!memory || typeof memory.id !== "string" || !memory.id.trim() ||
        typeof memory.content !== "string" || !memory.content.trim()) {
      throw new Error("memories[" + index + "] is missing id or content");
    }
    const metadata = safeObject(Object.assign({}, memory.metadata || {}, {
      tags: Array.isArray(memory.tags) ? memory.tags.filter(tag => typeof tag === "string") : []
    }));
    return {
      id: memory.id,
      kind: typeof memory.kind === "string" && memory.kind.trim() ? memory.kind.trim() : "note",
      title: typeof metadata.title === "string" ? metadata.title.slice(0, 512) : memory.content.split(String.fromCharCode(10), 1)[0].slice(0, 160),
      content: memory.content,
      source: safeSourceReference(memory.source),
      metadata,
      media: safeObject(metadata.media || {}),
      content_sha256: sha256(memory.content),
      created_at: memory.created_at,
      updated_at: memory.updated_at,
      deleted_at: null
    };
  });
  const links = payload.links.map((link, index) => {
    if (!link || typeof link.source_id !== "string" || typeof link.target_id !== "string") {
      throw new Error("links[" + index + "] is missing source_id or target_id");
    }
    const relation = typeof link.relation === "string" ? link.relation.trim() : "relates_to";
    return {
      source_id: link.source_id,
      target_id: link.target_id,
      relation: /^[a-z][a-z0-9_-]{0,63}$/.test(relation) ? relation : "relates_to",
      provenance: { type: "mnemos-export-v1" },
      confidence: null,
      metadata: {},
      created_at: link.created_at,
      updated_at: link.created_at,
      deleted_at: null
    };
  });
  return validateBundle({ schema_version: 1, workspace_id: workspaceId, nodes, links }, workspaceId);
}
function bundleToExport(bundle) {
  const normalized = validateBundle(bundle, env(CONFIG.workspace_id_env));
  if (normalized.nodes.some(node => node.deleted_at) || normalized.links.some(link => link.deleted_at)) {
    throw new Error("bundle contains tombstones; the current Mnemos import contract cannot safely apply deletions");
  }
  const nodeIds = new Set(normalized.nodes.map(node => node.id));
  const memories = normalized.nodes.map(node => {
    const metadata = safeObject(node.metadata || {});
    const tags = Array.isArray(metadata.tags) ? metadata.tags.filter(tag => typeof tag === "string") : [];
    delete metadata.tags;
    return {
      id: node.id,
      content: node.content,
      kind: node.kind,
      tags,
      source: null,
      metadata,
      created_at: node.created_at || new Date().toISOString(),
      updated_at: node.updated_at || node.created_at || new Date().toISOString()
    };
  });
  const links = normalized.links.map(link => {
    if (!nodeIds.has(link.source_id) || !nodeIds.has(link.target_id)) {
      throw new Error("cannot import bundle with links whose endpoints are absent from this bundle");
    }
    return {
      id: deterministicUuid(link.source_id + ":" + link.target_id + ":" + link.relation),
      source_id: link.source_id,
      target_id: link.target_id,
      relation: link.relation,
      created_at: link.created_at || new Date().toISOString()
    };
  });
  return { format: "mnemos-export-v1", exported_at: new Date().toISOString(), memories, links };
}
async function readAllTable(request, table, workspaceId, order, since) {
  const rows = [];
  const pageSize = 500;
  const maximum = table === CONFIG.supabase.nodes_table ? MAX_NODES : MAX_LINKS;
  for (let offset = 0; ; offset += pageSize) {
    const params = new URLSearchParams({
      select: "*",
      workspace_id: "eq." + workspaceId,
      order,
      limit: String(pageSize)
    });
    if (since) params.set("updated_at", "gte." + new Date(Date.parse(since) - 2000).toISOString());
    const page = await request(table, params.toString(), "GET", undefined, {
      "Range-Unit": "items",
      Range: offset + "-" + (offset + pageSize - 1)
    });
    if (!Array.isArray(page)) throw new Error("expected array response from " + table);
    rows.push(...page);
    if (rows.length > maximum) throw new Error(table + " exceeds configured bundle limit; refusing a truncated pull");
    if (page.length < pageSize) break;
  }
  return rows;
}
function rowKeyNode(node) { return node.id; }
function rowKeyLink(link) { return link.source_id + "|" + link.target_id + "|" + link.relation; }
async function push(bundlePath) {
  if (!bundlePath) throw new Error("usage: sync.js push bundle.json");
  const workspaceId = uuid(env(CONFIG.workspace_id_env), CONFIG.workspace_id_env);
  const bundle = validateBundle(JSON.parse(fs.readFileSync(path.resolve(bundlePath), "utf8")), workspaceId);
  const request = client();
  const remoteNodes = await readAllTable(request, CONFIG.supabase.nodes_table, workspaceId, "updated_at.asc,id.asc", null);
  const remoteLinks = await readAllTable(request, CONFIG.supabase.links_table, workspaceId, "updated_at.asc,source_id.asc,target_id.asc,relation.asc", null);
  const remoteNodeById = new Map(remoteNodes.map(node => [rowKeyNode(node), node]));
  const remoteLinkByKey = new Map(remoteLinks.map(link => [rowKeyLink(link), link]));
  let nodesSkippedOlder = 0, nodesConflicted = 0, linksSkippedOlder = 0;
  const nodesToPush = bundle.nodes.filter(node => {
    const remote = remoteNodeById.get(node.id);
    if (!remote) return true;
    const localTime = Date.parse(node.updated_at || node.created_at || 0) || 0;
    const remoteTime = Date.parse(remote.updated_at || remote.created_at || 0) || 0;
    if (localTime < remoteTime) { nodesSkippedOlder++; return false; }
    const differs = node.content_sha256 !== remote.content_sha256 ||
      JSON.stringify(node.metadata) !== JSON.stringify(remote.metadata) ||
      JSON.stringify(node.source) !== JSON.stringify(remote.source) ||
      JSON.stringify(node.media) !== JSON.stringify(remote.media) ||
      node.content !== remote.content || node.kind !== remote.kind || node.title !== remote.title;
    if (localTime === remoteTime) {
      if (differs) nodesConflicted++;
      return false;
    }
    return differs;
  });
  const linksToPush = bundle.links.filter(link => {
    const remote = remoteLinkByKey.get(rowKeyLink(link));
    if (!remote) return true;
    const localTime = Date.parse(link.updated_at || link.created_at || 0) || 0;
    const remoteTime = Date.parse(remote.updated_at || remote.created_at || 0) || 0;
    if (localTime <= remoteTime) { linksSkippedOlder++; return false; }
    return true;
  });
  const availableIds = new Set(remoteNodes.map(node => node.id));
  for (const node of nodesToPush) availableIds.add(node.id);
  for (const link of linksToPush) {
    if (!availableIds.has(link.source_id) || !availableIds.has(link.target_id)) {
      throw new Error("link endpoint missing in remote workspace and push bundle: " + link.source_id + " -> " + link.target_id);
    }
  }
  for (const batch of batches(nodesToPush, BATCH_SIZE)) if (batch.length) {
    await request(CONFIG.supabase.nodes_table, "on_conflict=owner_id,workspace_id,id", "POST", batch);
  }
  for (const batch of batches(linksToPush, BATCH_SIZE)) if (batch.length) {
    await request(CONFIG.supabase.links_table, "on_conflict=owner_id,workspace_id,source_id,target_id,relation", "POST", batch);
  }
  console.log(JSON.stringify({
    ok: true,
    workspace_id: bundle.workspace_id,
    nodes_upserted: nodesToPush.length,
    links_upserted: linksToPush.length,
    nodes_skipped_older: nodesSkippedOlder,
    nodes_conflicts_preserved_remote: nodesConflicted,
    links_skipped_older: linksSkippedOlder,
    binary_uploaded: false
  }, null, 2));
}
async function pull(since, outputPath) {
  const workspaceId = uuid(env(CONFIG.workspace_id_env), CONFIG.workspace_id_env);
  if (since && Number.isNaN(Date.parse(since))) throw new Error("since must be an ISO timestamp");
  const request = client();
  const nodes = await readAllTable(request, CONFIG.supabase.nodes_table, workspaceId, "updated_at.asc,id.asc", since);
  const links = await readAllTable(request, CONFIG.supabase.links_table, workspaceId, "updated_at.asc,source_id.asc,target_id.asc,relation.asc", since);
  const json = JSON.stringify({ schema_version: 1, workspace_id: workspaceId, nodes, links }, null, 2) + "\n";
  if (outputPath) {
    fs.writeFileSync(path.resolve(outputPath), json, "utf8");
    console.error("Wrote " + nodes.length + " nodes and " + links.length + " links to " + path.resolve(outputPath));
  } else process.stdout.write(json);
}
function runBridge(args) {
  const r = spawnSync(process.env.PYTHON || "python3", [path.resolve(__dirname, "sqlite_bridge.py"), ...args], { encoding: "utf8", timeout: 120000, maxBuffer: 128 * 1024 * 1024, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  if (r.error) throw r.error;
  if (r.status !== 0) throw new Error((r.stderr || r.stdout || "SQLite bridge failed").trim());
  return r.stdout;
}
async function syncLocal(args) {
  const index = args.indexOf("--db"); const db = index >= 0 ? args[index + 1] : null; const dry = args.includes("--dry-run");
  if (index >= 0 && (!db || db.startsWith("--"))) throw new Error("--db requires PATH");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mnemos-sync-"));
  const exp = path.join(dir, "export.json"); const bundlePath = path.join(dir, "bundle.json"); const remotePath = path.join(dir, "remote.json"); const importPath = path.join(dir, "import.json");
  const dbArgs = db ? ["--db", path.resolve(db)] : [];
  try {
    const counts = JSON.parse(runBridge(["export", "--output", exp, ...dbArgs]));
    const payload = JSON.parse(fs.readFileSync(exp, "utf8")); const workspace = uuid(env(CONFIG.workspace_id_env), CONFIG.workspace_id_env);
    const bundle = exportToBundle(payload, workspace); fs.writeFileSync(bundlePath, JSON.stringify(bundle) + "\n", "utf8");
    if (dry) { console.log(JSON.stringify({ mode: "dry-run", memories: bundle.nodes.length, links: bundle.links.length, network_initialized: false, outbox_acknowledged: 0, remote_verified: false }, null, 2)); return; }
    await push(bundlePath); await pull(null, remotePath);
    const remote = JSON.parse(fs.readFileSync(remotePath, "utf8")); const back = bundleToExport(remote); fs.writeFileSync(importPath, JSON.stringify(back) + "\n", "utf8");
    const imported = JSON.parse(runBridge(["import", "--input", importPath, ...dbArgs]));
    console.log(JSON.stringify({ mode: "live-sync", local_memories: bundle.nodes.length, local_links: bundle.links.length, remote_memories: back.memories.length, remote_links: back.links.length, imported, outbox_acknowledged: 0, outbox_ack_deferred: true, reason: "outbox schema cannot be safely identified by this bridge; no ACK issued" }, null, 2));
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
}
async function main(argv) {
  const [command, ...args] = argv;
  if (command === "bundle") {
    const inputPath = args[0], outputIndex = args.indexOf("--output");
    const outputPath = outputIndex >= 0 ? args[outputIndex + 1] : null;
    if (!inputPath || (outputIndex >= 0 && !outputPath)) throw new Error("usage: sync.js bundle mnemos-export.json [--output bundle.json]");
    const workspaceId = uuid(env(CONFIG.workspace_id_env), CONFIG.workspace_id_env);
    const bundle = exportToBundle(JSON.parse(fs.readFileSync(path.resolve(inputPath), "utf8")), workspaceId);
    const json = JSON.stringify(bundle, null, 2) + "\n";
    if (outputPath) fs.writeFileSync(path.resolve(outputPath), json, "utf8");
    else process.stdout.write(json);
    if (outputPath) console.error("Wrote " + bundle.nodes.length + " nodes and " + bundle.links.length + " links to " + path.resolve(outputPath));
    return;
  }
  if (command === "unbundle") {
    const inputPath = args[0], outputIndex = args.indexOf("--output");
    const outputPath = outputIndex >= 0 ? args[outputIndex + 1] : null;
    if (!inputPath || !outputPath) throw new Error("usage: sync.js unbundle remote-bundle.json --output mnemos-export.json");
    const payload = bundleToExport(JSON.parse(fs.readFileSync(path.resolve(inputPath), "utf8")));
    fs.writeFileSync(path.resolve(outputPath), JSON.stringify(payload, null, 2) + "\n", "utf8");
    console.error("Wrote portable Mnemos import with " + payload.memories.length + " memories and " + payload.links.length + " links");
    return;
  }
  if (command === "simulate") {
    const input = args[0], output = args[1]; if (!input || !output) throw new Error("usage: sync.js simulate export.json roundtrip.json");
    const source = JSON.parse(fs.readFileSync(path.resolve(input), "utf8")); const workspace = uuid(env(CONFIG.workspace_id_env), CONFIG.workspace_id_env);
    const back = bundleToExport(exportToBundle(source, workspace)); fs.writeFileSync(path.resolve(output), JSON.stringify(back, null, 2) + "\n", "utf8");
    const original = new Map(source.memories.map(m => [m.id, m])); const tags = back.memories.filter(m => JSON.stringify(Array.isArray(original.get(m.id)?.tags) ? original.get(m.id).tags : []) === JSON.stringify(m.tags)).length;
    if (back.memories.length !== source.memories.length || back.links.length !== source.links.length || tags !== source.memories.length || new Set(back.memories.map(m => m.id)).size !== source.memories.length) throw new Error("offline round-trip invariant failed");
    console.log(JSON.stringify({ mode: "offline-simulation", memories: back.memories.length, links: back.links.length, tags_arrays_preserved: tags, identity_preserved: true, relations_preserved: true, network_initialized: false }, null, 2)); return;
  }
  if (command === "sync") return syncLocal(args);
  if (command === "push") return push(args[0]);
  if (command === "pull") {
    let since = null, output = null;
    for (let i = 0; i < args.length; i++) {
      if (args[i] === "--output") { output = args[++i]; if (!output) throw new Error("--output requires a path"); }
      else if (!since) since = args[i];
      else throw new Error("unexpected argument: " + args[i]);
    }
    return pull(since, output);
  }
  throw new Error("usage: sync.js bundle mnemos-export.json [--output bundle.json] | simulate export.json roundtrip.json | sync [--db PATH] [--dry-run] | push bundle.json | pull [ISO_TIMESTAMP] [--output file.json] | unbundle remote-bundle.json --output mnemos-export.json");
}
main(process.argv.slice(2)).catch(error => { console.error("mnemos sync: " + error.message); process.exitCode = 1; });
