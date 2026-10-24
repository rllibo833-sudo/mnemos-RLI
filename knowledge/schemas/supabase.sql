-- Apply explicitly in the target Supabase project before enabling remote sync.
-- Uses the signed-in user's JWT and RLS. Never use a service-role key in an agent.
create table if not exists public.knowledge_nodes (
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  workspace_id uuid not null,
  id text not null check (char_length(id) between 1 and 256),
  kind text not null check (char_length(kind) between 1 and 80),
  title text not null default '' check (char_length(title) <= 512),
  content text not null default '' check (char_length(content) <= 65536),
  source jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  media jsonb not null default '{}'::jsonb,
  content_sha256 text not null check (content_sha256 ~ '^[a-fA-F0-9]{64}$'),
  schema_version integer not null default 1 check (schema_version = 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz null,
  primary key (owner_id, workspace_id, id)
);

create table if not exists public.knowledge_links (
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  workspace_id uuid not null,
  source_id text not null,
  target_id text not null,
  relation text not null check (char_length(relation) between 1 and 64),
  provenance jsonb not null default '{}'::jsonb,
  confidence double precision null check (confidence is null or (confidence >= 0 and confidence <= 1)),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz null,
  primary key (owner_id, workspace_id, source_id, target_id, relation),
  foreign key (owner_id, workspace_id, source_id)
    references public.knowledge_nodes(owner_id, workspace_id, id) on delete cascade,
  foreign key (owner_id, workspace_id, target_id)
    references public.knowledge_nodes(owner_id, workspace_id, id) on delete cascade
);

create index if not exists knowledge_nodes_workspace_updated
  on public.knowledge_nodes(workspace_id, updated_at, id);
create index if not exists knowledge_links_workspace_updated
  on public.knowledge_links(workspace_id, updated_at, source_id, target_id);

alter table public.knowledge_nodes enable row level security;
alter table public.knowledge_links enable row level security;

drop policy if exists knowledge_nodes_owner_select on public.knowledge_nodes;
create policy knowledge_nodes_owner_select on public.knowledge_nodes for select to authenticated using (owner_id = auth.uid());
drop policy if exists knowledge_nodes_owner_insert on public.knowledge_nodes;
create policy knowledge_nodes_owner_insert on public.knowledge_nodes for insert to authenticated with check (owner_id = auth.uid());
drop policy if exists knowledge_nodes_owner_update on public.knowledge_nodes;
create policy knowledge_nodes_owner_update on public.knowledge_nodes for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists knowledge_nodes_owner_delete on public.knowledge_nodes;
create policy knowledge_nodes_owner_delete on public.knowledge_nodes for delete to authenticated using (owner_id = auth.uid());

drop policy if exists knowledge_links_owner_select on public.knowledge_links;
create policy knowledge_links_owner_select on public.knowledge_links for select to authenticated using (owner_id = auth.uid());
drop policy if exists knowledge_links_owner_insert on public.knowledge_links;
create policy knowledge_links_owner_insert on public.knowledge_links for insert to authenticated with check (owner_id = auth.uid());
drop policy if exists knowledge_links_owner_update on public.knowledge_links;
create policy knowledge_links_owner_update on public.knowledge_links for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists knowledge_links_owner_delete on public.knowledge_links;
create policy knowledge_links_owner_delete on public.knowledge_links for delete to authenticated using (owner_id = auth.uid());

grant select, insert, update, delete on public.knowledge_nodes to authenticated;
grant select, insert, update, delete on public.knowledge_links to authenticated;

-- Keep incremental pulls correct when an existing record is upserted.
create or replace function public.set_knowledge_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists knowledge_nodes_updated_at on public.knowledge_nodes;
create trigger knowledge_nodes_updated_at
  before update on public.knowledge_nodes
  for each row execute function public.set_knowledge_updated_at();

drop trigger if exists knowledge_links_updated_at on public.knowledge_links;
create trigger knowledge_links_updated_at
  before update on public.knowledge_links
  for each row execute function public.set_knowledge_updated_at();
