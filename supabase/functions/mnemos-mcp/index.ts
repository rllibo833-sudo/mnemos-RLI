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

const tools = [
  { name: "mnemos_search", description: "Search cloud Mnemos memories using lexical matching.", inputSchema: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 1000, default: 20 } }, required: ["query"], additionalProperties: false } },
  { name: "mnemos_add", description: "Store a concise durable memory in cloud Mnemos. Never store secrets.", inputSchema: { type: "object", properties: { content: { type: "string" }, kind: { type: "string", default: "note" }, tags: { type: "array", items: { type: "string" }, default: [] }, source: { type: ["string", "null"], default: null }, metadata: { type: "object", default: {} } }, required: ["content"], additionalProperties: false } },
  { name: "mnemos_get", description: "Retrieve one memory by exact UUID.", inputSchema: { type: "object", properties: { memory_id: { type: "string" } }, required: ["memory_id"], additionalProperties: false } },
  { name: "mnemos_list", description: "List recent cloud Mnemos memories.", inputSchema: { type: "object", properties: { limit: { type: "integer", minimum: 1, maximum: 10000, default: 50 } }, additionalProperties: false } },
  { name: "mnemos_link", description: "Create an explicit directed relationship between two existing memory IDs.", inputSchema: { type: "object", properties: { source_id: { type: "string" }, target_id: { type: "string" }, relation: { type: "string", default: "relates_to" } }, required: ["source_id", "target_id"], additionalProperties: false } },
  { name: "mnemos_export", description: "Return a portable JSON snapshot of all cloud memories and links.", inputSchema: { type: "object", properties: {}, additionalProperties: false } },
];

async function callTool(name: string, rawArgs: unknown, ownerId: string) {
  const a = parseArgs(rawArgs);
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
