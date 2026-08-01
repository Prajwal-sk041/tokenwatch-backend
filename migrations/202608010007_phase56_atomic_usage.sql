-- Phase 5.6: atomic ingestion, exact counters, reconciliation, and alert job deduplication.
alter table public.usage_counters add column if not exists prompt_tokens bigint not null default 0 check (prompt_tokens >= 0);
alter table public.usage_counters add column if not exists completion_tokens bigint not null default 0 check (completion_tokens >= 0);

create index if not exists usage_logs_org_request_time_idx
  on public.usage_logs (organization_id, request_timestamp desc) where deleted_at is null;

create or replace function public.ingest_usage_atomic(p_event jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  existing_id uuid; inserted_id uuid; period_kind text; period_day date;
  scope_provider text; scope_model text; scope_user uuid; event_time timestamptz;
  month_requests bigint; month_tokens bigint; month_cost numeric;
begin
  if (p_event->>'organization_id') is null or (p_event->>'idempotency_key') is null then
    raise exception 'organization_id and idempotency_key are required';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_event->>'organization_id',0));
  select id into existing_id from public.usage_logs
   where organization_id=(p_event->>'organization_id')::uuid and idempotency_key=p_event->>'idempotency_key';
  if existing_id is not null then return jsonb_build_object('usage_id',existing_id,'duplicate',true); end if;
  event_time := (p_event->>'request_timestamp')::timestamptz;
  select coalesce(request_count,0),coalesce(token_count,0),coalesce(cost,0)
    into month_requests,month_tokens,month_cost from public.usage_counters
   where organization_id=(p_event->>'organization_id')::uuid and user_id is null and provider is null and model is null
     and period_type='monthly' and period_start=date_trunc('month',event_time)::date;
  month_requests:=coalesce(month_requests,0); month_tokens:=coalesce(month_tokens,0); month_cost:=coalesce(month_cost,0);
  if (p_event->>'limit_requests')::numeric <> -1 and month_requests+1 > (p_event->>'limit_requests')::numeric then raise exception 'usage_limit_reached:monthly_requests'; end if;
  if (p_event->>'limit_tokens')::numeric <> -1 and month_tokens+(p_event->>'total_tokens')::bigint > (p_event->>'limit_tokens')::numeric then raise exception 'usage_limit_reached:monthly_tokens'; end if;
  if (p_event->>'limit_spend')::numeric <> -1 and month_cost+(p_event->>'calculated_cost')::numeric > (p_event->>'limit_spend')::numeric then raise exception 'usage_limit_reached:monthly_spend'; end if;
  insert into public.usage_logs(organization_id,user_id,ingestion_key_id,idempotency_key,request_timestamp,
    provider,model,prompt_tokens,completion_tokens,total_tokens,calculated_cost,project,agent,environment,
    latency_ms,provider_request_id,metadata)
  values((p_event->>'organization_id')::uuid,nullif(p_event->>'user_id','')::uuid,
    nullif(p_event->>'ingestion_key_id','')::uuid,p_event->>'idempotency_key',event_time,
    p_event->>'provider',p_event->>'model',(p_event->>'prompt_tokens')::bigint,
    (p_event->>'completion_tokens')::bigint,(p_event->>'total_tokens')::bigint,
    (p_event->>'calculated_cost')::numeric,coalesce(p_event->>'project','default'),
    coalesce(p_event->>'agent','default'),coalesce(p_event->>'environment','production'),
    nullif(p_event->>'latency_ms','')::integer,nullif(p_event->>'provider_request_id',''),
    coalesce(p_event->'metadata','{}'::jsonb)) returning id into inserted_id;
  foreach period_kind in array array['daily','monthly'] loop
    period_day := case when period_kind='daily' then event_time::date else date_trunc('month',event_time)::date end;
    for scope_user in select null::uuid union select nullif(p_event->>'user_id','')::uuid loop
    for scope_provider,scope_model in select null::text,null::text union all select p_event->>'provider',null::text union all select p_event->>'provider',p_event->>'model' loop
      insert into public.usage_counters(organization_id,user_id,provider,model,period_type,period_start,
        request_count,prompt_tokens,completion_tokens,token_count,cost)
      values((p_event->>'organization_id')::uuid,scope_user,scope_provider,scope_model,
        period_kind,period_day,1,(p_event->>'prompt_tokens')::bigint,(p_event->>'completion_tokens')::bigint,
        (p_event->>'total_tokens')::bigint,(p_event->>'calculated_cost')::numeric)
      on conflict (organization_id,user_id,provider,model,period_type,period_start) do update set
        request_count=public.usage_counters.request_count+1,
        prompt_tokens=public.usage_counters.prompt_tokens+excluded.prompt_tokens,
        completion_tokens=public.usage_counters.completion_tokens+excluded.completion_tokens,
        token_count=public.usage_counters.token_count+excluded.token_count,
        cost=public.usage_counters.cost+excluded.cost,updated_at=now();
    end loop;
    end loop;
  end loop;
  return jsonb_build_object('usage_id',inserted_id,'duplicate',false);
