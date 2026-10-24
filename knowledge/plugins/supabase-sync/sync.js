#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

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
  if (Array.isArray(value)) return value.map(safeObject);
  if (!value || typeof value !== "object") return {};
  const clean = {};
  for (const [key, item] of Object.entries(value)) {
    if (/path|uri|token|secret|password|credential|base64|binary|bytes|blob/i.test(key)) continue;
    if (item && typeof item === "object") clean[key] = safeObject(item);
    else if (typeof item !== "string" || item.length <= MAX_TEXT_CHARS) clean[key] = item;
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
  const base = env(CONFIG.supabase.url_env).replace(/\/+$/, "");
  const anonKey = env(CONFIG.supabase.anon_key_env);
  const accessToken = env(CONFIG.supabase.access_token_env);
  return async function request(table, query, method = "GET", body) {
    const url = base + "/rest/v1/" + table + (query ? "?" + query : "");
    const headers = { apikey: anonKey, Authorization: "Bearer " + accessToken, Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (method === "POST" || method === "PATCH") headers.Prefer = "resolution=merge-duplicates,return=minimal";
    const response = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await response.text();
    if (!response.ok) throw new Error("Supabase " + method + " " + table + " failed (" + response.status + "): " + text.slice(0, 1200));
    if (!text) return null;
    try { return JSON.parse(text); } catch { throw new Error("Supabase returned non-JSON response for " + table); }
  };
}
function batches(items, size) {
  const out = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}
async function push(bundlePath) {
  if (!bundlePath) throw new Error("usage: sync.js push bundle.json");
  const workspaceId = uuid(env(CONFIG.workspace_id_env), CONFIG.workspace_id_env);
  const bundle = validateBundle(JSON.parse(fs.readFileSync(path.resolve(bundlePath), "utf8")), workspaceId);
  const request = client();
  for (const batch of batches(bundle.nodes, BATCH_SIZE)) if (batch.length) {
    await request(CONFIG.supabase.nodes_table, "on_conflict=owner_id,workspace_id,id", "POST", batch);
  }
  for (const batch of batches(bundle.links, BATCH_SIZE)) if (batch.length) {
    await request(CONFIG.supabase.links_table, "on_conflict=owner_id,workspace_id,source_id,target_id,relation", "POST", batch);
  }
  console.log(JSON.stringify({ ok: true, workspace_id: bundle.workspace_id, nodes_upserted: bundle.nodes.length, links_upserted: bundle.links.length, binary_uploaded: false }, null, 2));
}
async function pull(since, outputPath) {
  const workspaceId = uuid(env(CONFIG.workspace_id_env), CONFIG.workspace_id_env);
  if (since && Number.isNaN(Date.parse(since))) throw new Error("since must be an ISO timestamp");
  const request = client();
  async function getTable(table, order) {
    const params = new URLSearchParams({ select: "*", workspace_id: "eq." + workspaceId, order });
    if (since) params.set("updated_at", "gte." + new Date(Date.parse(since) - 2000).toISOString());
    const rows = await request(table, params.toString());
    if (!Array.isArray(rows)) throw new Error("expected array response from " + table);
    return rows;
  }
  const nodes = await getTable(CONFIG.supabase.nodes_table, "updated_at.asc,id.asc");
  const links = await getTable(CONFIG.supabase.links_table, "updated_at.asc,source_id.asc,target_id.asc,relation.asc");
  const json = JSON.stringify({ schema_version: 1, workspace_id: workspaceId, nodes, links }, null, 2) + "\n";
  if (outputPath) {
    fs.writeFileSync(path.resolve(outputPath), json, "utf8");
    console.error("Wrote " + nodes.length + " nodes and " + links.length + " links to " + path.resolve(outputPath));
  } else process.stdout.write(json);
}
async function main(argv) {
  const [command, ...args] = argv;
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
  throw new Error("usage: sync.js push bundle.json | sync.js pull [ISO_TIMESTAMP] [--output file.json]");
}
main(process.argv.slice(2)).catch(error => { console.error("mnemos sync: " + error.message); process.exitCode = 1; });
