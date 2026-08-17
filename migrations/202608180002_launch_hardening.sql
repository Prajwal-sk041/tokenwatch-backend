create table if not exists public.policy_decisions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  ingestion_key_id uuid references public.api_keys(id) on delete set null,
  provider text not null,
  model text not null,
  decision text not null check (decision in ('allow','warn','block','log')),
  reason text not null,
  estimated_cost numeric(20,10) not null default 0,
  remaining_budget numeric(20,10),
  created_at timestamptz not null default now()
);

create index if not exists policy_decisions_org_created_idx
  on public.policy_decisions (organization_id, created_at desc);
create index if not exists policy_decisions_ingestion_key_idx
  on public.policy_decisions (ingestion_key_id)
  where ingestion_key_id is not null;

alter table public.policy_decisions enable row level security;
revoke all on table public.policy_decisions from anon, authenticated;

comment on table public.policy_decisions is
  'Server-only evidence ledger for SDK policy checks; never stores provider keys or prompts.';
