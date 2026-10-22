-- Mnemos cloud storage foundation.
-- Private schema: no direct Data API access for anon/authenticated roles.
create schema if not exists mnemos;

create table if not exists mnemos.memories (
  id uuid primary key,
  content text not null check (length(btrim(content)) > 0),
  kind text not null default 'note',
  tags text[] not null default '{}',
  source text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table if not exists mnemos.links (
  id uuid primary key,
  source_id uuid not null references mnemos.memories(id) on delete cascade,
  target_id uuid not null references mnemos.memories(id) on delete cascade,
  relation text not null default 'relates_to',
  created_at timestamptz not null,
  constraint mnemos_links_unique unique (source_id, target_id, relation),
  constraint mnemos_links_no_self check (source_id <> target_id)
);

create index if not exists mnemos_memories_kind_idx on mnemos.memories(kind);
create index if not exists mnemos_links_source_idx on mnemos.links(source_id);
create index if not exists mnemos_links_target_idx on mnemos.links(target_id);

alter table mnemos.memories enable row level security;
alter table mnemos.links enable row level security;
revoke all on schema mnemos from public, anon, authenticated;
revoke all on all tables in schema mnemos from public, anon, authenticated;
