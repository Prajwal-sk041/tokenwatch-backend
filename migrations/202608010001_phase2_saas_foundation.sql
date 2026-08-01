begin;

create extension if not exists pgcrypto;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

-- Preserve incompatible Phase 1 tables instead of destructively replacing them.
do $$
declare
  legacy_name text;
begin
  foreach legacy_name in array array['users','api_keys','usage_logs','alert_rules','alert_history'] loop
    if to_regclass('public.' || legacy_name) is not null
       and not exists (
         select 1 from information_schema.columns
         where table_schema = 'public' and information_schema.columns.table_name = legacy_name
           and column_name = case when legacy_name = 'users' then 'token_version' else 'organization_id' end
       )
       and to_regclass('public.' || legacy_name || '_phase1_legacy') is null then
      execute format('alter table public.%I rename to %I', legacy_name, legacy_name || '_phase1_legacy');
    end if;
  end loop;
end $$;

create or replace function public.set_updated_at()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.plans (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  monthly_price numeric(12,2) not null default 0 check (monthly_price >= 0),
  currency text not null default 'USD' check (currency ~ '^[A-Z]{3}$'),
  monthly_event_limit bigint not null default 10000 check (monthly_event_limit >= 0),
  features jsonb not null default '{}'::jsonb check (jsonb_typeof(features) = 'object'),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  hashed_password text not null,
  full_name text not null default '',
  email_verified_at timestamptz,
  is_active boolean not null default true,
  disabled_at timestamptz,
  token_version integer not null default 1 check (token_version > 0),
  last_login_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint users_email_normalized check (email = lower(trim(email))),
  constraint users_disabled_consistent check (is_active or disabled_at is not null)
);
create unique index if not exists users_active_email_uidx on public.users (email) where deleted_at is null;

create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 1 and 120),
  slug text not null check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  owner_user_id uuid not null references public.users(id) on delete restrict,
  plan_id uuid references public.plans(id) on delete restrict,
  status text not null default 'active' check (status in ('active','suspended','closed')),
  monthly_budget numeric(18,6) check (monthly_budget is null or monthly_budget >= 0),
  daily_budget numeric(18,6) check (daily_budget is null or daily_budget >= 0),
  warning_threshold_percent numeric(5,2) not null default 80 check (warning_threshold_percent between 0 and 100),
  hard_stop_threshold_percent numeric(5,2) not null default 100 check (hard_stop_threshold_percent between 0 and 100),
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists organizations_active_slug_uidx on public.organizations (slug) where deleted_at is null;
create index if not exists organizations_owner_idx on public.organizations (owner_user_id) where deleted_at is null;

create table if not exists public.organization_members (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid references public.users(id) on delete cascade,
  invited_email text,
  role text not null check (role in ('owner','admin','member','viewer')),
  status text not null default 'active' check (status in ('invited','active','revoked')),
  invitation_token_hash text,
  invited_by uuid references public.users(id) on delete set null,
  invitation_expires_at timestamptz,
  joined_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organization_member_identity check (user_id is not null or invited_email is not null),
  constraint organization_member_invite check (status <> 'invited' or (invited_email is not null and invitation_token_hash is not null and invitation_expires_at is not null))
);
create unique index if not exists organization_members_active_user_uidx on public.organization_members (organization_id, user_id) where deleted_at is null and user_id is not null;
create unique index if not exists organization_members_pending_email_uidx on public.organization_members (organization_id, lower(invited_email)) where deleted_at is null and status = 'invited';
create index if not exists organization_members_user_idx on public.organization_members (user_id, organization_id) where deleted_at is null;
create index if not exists organization_members_org_role_idx on public.organization_members (organization_id, role, status) where deleted_at is null;

