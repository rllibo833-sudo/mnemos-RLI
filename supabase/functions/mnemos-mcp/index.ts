import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import postgres from "npm:postgres@3.4.5";

const DB_URL = Deno.env.get("SUPABASE_DB_URL");
if (!DB_URL) throw new Error("SUPABASE_DB_URL is not configured");
const sql = postgres(DB_URL, { max: 3, idle_timeout: 20, connect_timeout: 10 });

const corsHeaders = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, content-type, apikey, mcp-session-id",
  "access-control-allow-methods": "POST, GET, DELETE, OPTIONS",
  "content-type": "application/json; charset=utf-8",
};

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: corsHeaders });
}

function jsonRpc(id: unknown, result: unknown) {
  return { jsonrpc: "2.0", id: id ?? null, result };
}
function rpcError(id: unknown, code: number, message: string) {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}
function boundedInt(value: unknown, fallback: number, min: number, max: number): number {
  if (value === undefined) return fallback;
  if (!Number.isInteger(value) || (value as number) < min || (value as number) > max) {
    throw new Error(`value must be an integer from ${min} to ${max}`);
  }
  return value as number;
}
function parseArgs(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("arguments must be an object");
  return value as Record<string, unknown>;
}
function uuid() { return crypto.randomUUID(); }
function now() { return new Date().toISOString(); }

// Additive graph-sync storage; the existing memories/links tables are untouched.
const graphSchemaReady = (async () => {
  await sql`create schema if not exists mnemos`;
  await sql`create table if not exists mnemos.workspaces (
    id text primary key, visibility text not null default 'private'
      check (visibility in ('private','shared','public')),
    created_at timestamptz not null default now()
  )`;
  await sql`create table if not exists mnemos.memberships (
    workspace_id text not null references mnemos.workspaces(id),
    user_id text not null, role text not null check (role in ('reader','writer','admin')),
    primary key(workspace_id,user_id)
  )`;
  await sql`create table if not exists mnemos.sync_changes (
    id text primary key, workspace_id text not null references mnemos.workspaces(id),
    entity_type text not null check(entity_type in ('memory','link','node','relation')),
    entity_id text not null, op text not null check(op in ('upsert','delete')),
    payload_json jsonb not null, lamport_clock bigint not null check(lamport_clock >= 0),
    actor text not null, timestamp timestamptz not null, owner_id text not null
  )`;
  await sql`create index if not exists sync_changes_workspace_clock
    on mnemos.sync_changes(workspace_id,lamport_clock,timestamp)`;
})();

