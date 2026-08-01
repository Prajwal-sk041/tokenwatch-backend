begin;

alter table public.plans
  add column if not exists description text not null default '',
  add column if not exists stripe_product_id text,
  add column if not exists stripe_price_id text,
  add column if not exists annual_price numeric(12,2) not null default 0 check (annual_price >= 0),
  add column if not exists entitlements jsonb not null default '{}'::jsonb check (jsonb_typeof(entitlements) = 'object'),
  add column if not exists sort_order integer not null default 0;
create unique index if not exists plans_stripe_price_uidx on public.plans(stripe_price_id) where stripe_price_id is not null;

alter table public.users add column if not exists is_platform_admin boolean not null default false;

alter table public.subscriptions
  add column if not exists trial_start timestamptz,
  add column if not exists trial_end timestamptz,
  add column if not exists canceled_at timestamptz,
  add column if not exists conversion_at timestamptz,
  add column if not exists provider_price_id text,
  add column if not exists latest_invoice_id text,
  add column if not exists payment_failure_at timestamptz,
  add column if not exists metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object');
alter table public.subscriptions drop constraint if exists subscriptions_status_check;
alter table public.subscriptions add constraint subscriptions_status_check check
  (status in ('incomplete','incomplete_expired','trialing','active','past_due','canceled','unpaid','paused'));
create unique index if not exists subscriptions_customer_uidx on public.subscriptions(provider, provider_customer_id) where provider_customer_id is not null and deleted_at is null;

create table if not exists public.billing_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null check (provider in ('stripe','manual')),
  provider_event_id text not null,
  event_type text not null,
  organization_id uuid references public.organizations(id) on delete set null,
  status text not null default 'received' check (status in ('received','processed','ignored','failed')),
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  error_message text,
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(provider, provider_event_id)
);
create index if not exists billing_events_org_created_idx on public.billing_events(organization_id, created_at desc);
create index if not exists billing_events_status_idx on public.billing_events(status, created_at) where status in ('received','failed');

create table if not exists public.invoices (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  subscription_id uuid references public.subscriptions(id) on delete set null,
  provider text not null check (provider in ('stripe','manual')),
  provider_invoice_id text not null,
  number text,
  status text not null,
  currency text not null default 'USD' check (currency ~ '^[A-Z]{3}$'),
  subtotal numeric(12,2) not null default 0 check (subtotal >= 0),
  tax numeric(12,2) not null default 0 check (tax >= 0),
  total numeric(12,2) not null default 0 check (total >= 0),
  amount_paid numeric(12,2) not null default 0 check (amount_paid >= 0),
  hosted_invoice_url text,
  invoice_pdf text,
  due_at timestamptz,
  paid_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(provider, provider_invoice_id)
);
create index if not exists invoices_org_created_idx on public.invoices(organization_id, created_at desc) where deleted_at is null;

