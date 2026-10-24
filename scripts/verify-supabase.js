#!/usr/bin/env node
"use strict";
const crypto = require("node:crypto");
const mode = process.argv[2] || "dry-run";
const base = process.env.SUPABASE_URL; const key = process.env.SUPABASE_ANON_KEY; const token = process.env.SUPABASE_ACCESS_TOKEN; const workspace = process.env.WORKSPACE_ID;
if (!["dry-run", "read-check", "rls-check"].includes(mode)) { console.error("usage: node scripts/verify-supabase.js dry-run|read-check|rls-check"); process.exit(2); }
if (mode === "dry-run") { console.log(JSON.stringify({ mode, network: false, verified: false, reason: "configuration only" }, null, 2)); process.exit(0); }
if (!base || !key || !workspace || (mode === "rls-check" && !token)) { console.error("SUPABASE_URL, SUPABASE_ANON_KEY, WORKSPACE_ID, and (for rls-check) SUPABASE_ACCESS_TOKEN are required"); process.exit(2); }
let root = base; while (root.endsWith("/")) root = root.slice(0, -1); root += "/rest/v1/memories";
const headers = { apikey: key, Authorization: "Bearer " + (mode === "rls-check" ? token : (token || key)), Accept: "application/json" };
async function request(url, options = {}) { return fetch(url, { ...options, headers: { ...headers, ...(options.headers || {}) }, signal: AbortSignal.timeout(10000) }); }
(async () => {
 const query = "?select=id&workspace_id=eq." + encodeURIComponent(workspace) + "&limit=1";
 const read = await request(root + query); if (!read.ok) throw new Error("read-check HTTP " + read.status + ": " + (await read.text()).slice(0, 250));
 if (mode === "read-check") { console.log(JSON.stringify({ mode, network: true, readable: true, rows_seen: (await read.json()).length, rls_verified: false }, null, 2)); return; }
 const id = "mnemos-rls-probe-" + crypto.randomUUID(); const content = "temporary RLS verification record";
 const row = { id, workspace_id: workspace, kind: "verification", content, tags: [], source: {type:"verification"}, metadata: {temporary:true}, content_sha256: crypto.createHash("sha256").update(content).digest("hex"), schema_version: 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
 let inserted = false; let deleted = false;
 try { const write = await request(root, { method: "POST", headers: {"Content-Type":"application/json", Prefer:"return=minimal"}, body: JSON.stringify(row) }); if (!write.ok) throw new Error("authenticated insert HTTP " + write.status + ": " + (await write.text()).slice(0,250)); inserted = true; }
 finally { if (inserted) { const cleanup = await request(root + "?id=eq." + encodeURIComponent(id) + "&workspace_id=eq." + encodeURIComponent(workspace), {method:"DELETE",headers:{Prefer:"return=minimal"}}); deleted = cleanup.ok; if (!deleted) throw new Error("probe cleanup failed; manually remove id " + id); } }
 console.log(JSON.stringify({mode,network:true,authenticated_insert:inserted,authenticated_delete:deleted,cross_account_isolation_proven:false},null,2));
})().catch(error => { console.error("verify-supabase: " + error.message); process.exitCode = 1; });
