# Mnemos Cloud

## Current deployment

- Supabase project: `kuditcnmasfjgzmimnlc` (region `ap-southeast-2`).
- Remote MCP endpoint: `https://kuditcnmasfjgzmimnlc.supabase.co/functions/v1/mnemos-mcp`
- Transport: HTTP JSON-RPC MCP subset (`initialize`, `tools/list`, `tools/call`, `ping`).
- Tool names match the local adapter: `mnemos_search`, `mnemos_add`, `mnemos_get`, `mnemos_list`, `mnemos_link`, `mnemos_export`.
- Storage: private PostgreSQL schema `mnemos` with RLS enabled and direct public grants revoked.
- Authentication: Supabase gateway JWT validation is enabled, and the handler additionally requires a signed-in user's JWT with `role=authenticated`. The public anon key alone is intentionally rejected.

## Security notes

The function uses the server-side `SUPABASE_DB_URL` environment variable and does not embed database credentials in source control. Do not publish a service-role/secret key, database password, or user access token in a repository or chat. The function currently uses a single shared memory space for authenticated users of this project; per-user data isolation is not implemented yet, so only connect trusted users until ownership scoping is added.

## Connection request shape

A compatible MCP HTTP client sends JSON-RPC POST requests to the endpoint with:
- `Authorization: Bearer <Supabase user access token>`
- `apikey: <project publishable key>`
- `Content-Type: application/json`

The access token must belong to a signed-in Supabase Auth user; an anon/publishable key is not a user session. Hosts that cannot supply a custom bearer token may not be able to connect directly yet.

Example MCP initialization body:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"mnemos-client","version":"1.0.0"}}}
```

Example tool discovery body:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
```

## Verification boundary

The deployed function is active and its source is checked into `supabase/functions/mnemos-mcp/index.ts`. A full end-to-end call using a real authenticated user session is still needed. Do not treat deployment status alone as proof of a successful database round trip. This service currently starts with an empty cloud database; local SQLite memories have not been imported.
