# TokenWatch SDK Guide

TokenWatch SDK traffic uses ingestion keys, never user login tokens or provider credentials.

Create an SDK key through the authenticated `/sdk-keys/{organization_id}` endpoint. Store the returned `tw_live_...` value in the workload's secret manager; it is shown once. Send it as `X-TokenWatch-Key`.

Before a provider call, request:

```http
GET /policy/check?provider=openai&model=gpt-4o-mini&estimated_prompt_tokens=1000&estimated_completion_tokens=500
X-TokenWatch-Key: tw_live_...
```

Honor `blocked: true` by stopping the provider call. After a completed provider call, submit:

```http
POST /v1/ingest/usage
X-TokenWatch-Key: tw_live_...
Content-Type: application/json

{
  "idempotency_key": "request-unique-id",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "prompt_tokens": 1000,
  "completion_tokens": 500,
  "project": "checkout",
  "environment": "production",
  "timestamp": "2026-08-01T12:00:00Z"
}
```

Retry with the same idempotency key after network uncertainty. TokenWatch returns the original usage ID and does not double-count. Rotate keys periodically; rotation immediately revokes the previous key. Use only the required `usage:write` and `policy:check` permissions.
