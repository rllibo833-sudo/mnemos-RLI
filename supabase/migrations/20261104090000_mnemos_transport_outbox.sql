-- Temporary transport outbox. Mnemos Knowledge branch remains the durable canonical graph.
create table if not exists public.mnemos_outbox (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  event_type text not null check (char_length(event_type) between 1 and 80),
  idempotency_key text not null check (char_length(idempotency_key) between 1 and 256),
  payload jsonb not null,
  payload_sha256 text not null check (payload_sha256 ~ '^[a-f0-9]{64}$'),
  created_at timestamptz not null default now(),
  delivered_at timestamptz,
  delivery_commit text,
  attempts integer not null default 0 check (attempts >= 0),
  last_error text,
  constraint mnemos_outbox_idempotency_unique unique (workspace_id, idempotency_key)
);
create index if not exists mnemos_outbox_pending_idx
  on public.mnemos_outbox(created_at, id) where delivered_at is null;
alter table public.mnemos_outbox enable row level security;
revoke all on public.mnemos_outbox from public, anon, authenticated;
grant usage on schema public to service_role;
grant select, insert, update on public.mnemos_outbox to service_role;
comment on table public.mnemos_outbox is
  'Short-lived transport only. Successful deliveries are acknowledged after a verified Mnemos Knowledge branch commit.';
notify pgrst, 'reload schema';
