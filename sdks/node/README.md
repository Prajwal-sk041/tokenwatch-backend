# @tokenwatch/sdk

Official typed Node.js SDK. Requires Node 18+ and a TokenWatch SDK key, never a login JWT.

```ts
import {TokenWatch} from "@tokenwatch/sdk";
const tokenwatch=new TokenWatch({apiKey:process.env.TOKENWATCH_API_KEY!});
const decision=await tokenwatch.checkPolicy({provider:"openai",model:"gpt-4o-mini",estimated_prompt_tokens:500});
if(decision.allowed) await tokenwatch.ingest({provider:"openai",model:"gpt-4o-mini",prompt_tokens:400,completion_tokens:100,idempotency_key:crypto.randomUUID()});
```

Keys stay server-side. Use a unique idempotency key per provider request. Errors are `TokenWatchError` with HTTP status and machine-readable code.
