# TokenWatch Release Candidate Report

Date: 2026-08-01  
Backend baseline: `ca110ec` (`origin/main`)  
Frontend baseline: `ae13a70` (`origin/main`)  
Recommendation: **NO-GO**

## Executive summary

Phase 5.6 migration `phase56_atomic_usage` was applied to the healthy production Supabase project as migration `20260801130420`. Guarded reconciliation repaired both production organizations from immutable `usage_logs`; the final exact comparison reports zero mismatched daily or monthly root-counter rows.

The final zero-token bounded load profiles passed with all usage IDs unique: 40/10, 100/20, and 500/50. Live session, key, policy, reconciliation, dashboard/timezone, and cleanup checks passed. Local backend and frontend release suites passed.

The release remains **NO-GO** because the onboarding test-event endpoint was found to bypass atomic ingestion. The fix on `agent/rc-counter-integrity` must be reviewed, merged, deployed, and verified before launch. Production email, billing/webhook, alert scheduling, external monitoring, and confirmed backup/PITR activation are also incomplete.

## Production database activation

- Project status: `ACTIVE_HEALTHY`, PostgreSQL 17.
- Preflight migration history ended at Phase 5.5.
- Applied `migrations/202608010007_phase56_atomic_usage.sql` through the managed migration interface.
- Recorded migration: `20260801130420 phase56_atomic_usage`.
- Post-migration security advisors reported existing informational RLS-enabled/no-policy notices; no new Phase 5.6 security error was reported.
- Post-migration performance advisors reported existing informational unindexed-FK/unused-index notices and legacy RLS initialization warnings.

## Counter reconciliation

Before repair:

| Organization | Source | Requests | Tokens | Cost | Problem |
|---|---:|---:|---:|---:|---|
| Validation org | logs | 111 | 155,400 | $0.04329000 | Counters had 107 requests, 149,800 tokens, $0.04173000 |
| Earlier org | logs | 5 | 4,999,995 | $250.00000000 | May events were incorrectly represented by August counters |

The guarded reconciliation RPC ran once per affected organization in repair mode. The exact post-check compared requests, prompt tokens, completion tokens, total tokens, and cost for daily and monthly organization-level counters: **0 mismatch rows across 5 compared rows**.

After the final load run, the authenticated dry-run reconciliation still matched exactly at 1,494 requests, 714,000 prompt tokens, 285,600 completion tokens, 999,600 total tokens, and $0.27846 for both daily and monthly scopes.

## Verification results

### Local release checks

- Backend: 49/49 tests passed; Python compilation passed.
- Frontend: 13/13 tests passed; ESLint passed; TypeScript passed; Next.js production build generated 42 pages.
- Billing fixtures: signed test event accepted; environment mismatch rejected.
- Email fixture: Resend path exercised without exposing recipient secrets.
- Timezone fixtures: Asia/Kolkata boundary, Pacific DST 23-hour day, half-open custom ranges, invalid timezone rejection.

### Live acceptance checks

| Area | Result | Evidence |
|---|---|---|
| Service health | PASS | API and database operational; no active incidents |
| Login / refresh / logout | PASS | 200 / 200 / 204; post-logout `/auth/me` returned 401 |
| Organization and onboarding read | PASS | Owner membership and onboarding state returned correctly |
| SDK key lifecycle | PASS | Created, list hid secret/hash, revoked with 204 |
| Provider key lifecycle | PASS | Created, masked in list, deleted with 200 |
| Atomic ingestion | PASS | Post-migration events created unique usage IDs and exact counters |
| Budget/policy | PASS with configured block | Budget listed; policy returned an intentional blocked decision at the existing threshold |
| Alerts | PARTIAL | Rule/history reads passed; delivery job cannot be accepted because scheduler/channel configuration is absent |
| Dashboard reconciliation | PASS | API totals and database dry-run counters agree exactly |
| Timezone/date filters | PASS | UTC and Asia/Kolkata boundaries correct; `PST` rejected with 422 |
| Registration/email verification | BLOCKED | Email provider/domain not configured in production |
| Password-reset confirmation | BLOCKED | Requires a delivered reset token; email is not configured |
| Stripe checkout/webhook | BLOCKED | Stripe secret and webhook configuration absent |

## Bounded load profiles

The first post-migration 500/50 attempt used 1,400-token events and correctly reached the free-plan 1,000,000-token entitlement after 462 successes; 37 requests returned 402 and one Vercel invocation returned 500. The definitive concurrency run used zero-token synthetic usage events to avoid testing plan limits instead of ingestion capacity.

| Requests / concurrency | Success | Failure | Throughput | Mean | p50 | p95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 40 / 10 | 40 | 0 | 4.75 req/s | 2,029.57 ms | 1,966.60 ms | 2,269.11 ms | 2,627.93 ms |
| 100 / 20 | 100 | 0 | 9.32 req/s | 2,014.49 ms | 1,931.49 ms | 2,326.45 ms | 2,821.72 ms |
| 500 / 50 | 500 | 0 | 22.96 req/s | 2,031.08 ms | 1,980.19 ms | 2,429.44 ms | 2,794.12 ms |

All 640 final-run responses returned 201 and all 640 usage IDs were unique. The temporary SDK key was revoked after the run. Latency is consistently around two seconds and should be treated as a launch performance risk even though correctness and bounded throughput passed.

## Defect found and remediation

Root cause: `routers/onboarding.py` inserted onboarding test events directly into `usage_logs`, bypassing `ingest_usage_atomic` and recreating counter drift after reconciliation.

Fix: route onboarding test events through the same atomic ingestion RPC with the organization plan limits and preserve the onboarding progress/audit lifecycle. Added regression coverage that forbids direct onboarding writes to `usage_logs`. Local result: 49/49 backend tests passed.

Required activation: merge and deploy the draft PR, execute an onboarding test event in production, and verify dry-run reconciliation remains exact.

## Remaining launch blockers

1. Merge, deploy, and live-verify the onboarding atomic-ingestion fix.
2. Configure and verify production email provider/domain; complete registration verification and password-reset confirmation.
3. Configure Stripe production/test acceptance credentials and webhook; complete checkout, invoice, cancellation, and refund acceptance.
4. Configure the alert scheduler and a real delivery channel; verify deduplication and retry behavior.
5. Configure external monitoring and alerting.
6. Confirm Supabase backup/PITR entitlement and complete a restore rehearsal in an isolated project.
7. Review the current Supabase advisor backlog, especially legacy RLS initialization warnings and unindexed foreign keys.
8. Establish a latency SLO and investigate the approximately 2-second ingestion baseline before broad traffic acquisition.

## Final recommendation

**NO-GO.** Database integrity is repaired and the final bounded profiles pass, but one counter-integrity application fix is not yet deployed and multiple production integrations are unconfigured. Reassess for GO only after all required activation items above have evidence-backed passes.
