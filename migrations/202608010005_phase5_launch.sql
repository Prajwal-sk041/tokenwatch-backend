begin;

alter table public.plans
  add column if not exists stripe_test_product_id text,
  add column if not exists stripe_test_monthly_price_id text,
  add column if not exists stripe_test_annual_price_id text,
  add column if not exists stripe_live_product_id text,
  add column if not exists stripe_live_monthly_price_id text,
  add column if not exists stripe_live_annual_price_id text;

alter table public.billing_events
  add column if not exists livemode boolean not null default false,
  add column if not exists attempts integer not null default 1 check (attempts >= 1),
  add column if not exists next_retry_at timestamptz,
  add column if not exists request_id text;
create index if not exists billing_events_retry_idx on public.billing_events(next_retry_at) where status='failed' and next_retry_at is not null;

alter table public.email_deliveries
  add column if not exists idempotency_key text,
  add column if not exists attempts integer not null default 1 check (attempts >= 1),
  add column if not exists next_retry_at timestamptz,
  add column if not exists metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object');
create unique index if not exists email_deliveries_idempotency_uidx on public.email_deliveries(idempotency_key) where idempotency_key is not null;
create index if not exists email_deliveries_retry_idx on public.email_deliveries(next_retry_at) where status='failed' and next_retry_at is not null;
create index if not exists email_deliveries_user_idx on public.email_deliveries(user_id,created_at desc) where user_id is not null;
create index if not exists invoices_subscription_idx on public.invoices(subscription_id,created_at desc) where subscription_id is not null;

create table if not exists public.feature_flags(
  id uuid primary key default gen_random_uuid(),
  key text not null,
  description text not null default '',
  enabled boolean not null default false,
  organization_id uuid references public.organizations(id) on delete cascade,
  rollout_percent integer not null default 100 check (rollout_percent between 0 and 100),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object'),
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists feature_flags_scope_uidx on public.feature_flags(key,coalesce(organization_id,'00000000-0000-0000-0000-000000000000'::uuid)) where deleted_at is null;

create table if not exists public.support_tickets(
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.organizations(id) on delete set null,
  user_id uuid references public.users(id) on delete set null,
  category text not null check(category in ('support','billing','bug','feedback','security')),
  subject text not null check(length(subject) between 3 and 160),
  message text not null check(length(message) between 10 and 10000),
  status text not null default 'open' check(status in ('open','in_progress','resolved','closed')),
  priority text not null default 'normal' check(priority in ('low','normal','high','urgent')),
  assigned_to uuid references public.users(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb check(jsonb_typeof(metadata)='object'),
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists support_tickets_org_created_idx on public.support_tickets(organization_id,created_at desc) where deleted_at is null;
create index if not exists support_tickets_status_idx on public.support_tickets(status,priority,created_at) where deleted_at is null and status not in ('resolved','closed');

create table if not exists public.service_incidents(
  id uuid primary key default gen_random_uuid(),
  service text not null check(service in ('api','scheduler','email','billing','database','webhook')),
  title text not null,
  message text not null,
  status text not null check(status in ('investigating','identified','monitoring','resolved')),
  impact text not null check(impact in ('none','minor','major','critical')),
  started_at timestamptz not null,
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists service_incidents_service_started_idx on public.service_incidents(service,started_at desc);

create table if not exists public.rate_limit_buckets(
  id uuid primary key default gen_random_uuid(),
  bucket_key text not null,
  window_start timestamptz not null,
  request_count integer not null default 1 check(request_count >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(bucket_key,window_start)
);
create index if not exists rate_limit_buckets_expiry_idx on public.rate_limit_buckets(window_start);

create or replace function private.consume_rate_limit(p_key text,p_window_seconds integer,p_limit integer)
returns boolean language plpgsql security definer set search_path='' as $$
declare v_window timestamptz; v_count integer;
begin
  if p_window_seconds < 1 or p_limit < 1 then return false; end if;
  v_window := to_timestamp(floor(extract(epoch from now())/p_window_seconds)*p_window_seconds);
  insert into public.rate_limit_buckets(bucket_key,window_start,request_count) values(p_key,v_window,1)
  on conflict(bucket_key,window_start) do update set request_count=public.rate_limit_buckets.request_count+1,updated_at=now()
  returning request_count into v_count;
  return v_count <= p_limit;
end;$$;
revoke all on function private.consume_rate_limit(text,integer,integer) from public,anon,authenticated;
grant execute on function private.consume_rate_limit(text,integer,integer) to service_role;

do $$ declare t text; begin
  foreach t in array array['feature_flags','support_tickets','service_incidents','rate_limit_buckets'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('drop trigger if exists %I_set_updated_at on public.%I',t,t);
    execute format('create trigger %I_set_updated_at before update on public.%I for each row execute function public.set_updated_at()',t,t);
  end loop;
end$$;
create policy support_tickets_member_select on public.support_tickets for select to authenticated using((select private.is_organization_member(organization_id)));
revoke all on public.feature_flags,public.service_incidents,public.rate_limit_buckets from anon,authenticated;
grant select,insert on public.support_tickets to authenticated;
grant all on public.feature_flags,public.support_tickets,public.service_incidents,public.rate_limit_buckets to service_role;

commit;