type GraphChange = {
  id: string; workspace_id: string; entity_type: "memory"|"link"|"node"|"relation";
  entity_id: string; op: "upsert"|"delete"; payload: Record<string, unknown>;
  lamport_clock: number; actor: string; timestamp: string|number;
};
async function requireWorkspaceRole(workspaceId: string, userId: string, write: boolean) {
  await graphSchemaReady;
  let workspaces = await sql`select id,visibility from mnemos.workspaces where id=${workspaceId}`;
  if (!workspaces.length && workspaceId === "default") {
    await sql`insert into mnemos.workspaces(id,visibility) values ('default','private') on conflict do nothing`;
    await sql`insert into mnemos.memberships(workspace_id,user_id,role) values ('default',${userId},'admin') on conflict do nothing`;
    workspaces = await sql`select id,visibility from mnemos.workspaces where id=${workspaceId}`;
  }
  if (!workspaces.length) throw new Error("workspace not found");
  const memberships = await sql`select role from mnemos.memberships where workspace_id=${workspaceId} and user_id=${userId}`;
  const role = memberships[0]?.role as string|undefined;
  if (write && role !== "writer" && role !== "admin") throw new Error("workspace writer/admin membership required");
  if (!write && workspaces[0].visibility !== "public" && !role) throw new Error("workspace membership required");
  if (!write && workspaces[0].visibility === "private" && !role) throw new Error("private workspace is not accessible");
  return {visibility: workspaces[0].visibility as string, role};
}
function stableJson(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(stableJson).join(",") + "]";
  if (value && typeof value === "object") {
    const object=value as Record<string,unknown>;
    return "{" + Object.keys(object).sort().map(k => JSON.stringify(k)+":"+stableJson(object[k])).join(",") + "}";
  }
  return JSON.stringify(value) ?? "null";
}
function parseGraphChange(value: unknown): GraphChange {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("change must be an object");
  const c=value as Record<string,unknown>;
  if (typeof c.id!=="string" || !c.id || typeof c.workspace_id!=="string" || !c.workspace_id ||
      !["memory","link","node","relation"].includes(String(c.entity_type)) ||
      typeof c.entity_id!=="string" || !c.entity_id || !["upsert","delete"].includes(String(c.op)) ||
      !Number.isSafeInteger(c.lamport_clock) || (c.lamport_clock as number)<0 ||
      typeof c.actor!=="string" || !c.actor ||
      !(typeof c.timestamp==="string" || typeof c.timestamp==="number") ||
      !c.payload || typeof c.payload!=="object" || Array.isArray(c.payload)) {
    throw new Error("invalid Change contract");
  }
  return c as unknown as GraphChange;
}
async function pushChanges(raw: unknown, userId: string) {
  if (!Array.isArray(raw) || raw.length>1000) throw new Error("changes must be an array of at most 1000 changes");
  const result={accepted:0,duplicates:0};
  for (const rawChange of raw) {
    const c=parseGraphChange(rawChange);
    const {role}=await requireWorkspaceRole(c.workspace_id,userId,true);
    if (role!=="writer" && role!=="admin") throw new Error("workspace writer/admin membership required");
    const timestamp=typeof c.timestamp==="number" ? new Date(c.timestamp*1000).toISOString() : c.timestamp;
    const old=await sql`select workspace_id,entity_type,entity_id,op,payload_json,lamport_clock,actor
      from mnemos.sync_changes where id=${c.id}`;
    if (old.length) {
      const same=old[0].workspace_id===c.workspace_id && old[0].entity_type===c.entity_type &&
        old[0].entity_id===c.entity_id && old[0].op===c.op &&
        Number(old[0].lamport_clock)===c.lamport_clock &&
        stableJson(old[0].payload_json)===stableJson(c.payload);
      if (!same) throw new Error("change id already exists with different content");
      result.duplicates++; continue;
    }
    await sql`insert into mnemos.sync_changes
      (id,workspace_id,entity_type,entity_id,op,payload_json,lamport_clock,actor,timestamp,owner_id)
      values (${c.id},${c.workspace_id},${c.entity_type},${c.entity_id},${c.op},
        ${sql.json(c.payload)},${c.lamport_clock},${c.actor},${timestamp}::timestamptz,${userId})`;
    result.accepted++;
  }
  return result;
}
async function pullChanges(workspaceId: string, sinceLamport: number, sinceId: string, userId: string) {
  await requireWorkspaceRole(workspaceId,userId,false);
  const rows=await sql`select id,workspace_id,entity_type,entity_id,op,payload_json as payload,
      lamport_clock,actor,timestamp from mnemos.sync_changes
      where workspace_id=${workspaceId}
        and (lamport_clock,id) > (${sinceLamport},${sinceId})
      order by lamport_clock,id limit 5000`;
  return rows.map((r: Record<string,unknown>)=>({...r,lamport_clock:Number(r.lamport_clock),
    timestamp:r.timestamp instanceof Date ? r.timestamp.toISOString() : new Date(String(r.timestamp)).toISOString()}));
}

const tools = [
  { name: "mnemos_search", description: "Search cloud Mnemos memories using lexical matching.", inputSchema: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 1000, default: 20 } }, required: ["query"], additionalProperties: false } },
  { name: "mnemos_add", description: "Store a concise durable memory in cloud Mnemos. Never store secrets.", inputSchema: { type: "object", properties: { content: { type: "string" }, kind: { type: "string", default: "note" }, tags: { type: "array", items: { type: "string" }, default: [] }, source: { type: ["string", "null"], default: null }, metadata: { type: "object", default: {} } }, required: ["content"], additionalProperties: false } },
  { name: "mnemos_get", description: "Retrieve one memory by exact UUID.", inputSchema: { type: "object", properties: { memory_id: { type: "string" } }, required: ["memory_id"], additionalProperties: false } },
  { name: "mnemos_list", description: "List recent cloud Mnemos memories.", inputSchema: { type: "object", properties: { limit: { type: "integer", minimum: 1, maximum: 10000, default: 50 } }, additionalProperties: false } },
  { name: "mnemos_link", description: "Create an explicit directed relationship between two existing memory IDs.", inputSchema: { type: "object", properties: { source_id: { type: "string" }, target_id: { type: "string" }, relation: { type: "string", default: "relates_to" } }, required: ["source_id", "target_id"], additionalProperties: false } },
  { name: "mnemos_export", description: "Return a portable JSON snapshot of all cloud memories and links.", inputSchema: { type: "object", properties: {}, additionalProperties: false } },
  { name: "mnemos_push", description: "Push idempotent graph Change records into an authorized workspace.", inputSchema: { type: "object", properties: { changes: { type: "array", items: { type: "object" } } }, required: ["changes"], additionalProperties: false } },
  { name: "mnemos_pull", description: "Pull workspace changes after a Lamport clock and change ID cursor.", inputSchema: { type: "object", properties: { workspace_id: { type: "string" }, since_lamport: { type: "integer", minimum: 0, default: 0 }, since_id: { type: "string", default: "" } }, required: ["workspace_id"], additionalProperties: false } },
];

