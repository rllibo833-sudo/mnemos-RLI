-- Explicitly scope transport access to the server-only service role.
drop policy if exists mnemos_outbox_service_role_all on public.mnemos_outbox;
create policy mnemos_outbox_service_role_all
  on public.mnemos_outbox
  for all
  to service_role
  using (true)
  with check (true);

-- This trigger function is invoked by auth.users inserts; it is not an RPC API.
revoke all on function public.ensure_steadfast_living_shared_member() from public, anon, authenticated;
