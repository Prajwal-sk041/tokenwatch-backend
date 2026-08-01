# TokenWatch API

Interactive OpenAPI documentation is served at `/docs`; the machine-readable schema is `/openapi.json`.

## Authentication

Dashboard endpoints use secure session cookies. SDK endpoints use `X-TokenWatch-Key: tw_live_...`. Never send login JWTs from an SDK. All organization resources enforce membership server-side.

## Policy check

`POST /policy/check`

```json
{"provider":"openai","model":"gpt-4o-mini","estimated_prompt_tokens":500,"estimated_completion_tokens":200}
```

## Usage ingestion

`POST /v1/ingest/usage` requires a unique `idempotency_key`, a recent timestamp, and a key with `usage:write`. Cost is calculated server-side.

```bash
curl -X POST https://tokenwatch-backend.vercel.app/v1/ingest/usage \
  -H "X-TokenWatch-Key: $TOKENWATCH_API_KEY" -H "Content-Type: application/json" \
  -d '{"provider":"openai","model":"gpt-4o-mini","prompt_tokens":400,"completion_tokens":100,"idempotency_key":"request-12345678"}'
```

```js
await tokenwatch.ingest({provider:"openai",model:"gpt-4o-mini",prompt_tokens:400,completion_tokens:100,idempotency_key:crypto.randomUUID()});
```

```python
tw.ingest("openai", "gpt-4o-mini", 400, 100, str(uuid.uuid4()))
```

## Errors

- `400` malformed or replayed request
- `401` missing, expired, or revoked credentials
- `403` missing permission or organization role
- `402` usage entitlement reached
- `409` resource plan limit or conflicting subscription state
- `422` validation or unsupported pricing model
- `429` rate limit reached; honor `Retry-After`
- `503` required billing/email/database integration unavailable

Errors use `{"detail":"message"}` or `{"detail":{"code":"machine_code","feature":"name","limit":5}}`.

## Pagination and limits

List endpoints use `page` and `page_size` (maximum 100), returning `items`, `page`, `page_size`, and `has_more` or `total`. Default API limits are documented per endpoint in OpenAPI. SDK ingestion additionally enforces organization plan limits.