exception when unique_violation then
  select id into existing_id from public.usage_logs where organization_id=(p_event->>'organization_id')::uuid and idempotency_key=p_event->>'idempotency_key';
  if existing_id is not null then return jsonb_build_object('usage_id',existing_id,'duplicate',true); end if;
  raise;
end $$;
revoke all on function public.ingest_usage_atomic(jsonb) from public,anon,authenticated;
grant execute on function public.ingest_usage_atomic(jsonb) to service_role;

create or replace function public.reconcile_usage_counters(p_organization_id uuid,p_repair boolean default false,p_actor_user_id uuid default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare before_rows jsonb; after_rows jsonb;
begin
  select coalesce(jsonb_agg(x),'[]'::jsonb) into before_rows from (
    select l.period_type,l.period_start,l.requests,l.prompt_tokens,l.completion_tokens,l.tokens,l.cost,
      coalesce(c.request_count,0) counter_requests,coalesce(c.prompt_tokens,0) counter_prompt_tokens,
      coalesce(c.completion_tokens,0) counter_completion_tokens,coalesce(c.token_count,0) counter_tokens,coalesce(c.cost,0) counter_cost
    from (select 'daily' period_type,request_timestamp::date period_start,count(*) requests,sum(prompt_tokens) prompt_tokens,
      sum(completion_tokens) completion_tokens,sum(total_tokens) tokens,sum(calculated_cost) cost from public.usage_logs
      where organization_id=p_organization_id and deleted_at is null group by request_timestamp::date
      union all select 'monthly',date_trunc('month',request_timestamp)::date,count(*),sum(prompt_tokens),sum(completion_tokens),sum(total_tokens),sum(calculated_cost)
      from public.usage_logs where organization_id=p_organization_id and deleted_at is null group by date_trunc('month',request_timestamp)::date) l
    left join public.usage_counters c on c.organization_id=p_organization_id and c.user_id is null and c.provider is null and c.model is null
      and c.period_type=l.period_type and c.period_start=l.period_start) x;
  if p_repair then
    delete from public.usage_counters where organization_id=p_organization_id;
    insert into public.usage_counters(organization_id,user_id,provider,model,period_type,period_start,request_count,prompt_tokens,completion_tokens,token_count,cost)
    select organization_id,scope_user,scope_provider,scope_model,period_type,period_start,count(*),sum(prompt_tokens),sum(completion_tokens),sum(total_tokens),sum(calculated_cost)
    from (select u.*,us.scope_user,p.period_type,case when p.period_type='daily' then u.request_timestamp::date else date_trunc('month',u.request_timestamp)::date end period_start,
      s.provider scope_provider,s.model scope_model from public.usage_logs u cross join (values('daily'),('monthly')) p(period_type)
      cross join lateral (select null::uuid scope_user union select u.user_id where u.user_id is not null) us
      cross join lateral (values(null::text,null::text),(u.provider,null::text),(u.provider,u.model)) s(provider,model)
      where u.organization_id=p_organization_id and u.deleted_at is null) q
    group by organization_id,scope_user,scope_provider,scope_model,period_type,period_start;
    insert into public.audit_logs(organization_id,actor_user_id,action,target_type,metadata)
      values(p_organization_id,p_actor_user_id,'usage.counters_reconciled','usage_counters',jsonb_build_object('source','usage_logs','mode','repair'));
  end if;
  after_rows := case when p_repair then public.reconcile_usage_counters(p_organization_id,false,null)->'before' else before_rows end;
  return jsonb_build_object('organization_id',p_organization_id,'repaired',p_repair,'before',before_rows,'after',after_rows);
end $$;
revoke all on function public.reconcile_usage_counters(uuid,boolean,uuid) from public,anon,authenticated;
grant execute on function public.reconcile_usage_counters(uuid,boolean,uuid) to service_role;

alter table public.alert_history add column if not exists deduplication_key text;
alter table public.alert_history add column if not exists attempt_count integer not null default 0;
alter table public.alert_history add column if not exists next_retry_at timestamptz;
create unique index if not exists alert_history_dedup_uidx on public.alert_history(deduplication_key) where deduplication_key is not null;
