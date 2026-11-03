-- Retire the legacy permanent graph tables. Knowledge branch snapshots are canonical;
-- new writes must go through the temporary mnemos_outbox transport.
revoke all on table
  public.knowledge_nodes,
  public.knowledge_links,
  public.knowledge_edges,
  public.steadfast_knowledge_nodes,
  public.steadfast_knowledge_edges
from public, anon, authenticated, service_role;

comment on table public.knowledge_nodes is 'Retired legacy graph table. Canonical graph lives in mnemos-RLI:Knowledge; transport uses public.mnemos_outbox.';
comment on table public.knowledge_links is 'Retired legacy graph table. Canonical graph lives in mnemos-RLI:Knowledge; transport uses public.mnemos_outbox.';
comment on table public.knowledge_edges is 'Retired legacy graph table. Canonical graph lives in mnemos-RLI:Knowledge; transport uses public.mnemos_outbox.';
