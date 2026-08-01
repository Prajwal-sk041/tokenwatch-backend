from __future__ import annotations
from typing import Any, Literal, TypedDict
import httpx
Provider=Literal["openai","anthropic","gemini","groq","openrouter","azure_openai","aws_bedrock"]
class PolicyDecision(TypedDict):
    allowed:bool; blocked:bool; reason:str; remaining_budget:float|None; current_usage:float
class TokenWatchError(RuntimeError):
    def __init__(self,message:str,status:int,code:str|None=None):super().__init__(message);self.status=status;self.code=code
class TokenWatch:
    def __init__(self,api_key:str,base_url:str="https://tokenwatch-backend.vercel.app",timeout:float=10):
        if not api_key.startswith("tw_live_"): raise ValueError("A TokenWatch SDK key is required")
        self._client=httpx.Client(base_url=base_url.rstrip("/"),timeout=timeout,headers={"X-TokenWatch-Key":api_key})
    def _post(self,path:str,payload:dict[str,Any])->dict[str,Any]:
        response=self._client.post(path,json=payload)
        if response.is_error:
            detail=response.json().get("detail","TokenWatch request failed")
            code=detail.get("code") if isinstance(detail,dict) else None
            raise TokenWatchError(str(code or detail),response.status_code,code)
        return response.json()
    def check_policy(self,provider:Provider,model:str,**estimates:Any)->PolicyDecision:return self._post("/policy/check",{"provider":provider,"model":model,**estimates}) # type: ignore[return-value]
    def ingest(self,provider:Provider,model:str,prompt_tokens:int,completion_tokens:int,idempotency_key:str,**metadata:Any)->dict[str,Any]:return self._post("/v1/ingest/usage",{"provider":provider,"model":model,"prompt_tokens":prompt_tokens,"completion_tokens":completion_tokens,"idempotency_key":idempotency_key,**metadata})
    def close(self)->None:self._client.close()
    def __enter__(self)->"TokenWatch":return self
    def __exit__(self,*_:object)->None:self.close()
