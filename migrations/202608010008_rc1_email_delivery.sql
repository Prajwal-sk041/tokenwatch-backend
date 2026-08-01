begin;

alter table public.email_deliveries drop constraint if exists email_deliveries_status_check;
alter table public.email_deliveries add constraint email_deliveries_status_check
  check (status in ('sent','failed','previewed','dead_letter'));
alter table public.email_deliveries add column if not exists dead_lettered_at timestamptz;
create index if not exists email_deliveries_dead_letter_idx
  on public.email_deliveries(dead_lettered_at desc) where status='dead_letter';
create index if not exists support_tickets_user_idx on public.support_tickets(user_id) where user_id is not null;
create index if not exists support_tickets_assigned_to_idx on public.support_tickets(assigned_to) where assigned_to is not null;

alter policy "Users manage own alert rules" on public.alert_rules_phase1_legacy
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
alter policy "Users view own alert history" on public.alert_history_phase1_legacy
  using ((select auth.uid()) = user_id);

commit;
