begin;

-- PostgREST resolves unqualified RPC calls through the exposed public schema.
-- Keep this security-definer function callable only by the server-side role.
create or replace function public.consume_rate_limit(
  p_key text,
  p_window_seconds integer,
  p_limit integer
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_window timestamptz;
  v_count integer;
begin
  if p_window_seconds < 1 or p_limit < 1 then
    return false;
  end if;

  v_window := to_timestamp(
    floor(extract(epoch from now()) / p_window_seconds) * p_window_seconds
  );

  insert into public.rate_limit_buckets (
    bucket_key,
    window_start,
    request_count
  )
  values (p_key, v_window, 1)
  on conflict (bucket_key, window_start)
  do update set
    request_count = public.rate_limit_buckets.request_count + 1,
    updated_at = now()
  returning request_count into v_count;

  return v_count <= p_limit;
end;
$$;

revoke all on function public.consume_rate_limit(text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.consume_rate_limit(text, integer, integer)
  to service_role;

drop function if exists private.consume_rate_limit(text, integer, integer);

commit;
