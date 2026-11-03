-- Allow authenticated workspace writers to enqueue transport events, without reading or mutating the queue.
drop policy if exists mnemos_outbox_authenticated_writer_insert on public.mnemos_outbox;
create policy mnemos_outbox_authenticated_writer_insert
  on public.mnemos_outbox
  for insert
  to authenticated
  with check (public.mnemos_workspace_role(workspace_id) in ('writer','admin'));
grant insert on public.mnemos_outbox to authenticated;
