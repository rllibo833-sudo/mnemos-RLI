-- Canonical shared Knowledge Graph schema. Apply to Supabase before live sync.
create table if not exists public.knowledge_workspaces (
 id uuid primary key default gen_random_uuid(), name text not null default 'Shared Knowledge' check(char_length(name) between 1 and 160),
 owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade, created_at timestamptz not null default now()
);
create table if not exists public.knowledge_workspace_members (
 workspace_id uuid not null references public.knowledge_workspaces(id) on delete cascade,
 user_id uuid not null references auth.users(id) on delete cascade, role text not null check(role in ('reader','writer','admin')),
 created_at timestamptz not null default now(), primary key(workspace_id,user_id)
);
create table if not exists public.knowledge_nodes (
 owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 workspace_id uuid not null, id text not null check(char_length(id) between 1 and 256), kind text not null check(char_length(kind) between 1 and 80),
 title text not null default '' check(char_length(title)<=512), content text not null default '' check(char_length(content)<=65536),
 source jsonb not null default '{}'::jsonb, metadata jsonb not null default '{}'::jsonb, media jsonb not null default '{}'::jsonb,
 content_sha256 text not null check(content_sha256 ~ '^[a-fA-F0-9]{64}$'), schema_version integer not null default 1 check(schema_version=1),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz null,
 constraint knowledge_nodes_pkey primary key(workspace_id,id),
 constraint knowledge_nodes_workspace_fk foreign key(workspace_id) references public.knowledge_workspaces(id) on delete cascade
);
create table if not exists public.knowledge_links (
 owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 workspace_id uuid not null, source_id text not null, target_id text not null, relation text not null check(char_length(relation) between 1 and 64),
 provenance jsonb not null default '{}'::jsonb, confidence double precision null check(confidence is null or (confidence>=0 and confidence<=1)),
 metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(), deleted_at timestamptz null,
 constraint knowledge_links_pkey primary key(workspace_id,source_id,target_id,relation),
 constraint knowledge_links_workspace_fk foreign key(workspace_id) references public.knowledge_workspaces(id) on delete cascade,
 constraint knowledge_links_source_fk foreign key(workspace_id,source_id) references public.knowledge_nodes(workspace_id,id) on delete cascade,
 constraint knowledge_links_target_fk foreign key(workspace_id,target_id) references public.knowledge_nodes(workspace_id,id) on delete cascade,
 check(source_id<>target_id)
);
create index if not exists knowledge_nodes_workspace_updated on public.knowledge_nodes(workspace_id,updated_at,id);
create index if not exists knowledge_links_workspace_updated on public.knowledge_links(workspace_id,updated_at,source_id,target_id);
create or replace function public.mnemos_workspace_role(p_workspace_id uuid)
returns text language sql stable security definer set search_path=public
as $$ select case when w.owner_id=auth.uid() then 'admin' else m.role end from public.knowledge_workspaces w left join public.knowledge_workspace_members m on m.workspace_id=w.id and m.user_id=auth.uid() where w.id=p_workspace_id $$;
create or replace function public.mnemos_workspace_admin(p_workspace_id uuid)
returns boolean language sql stable security definer set search_path=public
as $$ select coalesce(public.mnemos_workspace_role(p_workspace_id)='admin',false) $$;
revoke all on function public.mnemos_workspace_role(uuid) from public;
revoke all on function public.mnemos_workspace_admin(uuid) from public;
grant execute on function public.mnemos_workspace_role(uuid) to authenticated;
grant execute on function public.mnemos_workspace_admin(uuid) to authenticated;
create or replace function public.mnemos_add_workspace_owner()
returns trigger language plpgsql security definer set search_path=public
as $$ begin insert into public.knowledge_workspace_members(workspace_id,user_id,role) values(new.id,new.owner_id,'admin') on conflict(workspace_id,user_id) do nothing; return new; end $$;
drop trigger if exists knowledge_workspace_owner_membership on public.knowledge_workspaces;
create trigger knowledge_workspace_owner_membership after insert on public.knowledge_workspaces for each row execute function public.mnemos_add_workspace_owner();
create or replace function public.set_knowledge_updated_at()
returns trigger language plpgsql set search_path=public
as $$ begin new.updated_at=now(); return new; end $$;
drop trigger if exists knowledge_nodes_updated_at on public.knowledge_nodes;
create trigger knowledge_nodes_updated_at before update on public.knowledge_nodes for each row execute function public.set_knowledge_updated_at();
drop trigger if exists knowledge_links_updated_at on public.knowledge_links;
create trigger knowledge_links_updated_at before update on public.knowledge_links for each row execute function public.set_knowledge_updated_at();
alter table public.knowledge_workspaces enable row level security;
alter table public.knowledge_workspace_members enable row level security;
alter table public.knowledge_nodes enable row level security;
alter table public.knowledge_links enable row level security;
drop policy if exists knowledge_workspaces_member_select on public.knowledge_workspaces;
create policy knowledge_workspaces_member_select on public.knowledge_workspaces for select to authenticated using(public.mnemos_workspace_role(id) is not null);
drop policy if exists knowledge_workspaces_owner_insert on public.knowledge_workspaces;
create policy knowledge_workspaces_owner_insert on public.knowledge_workspaces for insert to authenticated with check(owner_id=auth.uid());
drop policy if exists knowledge_workspaces_admin_update on public.knowledge_workspaces;
create policy knowledge_workspaces_admin_update on public.knowledge_workspaces for update to authenticated using(public.mnemos_workspace_admin(id)) with check(public.mnemos_workspace_admin(id));
drop policy if exists knowledge_workspaces_admin_delete on public.knowledge_workspaces;
create policy knowledge_workspaces_admin_delete on public.knowledge_workspaces for delete to authenticated using(public.mnemos_workspace_admin(id));
drop policy if exists knowledge_workspace_members_select on public.knowledge_workspace_members;
create policy knowledge_workspace_members_select on public.knowledge_workspace_members for select to authenticated using(user_id=auth.uid() or public.mnemos_workspace_admin(workspace_id));
drop policy if exists knowledge_workspace_members_admin_insert on public.knowledge_workspace_members;
create policy knowledge_workspace_members_admin_insert on public.knowledge_workspace_members for insert to authenticated with check(public.mnemos_workspace_admin(workspace_id));
drop policy if exists knowledge_workspace_members_admin_update on public.knowledge_workspace_members;
create policy knowledge_workspace_members_admin_update on public.knowledge_workspace_members for update to authenticated using(public.mnemos_workspace_admin(workspace_id)) with check(public.mnemos_workspace_admin(workspace_id));
drop policy if exists knowledge_workspace_members_admin_delete on public.knowledge_workspace_members;
create policy knowledge_workspace_members_admin_delete on public.knowledge_workspace_members for delete to authenticated using(public.mnemos_workspace_admin(workspace_id));
drop policy if exists knowledge_nodes_owner_select on public.knowledge_nodes;
drop policy if exists knowledge_nodes_owner_insert on public.knowledge_nodes;
drop policy if exists knowledge_nodes_owner_update on public.knowledge_nodes;
drop policy if exists knowledge_nodes_owner_delete on public.knowledge_nodes;
drop policy if exists knowledge_nodes_member_select on public.knowledge_nodes;
create policy knowledge_nodes_member_select on public.knowledge_nodes for select to authenticated using(public.mnemos_workspace_role(workspace_id) in ('reader','writer','admin'));
drop policy if exists knowledge_nodes_member_insert on public.knowledge_nodes;
create policy knowledge_nodes_member_insert on public.knowledge_nodes for insert to authenticated with check(public.mnemos_workspace_role(workspace_id) in ('writer','admin'));
drop policy if exists knowledge_nodes_member_update on public.knowledge_nodes;
create policy knowledge_nodes_member_update on public.knowledge_nodes for update to authenticated using(public.mnemos_workspace_role(workspace_id) in ('writer','admin')) with check(public.mnemos_workspace_role(workspace_id) in ('writer','admin'));
drop policy if exists knowledge_nodes_member_delete on public.knowledge_nodes;
create policy knowledge_nodes_member_delete on public.knowledge_nodes for delete to authenticated using(public.mnemos_workspace_role(workspace_id) in ('writer','admin'));
drop policy if exists knowledge_links_owner_select on public.knowledge_links;
drop policy if exists knowledge_links_owner_insert on public.knowledge_links;
drop policy if exists knowledge_links_owner_update on public.knowledge_links;
drop policy if exists knowledge_links_owner_delete on public.knowledge_links;
drop policy if exists knowledge_links_member_select on public.knowledge_links;
create policy knowledge_links_member_select on public.knowledge_links for select to authenticated using(public.mnemos_workspace_role(workspace_id) in ('reader','writer','admin'));
drop policy if exists knowledge_links_member_insert on public.knowledge_links;
create policy knowledge_links_member_insert on public.knowledge_links for insert to authenticated with check(public.mnemos_workspace_role(workspace_id) in ('writer','admin'));
drop policy if exists knowledge_links_member_update on public.knowledge_links;
create policy knowledge_links_member_update on public.knowledge_links for update to authenticated using(public.mnemos_workspace_role(workspace_id) in ('writer','admin')) with check(public.mnemos_workspace_role(workspace_id) in ('writer','admin'));
drop policy if exists knowledge_links_member_delete on public.knowledge_links;
create policy knowledge_links_member_delete on public.knowledge_links for delete to authenticated using(public.mnemos_workspace_role(workspace_id) in ('writer','admin'));
grant select,insert,update,delete on public.knowledge_workspaces,public.knowledge_workspace_members,public.knowledge_nodes,public.knowledge_links to authenticated;