async function callTool(name: string, rawArgs: unknown, ownerId: string) {
  const a = parseArgs(rawArgs);
  if (name === "mnemos_push") return await pushChanges(a.changes, ownerId);
  if (name === "mnemos_pull") {
    if (typeof a.workspace_id !== "string" || !a.workspace_id) throw new Error("workspace_id is required");
    const since=boundedInt(a.since_lamport,0,0,Number.MAX_SAFE_INTEGER);
    const sinceId = a.since_id === undefined ? "" : a.since_id;
    if (typeof sinceId !== "string") throw new Error("since_id must be a string");
    return await pullChanges(a.workspace_id,since,sinceId,ownerId);
  }
  if (name === "mnemos_add") {
    if (typeof a.content !== "string" || !a.content.trim()) throw new Error("content must be a non-empty string");
    const kind = a.kind === undefined ? "note" : a.kind;
    const tags = a.tags === undefined ? [] : a.tags;
    const source = a.source === undefined ? null : a.source;
    const metadata = a.metadata === undefined ? {} : a.metadata;
    if (typeof kind !== "string" || !Array.isArray(tags) || !tags.every(x => typeof x === "string") || (source !== null && typeof source !== "string") || !metadata || typeof metadata !== "object" || Array.isArray(metadata)) throw new Error("invalid memory fields");
    const timestamp = now();
    const id = uuid();
    const rows = await sql`insert into mnemos.memories (id, owner_id, content, kind, tags, source, metadata, created_at, updated_at)
      values (${id}::uuid, ${ownerId}::uuid, ${a.content.trim()}, ${kind.trim() || "note"}, ${[...new Set((tags as string[]).map(x => x.trim()).filter(Boolean))]}, ${source}, ${sql.json(metadata)}, ${timestamp}::timestamptz, ${timestamp}::timestamptz)
      returning id, content, kind, tags, source, metadata, created_at, updated_at`;
    return rows[0];
  }
  if (name === "mnemos_get") {
    if (typeof a.memory_id !== "string") throw new Error("memory_id must be a UUID string");
    const rows = await sql`select id, content, kind, tags, source, metadata, created_at, updated_at from mnemos.memories where id = ${a.memory_id}::uuid and owner_id = ${ownerId}::uuid`;
    return rows[0] ?? null;
  }
  if (name === "mnemos_list") {
    const limit = boundedInt(a.limit, 50, 1, 10000);
    return await sql`select id, content, kind, tags, source, metadata, created_at, updated_at from mnemos.memories where owner_id = ${ownerId}::uuid order by created_at desc limit ${limit}`;
  }
  if (name === "mnemos_search") {
    if (typeof a.query !== "string") throw new Error("query must be a string");
    const limit = boundedInt(a.limit, 20, 1, 1000);
    const terms = a.query.toLocaleLowerCase().split(/\s+/).filter(Boolean).slice(0, 32);
    if (!terms.length) return [];
    const rows = await sql`select id, content, kind, tags, source, metadata, created_at, updated_at from mnemos.memories where owner_id = ${ownerId}::uuid order by created_at desc limit 10000`;
    const scored = rows.map((row: Record<string, unknown>) => {
      const haystack = [row.content, row.kind, ...(Array.isArray(row.tags) ? row.tags : []), row.source ?? ""].join(" ").toLocaleLowerCase();
      const score = terms.reduce((n, term) => n + Math.max(0, haystack.split(term).length - 1), 0);
      return { row, score };
    }).filter((item: { score: number }) => item.score > 0).sort((a: { score: number }, b: { score: number }) => b.score - a.score);
    return scored.slice(0, limit).map((item: { row: unknown }) => item.row);
  }
  if (name === "mnemos_link") {
    if (typeof a.source_id !== "string" || typeof a.target_id !== "string") throw new Error("source_id and target_id must be UUID strings");
    const relation = a.relation === undefined ? "relates_to" : a.relation;
    if (typeof relation !== "string" || !relation.trim()) throw new Error("relation must be a non-empty string");
    const owned = await sql`select id from mnemos.memories where owner_id = ${ownerId}::uuid and id in (${a.source_id}::uuid, ${a.target_id}::uuid)`;
    if (owned.length !== 2) throw new Error("both memories must exist and belong to the authenticated user");
    const rows = await sql`insert into mnemos.links (id, owner_id, source_id, target_id, relation, created_at)
      values (${uuid()}::uuid, ${ownerId}::uuid, ${a.source_id}::uuid, ${a.target_id}::uuid, ${relation.trim()}, ${now()}::timestamptz)
      on conflict (source_id, target_id, relation) do update set relation = excluded.relation
      returning id, source_id, target_id, relation, created_at`;
    return rows[0];
  }
  if (name === "mnemos_export") {
    const memories = await sql`select id, content, kind, tags, source, metadata, created_at, updated_at from mnemos.memories where owner_id = ${ownerId}::uuid order by created_at`;
    const links = await sql`select id, source_id, target_id, relation, created_at from mnemos.links where owner_id = ${ownerId}::uuid order by created_at`;
    return { format: "mnemos-export-v1", exported_at: now(), memories, links };
  }
  throw new Error(`unknown tool: ${name}`);
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders });
  if (req.method === "GET") return response({ name: "mnemos-cloud-mcp", status: "ready", transport: "streamable-http", authentication: "Supabase authenticated user JWT required" });
  if (req.method !== "POST") return response({ error: "method not allowed" }, 405);

  // Supabase gateway verifies the JWT signature when verify_jwt=true. Restrict the
  // endpoint to real signed-in users; the public anon key alone is not sufficient.
  const authorization = req.headers.get("authorization") ?? "";
  const token = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  const parts = token.split(".");
  if (parts.length !== 3) return response({ error: "authenticated Supabase user session required" }, 401);
  let claims: Record<string, unknown>;
  try { claims = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"))); }
  catch { return response({ error: "invalid access token" }, 401); }
  if (claims.role !== "authenticated" || typeof claims.sub !== "string") return response({ error: "signed-in user token required; anon key is not enough" }, 403);

  let body: Record<string, unknown>;
  try {
    const raw = await req.text();
    if (raw.length > 1_000_000) return response({ error: "request body too large" }, 413);
    body = JSON.parse(raw);
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("JSON-RPC body must be an object");
  } catch (e) { return response(rpcError(null, -32700, e instanceof Error ? e.message : "invalid JSON"), 400); }

  const id = body.id;
  const method = body.method;
  if (body.jsonrpc !== "2.0" || typeof method !== "string") return response(rpcError(id, -32600, "invalid JSON-RPC request"), 400);
  if (method === "notifications/initialized" || method === "notifications/cancelled") return new Response(null, { status: 202, headers: corsHeaders });
  if (method === "initialize") return response(jsonRpc(id, { protocolVersion: "2025-03-26", capabilities: { tools: {} }, serverInfo: { name: "mnemos-cloud", version: "0.3.0" } }));
  if (method === "ping") return response(jsonRpc(id, {}));
  if (method === "tools/list") return response(jsonRpc(id, { tools }));
  if (method === "tools/call") {
    let params: Record<string, unknown>;
    try { params = parseArgs(body.params); }
    catch (e) { return response(rpcError(id, -32602, e instanceof Error ? e.message : "invalid tool params"), 400); }
    if (typeof params.name !== "string") return response(rpcError(id, -32602, "tool name is required"), 400);
    try {
      const result = await callTool(params.name, params.arguments ?? {}, claims.sub as string);
      return response(jsonRpc(id, { content: [{ type: "text", text: JSON.stringify(result) }], structuredContent: result, isError: false }));
    } catch (e) {
      const message = e instanceof Error ? e.message : "tool execution failed";
      return response(jsonRpc(id, { content: [{ type: "text", text: message }], isError: true }));
    }
  }
  if (method === "resources/list") return response(jsonRpc(id, { resources: [] }));
  return response(rpcError(id, -32601, "method not found"), 400);
});