create table if not exists public.email_deliveries (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.organizations(id) on delete set null,
  user_id uuid references public.users(id) on delete set null,
  template text not null,
  recipient_hash text not null,
  provider text not null check (provider in ('resend','smtp','preview')),
  provider_message_id text,
  status text not null check (status in ('sent','failed','previewed')),
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists email_deliveries_org_created_idx on public.email_deliveries(organization_id, created_at desc);

create or replace function public.increment_usage_counters(
  p_organization_id uuid, p_user_id uuid, p_provider text, p_model text,
  p_requests bigint, p_tokens bigint, p_cost numeric
) returns void language plpgsql security invoker set search_path = '' as $$
declare
  period_kind text; period_day date; scope_user uuid; scope_provider text; scope_model text;
begin
  foreach period_kind in array array['daily','monthly'] loop
    period_day := case when period_kind = 'daily' then current_date else date_trunc('month', current_date)::date end;
    for scope_user, scope_provider, scope_model in
      select null::uuid, null::text, null::text
      union all select null::uuid, p_provider, null::text
      union all select null::uuid, p_provider, p_model
      union all select p_user_id, null::text, null::text where p_user_id is not null
      union all select p_user_id, p_provider, null::text where p_user_id is not null
      union all select p_user_id, p_provider, p_model where p_user_id is not null
    loop
      insert into public.usage_counters(organization_id,user_id,provider,model,period_type,period_start,request_count,token_count,cost)
      values(p_organization_id,scope_user,scope_provider,scope_model,period_kind,period_day,p_requests,p_tokens,p_cost)
      on conflict(organization_id,user_id,provider,model,period_type,period_start)
      do update set request_count=public.usage_counters.request_count+excluded.request_count,
        token_count=public.usage_counters.token_count+excluded.token_count,
        cost=public.usage_counters.cost+excluded.cost,updated_at=now();
    end loop;
  end loop;
end;
$$;
revoke all on function public.increment_usage_counters(uuid,uuid,text,text,bigint,bigint,numeric) from public, anon, authenticated;
grant execute on function public.increment_usage_counters(uuid,uuid,text,text,bigint,bigint,numeric) to service_role;

-- Counters are derived data. Rebuild once so historical attributed usage is included in organization limits.
delete from public.usage_counters;
do $$ declare item record; begin
  for item in select organization_id,user_id,provider,model,total_tokens,calculated_cost from public.usage_logs where deleted_at is null loop
    perform public.increment_usage_counters(item.organization_id,item.user_id,item.provider,item.model,1,item.total_tokens,item.calculated_cost);
  end loop;
end $$;

do $$ declare t text; begin
  foreach t in array array['billing_events','invoices','email_deliveries'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop trigger if exists %I_set_updated_at on public.%I', t, t);
    execute format('create trigger %I_set_updated_at before update on public.%I for each row execute function public.set_updated_at()', t, t);
  end loop;
end $$;

create policy invoices_org_select on public.invoices for select to authenticated
using ((select private.is_organization_member(organization_id)));
revoke all on public.billing_events, public.email_deliveries from anon, authenticated;
grant select on public.invoices to authenticated;
grant all on public.billing_events, public.invoices, public.email_deliveries to service_role;

insert into public.plans(code,name,description,monthly_price,annual_price,monthly_event_limit,features,entitlements,sort_order,is_active)
values
('free','Free','For evaluation and personal projects',0,0,10000,
 '{"organizations":1,"members":1}'::jsonb,
 '{"organizations":1,"members":1,"provider_keys":2,"sdk_keys":2,"monthly_requests":10000,"monthly_tokens":1000000,"monthly_spend":25,"budgets":2,"alerts":2,"audit_retention_days":7,"export":false,"api_access":true}'::jsonb,10,true),
('starter','Starter','For small production workloads',19,190,100000,
 '{"organizations":1,"members":3}'::jsonb,
 '{"organizations":1,"members":3,"provider_keys":5,"sdk_keys":5,"monthly_requests":100000,"monthly_tokens":10000000,"monthly_spend":500,"budgets":10,"alerts":10,"audit_retention_days":30,"export":true,"api_access":true}'::jsonb,20,true),
('pro','Pro','For growing AI products',49,490,1000000,
 '{"organizations":5,"members":10}'::jsonb,
 '{"organizations":5,"members":10,"provider_keys":50,"sdk_keys":50,"monthly_requests":1000000,"monthly_tokens":100000000,"monthly_spend":10000,"budgets":100,"alerts":100,"audit_retention_days":365,"export":true,"api_access":true}'::jsonb,30,true),
('team','Team','For multi-team operations',149,1490,5000000,
 '{"organizations":25,"members":50}'::jsonb,
 '{"organizations":25,"members":50,"provider_keys":-1,"sdk_keys":-1,"monthly_requests":5000000,"monthly_tokens":500000000,"monthly_spend":100000,"budgets":-1,"alerts":-1,"audit_retention_days":730,"export":true,"api_access":true}'::jsonb,40,true),
('enterprise','Enterprise','Custom limits, retention, and support',0,0,9223372036854775807,
 '{"organizations":-1,"members":-1}'::jsonb,
 '{"organizations":-1,"members":-1,"provider_keys":-1,"sdk_keys":-1,"monthly_requests":-1,"monthly_tokens":-1,"monthly_spend":-1,"budgets":-1,"alerts":-1,"audit_retention_days":-1,"export":true,"api_access":true,"sso":true,"scim":true}'::jsonb,50,true)
on conflict(code) do update set name=excluded.name,description=excluded.description,monthly_price=excluded.monthly_price,
 annual_price=excluded.annual_price,monthly_event_limit=excluded.monthly_event_limit,features=excluded.features,
 entitlements=excluded.entitlements,sort_order=excluded.sort_order,is_active=excluded.is_active,updated_at=now();

commit;