-- Convert Phase 1 identities into verified owners of isolated legacy workspaces.
do $$
begin
  if to_regclass('public.users_phase1_legacy') is not null then
    insert into public.users (id,email,hashed_password,full_name,email_verified_at,is_active,created_at,updated_at)
    select id,lower(trim(email)),hashed_password,coalesce(full_name,''),coalesce(created_at,now()),coalesce(is_active,true),coalesce(created_at,now()),coalesce(created_at,now())
    from public.users_phase1_legacy on conflict (id) do nothing;

    insert into public.organizations (name,slug,owner_user_id,created_at,updated_at)
    select coalesce(nullif(full_name,''),split_part(email,'@',1)) || '''s workspace', 'legacy-' || replace(id::text,'-',''), id, coalesce(created_at,now()), coalesce(created_at,now())
    from public.users_phase1_legacy on conflict do nothing;

    insert into public.organization_members (organization_id,user_id,role,status,joined_at,created_at,updated_at)
    select o.id,u.id,'owner','active',coalesce(u.created_at,now()),coalesce(u.created_at,now()),coalesce(u.created_at,now())
    from public.users_phase1_legacy u join public.organizations o on o.owner_user_id = u.id
    on conflict do nothing;
  end if;
end $$;

create table if not exists public.api_keys (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  created_by uuid references public.users(id) on delete set null,
  key_type text not null check (key_type in ('provider','ingestion')),
  name text not null check (char_length(name) between 1 and 80),
  provider text,
  encrypted_key text,
  key_prefix text,
  key_hash text,
  permissions text[] not null default array[]::text[],
  last_used_at timestamptz,
  expires_at timestamptz,
  revoked_at timestamptz,
  rotated_from_id uuid references public.api_keys(id) on delete set null,
  is_active boolean not null default true,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint api_keys_material_by_type check (
    (key_type = 'provider' and provider is not null and encrypted_key is not null and key_hash is null)
    or (key_type = 'ingestion' and provider is null and encrypted_key is null and key_hash is not null and key_prefix is not null)
  ),
  constraint api_keys_revocation_consistent check (is_active or revoked_at is not null or deleted_at is not null)
);
create unique index if not exists api_keys_org_name_uidx on public.api_keys (organization_id, lower(name)) where deleted_at is null and is_active;
create unique index if not exists api_keys_hash_uidx on public.api_keys (key_hash) where key_hash is not null;
create index if not exists api_keys_org_type_idx on public.api_keys (organization_id, key_type, created_at desc) where deleted_at is null;

do $$ begin
  if to_regclass('public.api_keys_phase1_legacy') is not null then
    insert into public.api_keys (id,organization_id,created_by,key_type,name,provider,encrypted_key,is_active,created_at,updated_at)
    select k.id,o.id,k.user_id,'provider',k.key_name,k.provider,k.encrypted_key,coalesce(k.is_active,true),coalesce(k.created_at,now()),coalesce(k.created_at,now())
    from public.api_keys_phase1_legacy k join public.organizations o on o.owner_user_id = k.user_id
    on conflict (id) do nothing;
  end if;
end $$;

create table if not exists public.usage_logs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid references public.users(id) on delete set null,
  ingestion_key_id uuid references public.api_keys(id) on delete set null,
  idempotency_key text not null,
  request_timestamp timestamptz not null,
  provider text not null check (provider in ('openai','anthropic','gemini','groq','openrouter','azure_openai','aws_bedrock')),
  model text not null,
  prompt_tokens bigint not null default 0 check (prompt_tokens >= 0),
  completion_tokens bigint not null default 0 check (completion_tokens >= 0),
  total_tokens bigint not null check (total_tokens >= 0 and total_tokens = prompt_tokens + completion_tokens),
  calculated_cost numeric(18,8) not null check (calculated_cost >= 0),
  currency text not null default 'USD' check (currency ~ '^[A-Z]{3}$'),
  project text not null default 'default',
  agent text not null default 'default',
  environment text not null default 'production',
  latency_ms integer check (latency_ms is null or latency_ms >= 0),
  provider_request_id text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, idempotency_key)
);
create index if not exists usage_logs_org_created_idx on public.usage_logs (organization_id, created_at desc) where deleted_at is null;
create index if not exists usage_logs_org_provider_created_idx on public.usage_logs (organization_id, provider, created_at desc) where deleted_at is null;
create index if not exists usage_logs_org_model_created_idx on public.usage_logs (organization_id, model, created_at desc) where deleted_at is null;
create index if not exists usage_logs_user_created_idx on public.usage_logs (user_id, created_at desc) where user_id is not null and deleted_at is null;
create unique index if not exists usage_logs_provider_request_uidx on public.usage_logs (organization_id, provider, provider_request_id) where provider_request_id is not null;

do $$ begin
  if to_regclass('public.usage_logs_phase1_legacy') is not null then
    insert into public.usage_logs (id,organization_id,user_id,idempotency_key,request_timestamp,provider,model,prompt_tokens,completion_tokens,total_tokens,calculated_cost,project,agent,environment,latency_ms,metadata,created_at,updated_at)
    select l.id,o.id,l.user_id,'legacy:' || l.id::text,coalesce(l.logged_at,now()),
      case when l.provider in ('openai','anthropic','gemini','groq','openrouter','azure_openai','aws_bedrock') then l.provider else 'openai' end,
      coalesce(nullif(l.model,''),'legacy-unknown'),
      case when coalesce(l.prompt_tokens,0) + coalesce(l.completion_tokens,0) = 0 then greatest(coalesce(l.tokens_used,0),0) else greatest(coalesce(l.prompt_tokens,0),0) end,
      greatest(coalesce(l.completion_tokens,0),0),
      case when coalesce(l.prompt_tokens,0) + coalesce(l.completion_tokens,0) = 0 then greatest(coalesce(l.tokens_used,0),0) else greatest(coalesce(l.prompt_tokens,0),0) + greatest(coalesce(l.completion_tokens,0),0) end,
      greatest(coalesce(l.cost,0),0)::numeric,coalesce(l.project,'default'),coalesce(l.agent,'default'),coalesce(l.environment,'development'),greatest(coalesce(l.latency_ms,0),0),
      jsonb_build_object('migrated_from','phase1','legacy_api_key_id',l.api_key_id),coalesce(l.logged_at,now()),coalesce(l.logged_at,now())
    from public.usage_logs_phase1_legacy l join public.organizations o on o.owner_user_id = l.user_id
    on conflict (id) do nothing;
  end if;
end $$;

create table if not exists public.alert_rules (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  created_by uuid references public.users(id) on delete set null,
  name text not null,
  metric text not null check (metric in ('cost','tokens','requests')),
  period text not null check (period in ('daily','monthly')),
  threshold numeric(18,6) not null check (threshold > 0),
  provider text,
  model text,
  channel text not null check (channel in ('email','webhook','slack','teams')),
  destination text,
  is_active boolean not null default true,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists alert_rules_org_active_idx on public.alert_rules (organization_id, is_active) where deleted_at is null;

create table if not exists public.alert_history (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  rule_id uuid references public.alert_rules(id) on delete set null,
  status text not null check (status in ('queued','sent','failed','stubbed')),
  channel text not null check (channel in ('email','webhook','slack','teams')),
  current_value numeric(18,6) not null,
  threshold numeric(18,6) not null,
  payload jsonb not null default '{}'::jsonb,
  error_message text,
  triggered_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists alert_history_org_triggered_idx on public.alert_history (organization_id, triggered_at desc);
create index if not exists alert_history_rule_idx on public.alert_history (rule_id, triggered_at desc) where rule_id is not null;

do $$ begin
  if to_regclass('public.alert_rules_phase1_legacy') is not null then
    insert into public.alert_rules (id,organization_id,created_by,name,metric,period,threshold,provider,channel,destination,is_active,created_at,updated_at)
    select r.id,o.id,r.user_id,coalesce(r.period,'daily') || ' ' || r.alert_type || ' alert',r.alert_type,coalesce(r.period,'daily'),r.threshold::numeric,nullif(r.provider,'all'),'email',r.notify_email,coalesce(r.is_active,true),coalesce(r.created_at,now()),coalesce(r.created_at,now())
    from public.alert_rules_phase1_legacy r join public.organizations o on o.owner_user_id = r.user_id
    on conflict (id) do nothing;
  end if;
  if to_regclass('public.alert_history_phase1_legacy') is not null then
    insert into public.alert_history (id,organization_id,rule_id,status,channel,current_value,threshold,payload,triggered_at,created_at,updated_at)
    select h.id,o.id,h.rule_id,case when coalesce(h.email_sent,false) then 'sent' else 'failed' end,'email',h.current_val::numeric,h.threshold::numeric,
      jsonb_build_object('migrated_from','phase1','provider',h.provider,'alert_type',h.alert_type),coalesce(h.triggered_at,now()),coalesce(h.triggered_at,now()),coalesce(h.triggered_at,now())
    from public.alert_history_phase1_legacy h join public.organizations o on o.owner_user_id = h.user_id
    left join public.alert_rules r on r.id = h.rule_id
    on conflict (id) do nothing;
  end if;
end $$;

create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  plan_id uuid not null references public.plans(id) on delete restrict,
  provider text not null default 'manual' check (provider in ('manual','stripe')),
  provider_customer_id text,
  provider_subscription_id text,
  status text not null check (status in ('trialing','active','past_due','canceled','paused')),
  current_period_start timestamptz,
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists subscriptions_org_active_uidx on public.subscriptions (organization_id) where deleted_at is null and status in ('trialing','active','past_due','paused');
create unique index if not exists subscriptions_provider_uidx on public.subscriptions (provider, provider_subscription_id) where provider_subscription_id is not null;

create table if not exists public.usage_counters (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid references public.users(id) on delete cascade,
  provider text,
  model text,
  period_type text not null check (period_type in ('daily','monthly')),
  period_start date not null,
  request_count bigint not null default 0 check (request_count >= 0),
  token_count bigint not null default 0 check (token_count >= 0),
  cost numeric(18,8) not null default 0 check (cost >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique nulls not distinct (organization_id, user_id, provider, model, period_type, period_start)
);
create index if not exists usage_counters_org_period_idx on public.usage_counters (organization_id, period_type, period_start desc);
create index if not exists usage_counters_user_period_idx on public.usage_counters (user_id, period_type, period_start desc) where user_id is not null;

create or replace function public.increment_usage_counters(
  p_organization_id uuid, p_user_id uuid, p_provider text, p_model text,
  p_requests bigint, p_tokens bigint, p_cost numeric
) returns void language plpgsql security invoker set search_path = '' as $$
declare
  period_kind text;
  period_day date;
  scope_provider text;
  scope_model text;
begin
  foreach period_kind in array array['daily','monthly'] loop
    period_day := case when period_kind = 'daily' then current_date else date_trunc('month', current_date)::date end;
    for scope_provider, scope_model in
      select null::text, null::text union all select p_provider, null::text union all select p_provider, p_model
    loop
      insert into public.usage_counters (organization_id,user_id,provider,model,period_type,period_start,request_count,token_count,cost)
      values (p_organization_id,p_user_id,scope_provider,scope_model,period_kind,period_day,p_requests,p_tokens,p_cost)
      on conflict (organization_id,user_id,provider,model,period_type,period_start)
      do update set request_count = public.usage_counters.request_count + excluded.request_count,
                    token_count = public.usage_counters.token_count + excluded.token_count,
                    cost = public.usage_counters.cost + excluded.cost,
                    updated_at = now();
    end loop;
  end loop;
end;
$$;
revoke all on function public.increment_usage_counters(uuid,uuid,text,text,bigint,bigint,numeric) from public, anon, authenticated;
grant execute on function public.increment_usage_counters(uuid,uuid,text,text,bigint,bigint,numeric) to service_role;

do $$ declare item record; begin
  for item in select organization_id,user_id,provider,model,total_tokens,calculated_cost from public.usage_logs loop
    perform public.increment_usage_counters(item.organization_id,item.user_id,item.provider,item.model,1,item.total_tokens,item.calculated_cost);
  end loop;
end $$;

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.organizations(id) on delete set null,
  actor_user_id uuid references public.users(id) on delete set null,
  action text not null,
  target_type text,
  target_id uuid,
  ip_address inet,
  user_agent text,
  request_id text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists audit_logs_org_created_idx on public.audit_logs (organization_id, created_at desc);
create index if not exists audit_logs_actor_created_idx on public.audit_logs (actor_user_id, created_at desc) where actor_user_id is not null;

create table if not exists public.auth_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  refresh_token_hash text not null unique,
  family_id uuid not null,
  expires_at timestamptz not null,
  last_used_at timestamptz,
  revoked_at timestamptz,
  replaced_by_session_id uuid references public.auth_sessions(id) on delete set null,
  ip_address inet,
  user_agent text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists auth_sessions_user_active_idx on public.auth_sessions (user_id, expires_at desc) where revoked_at is null;

create table if not exists public.auth_action_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  token_hash text not null unique,
  purpose text not null check (purpose in ('verify_email','reset_password')),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists auth_action_tokens_user_purpose_idx on public.auth_action_tokens (user_id, purpose, expires_at desc) where consumed_at is null;

create table if not exists public.budget_policies (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  scope_type text not null check (scope_type in ('organization','user','provider','model')),
  scope_value text,
  period_type text not null check (period_type in ('daily','monthly')),
  amount numeric(18,6) not null check (amount >= 0),
  warning_threshold_percent numeric(5,2) not null default 80 check (warning_threshold_percent between 0 and 100),
  hard_stop_threshold_percent numeric(5,2) not null default 100 check (hard_stop_threshold_percent between 0 and 100),
  action text not null default 'block' check (action in ('allow','warn','block','log')),
  is_active boolean not null default true,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint budget_policy_scope_value check ((scope_type = 'organization' and scope_value is null) or (scope_type <> 'organization' and scope_value is not null))
);
create unique index if not exists budget_policies_scope_uidx on public.budget_policies (organization_id, scope_type, coalesce(scope_value, ''), period_type) where deleted_at is null and is_active;

do $$ begin
  if to_regclass('public.api_keys_phase1_legacy') is not null then
    insert into public.budget_policies (organization_id,scope_type,scope_value,period_type,amount,warning_threshold_percent,hard_stop_threshold_percent,action)
    select distinct on (o.id,k.provider) o.id,'provider',k.provider,'monthly',k.monthly_budget::numeric,80,100,'block'
    from public.api_keys_phase1_legacy k join public.organizations o on o.owner_user_id = k.user_id
    where coalesce(k.monthly_budget,0) > 0
    on conflict do nothing;
  end if;
end $$;

create or replace function private.is_organization_member(target_organization_id uuid, allowed_roles text[] default array['owner','admin','member','viewer'])
returns boolean language sql stable security definer set search_path = '' as $$
  select (select auth.uid()) is not null and exists (
    select 1 from public.organization_members m
    where m.organization_id = target_organization_id
      and m.user_id = (select auth.uid())
      and m.status = 'active' and m.deleted_at is null and m.role = any(allowed_roles)
  );
$$;
revoke all on function private.is_organization_member(uuid, text[]) from public, anon;
grant execute on function private.is_organization_member(uuid, text[]) to authenticated, service_role;

do $$ declare t text; begin
  foreach t in array array['plans','users','organizations','organization_members','api_keys','usage_logs','alert_rules','alert_history','subscriptions','usage_counters','audit_logs','auth_sessions','auth_action_tokens','budget_policies'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop trigger if exists %I_set_updated_at on public.%I', t, t);
    execute format('create trigger %I_set_updated_at before update on public.%I for each row execute function public.set_updated_at()', t, t);
  end loop;
end $$;

create policy organizations_member_select on public.organizations for select to authenticated
using ((select private.is_organization_member(id)));
create policy organization_members_member_select on public.organization_members for select to authenticated
using ((select private.is_organization_member(organization_id)));
create policy organization_members_admin_write on public.organization_members for all to authenticated
using ((select private.is_organization_member(organization_id, array['owner','admin'])))
with check ((select private.is_organization_member(organization_id, array['owner','admin'])));

do $$ declare t text; begin
  foreach t in array array['api_keys','usage_logs','alert_rules','alert_history','subscriptions','usage_counters','audit_logs','budget_policies'] loop
    execute format('create policy %I_org_select on public.%I for select to authenticated using ((select private.is_organization_member(organization_id)))', t, t);
  end loop;
end $$;

revoke all on all tables in schema public from anon;
grant usage on schema public to authenticated, service_role;
grant select on public.organizations, public.organization_members, public.api_keys, public.usage_logs, public.alert_rules, public.alert_history, public.subscriptions, public.plans, public.usage_counters, public.audit_logs, public.budget_policies to authenticated;
grant all on all tables in schema public to service_role;

insert into public.plans (code, name, monthly_price, monthly_event_limit, features)
values
  ('free','Free',0,10000,'{"organizations":1,"members":3}'::jsonb),
  ('pro','Pro',49,1000000,'{"organizations":5,"members":25}'::jsonb)
on conflict (code) do update set name = excluded.name, monthly_price = excluded.monthly_price, monthly_event_limit = excluded.monthly_event_limit, features = excluded.features;

commit;
