begin;

create table if not exists public.onboarding_progress (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null unique references public.organizations(id) on delete cascade,
  integration_type text check (integration_type is null or integration_type in ('python','node','rest')),
  provider text check (provider is null or provider in ('openai','anthropic','gemini','groq','openrouter','azure_openai','aws_bedrock')),
  current_step integer not null default 1 check (current_step between 1 and 11),
  completed_steps integer[] not null default array[]::integer[],
  test_usage_log_id uuid references public.usage_logs(id) on delete set null,
  first_budget_id uuid references public.budget_policies(id) on delete set null,
  completed_at timestamptz,
  skipped_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists onboarding_test_usage_idx on public.onboarding_progress (test_usage_log_id) where test_usage_log_id is not null;
create index if not exists onboarding_first_budget_idx on public.onboarding_progress (first_budget_id) where first_budget_id is not null;
alter table public.onboarding_progress enable row level security;
drop trigger if exists onboarding_progress_set_updated_at on public.onboarding_progress;
create trigger onboarding_progress_set_updated_at before update on public.onboarding_progress
for each row execute function public.set_updated_at();
create policy onboarding_progress_org_select on public.onboarding_progress for select to authenticated
using ((select private.is_organization_member(organization_id)));
revoke all on public.onboarding_progress from anon, authenticated;
grant select on public.onboarding_progress to authenticated;
grant all on public.onboarding_progress to service_role;

commit;
