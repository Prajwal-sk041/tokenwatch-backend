# tokenwatch

Official typed Python SDK. Use a TokenWatch SDK key, never a login token.

```python
import os, uuid
from tokenwatch import TokenWatch
with TokenWatch(os.environ["TOKENWATCH_API_KEY"]) as tw:
    decision=tw.check_policy("openai","gpt-4o-mini",estimated_prompt_tokens=500)
    if decision["allowed"]:
        tw.ingest("openai","gpt-4o-mini",400,100,str(uuid.uuid4()))
```
