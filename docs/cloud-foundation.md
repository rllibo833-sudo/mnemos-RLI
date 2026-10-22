# Mnemos Cloud Foundation

## Status

The dedicated Supabase project is provisioned separately from any other project. The initial private database schema stores Mnemos memories and explicit links. It is intentionally not exposed through the public Supabase Data API.

## Storage model

- `mnemos.memories`: stable UUID, content, kind, tags, source, JSON metadata, and timestamps.
- `mnemos.links`: stable UUID, source/target memory IDs, relation, and creation timestamp.
- Foreign keys cascade link deletion when a memory is removed.
- Duplicate links and self-links are rejected.
- Row-level security is enabled; direct grants to `anon`, `authenticated`, and `public` are revoked.

## Remote MCP status

The current production MCP adapter is a local stdio server backed by SQLite. The cloud schema alone does not make it a remote MCP service. A remote adapter still needs to be implemented and deployed, with explicit authentication, bounded request parsing, and tests for all existing tools. Do not expose the Supabase service-role key or accept unauthenticated memory operations.

## Deployment plan

1. Apply the SQL migration to the dedicated Mnemos Supabase project.
2. Implement a remote MCP transport using the existing Mnemos tool contract.
3. Configure a server-side secret through the hosting provider's secret manager; never commit it to the repository.
4. Test search/add/get/list/link/export against the hosted database and verify unauthenticated requests are rejected.
5. Document the simplest compatible AI host setup and backup/restore procedure.

## Important

Creating a Supabase project and schema does not mean the AI host is connected. Cross-provider MCP support depends on the host and its plan. The database currently starts empty; local SQLite data has not been uploaded.
