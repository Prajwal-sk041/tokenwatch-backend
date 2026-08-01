begin;

-- Cover every Phase 2 foreign key used by delete/update checks and joins.
create index if not exists organizations_plan_idx on public.organizations (plan_id) where plan_id is not null;
create index if not exists organization_members_invited_by_idx on public.organization_members (invited_by) where invited_by is not null;
create index if not exists api_keys_created_by_idx on public.api_keys (created_by) where created_by is not null;
create index if not exists api_keys_rotated_from_idx on public.api_keys (rotated_from_id) where rotated_from_id is not null;
create index if not exists usage_logs_ingestion_key_idx on public.usage_logs (ingestion_key_id) where ingestion_key_id is not null;
create index if not exists alert_rules_created_by_idx on public.alert_rules (created_by) where created_by is not null;
create index if not exists subscriptions_plan_idx on public.subscriptions (plan_id);
create index if not exists auth_sessions_replaced_by_idx on public.auth_sessions (replaced_by_session_id) where replaced_by_session_id is not null;

-- Avoid overlapping permissive SELECT policies while retaining admin writes.
drop policy if exists organization_members_admin_write on public.organization_members;
create policy organization_members_admin_insert on public.organization_members
for insert to authenticated
with check ((select private.is_organization_member(organization_id, array['owner','admin'])));
create policy organization_members_admin_update on public.organization_members
for update to authenticated
using ((select private.is_organization_member(organization_id, array['owner','admin'])))
with check ((select private.is_organization_member(organization_id, array['owner','admin'])));
create policy organization_members_admin_delete on public.organization_members
for delete to authenticated
using ((select private.is_organization_member(organization_id, array['owner','admin'])));

commit;
