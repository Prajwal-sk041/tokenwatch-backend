"""Bounded Phase 5.6 ingestion acceptance harness. Never prints credentials."""
import argparse,json,statistics,time,uuid,threading
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests

def percentile(values,p): return sorted(values)[min(len(values)-1,int((len(values)-1)*p))]
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--base-url",required=True);parser.add_argument("--sdk-key",required=True)
    parser.add_argument("--requests",type=int,choices=(40,100,500),default=40);parser.add_argument("--concurrency",type=int,choices=(10,20,50),default=10)
    args=parser.parse_args(); run=f"phase56-{uuid.uuid4()}"; started=time.perf_counter()
    local=threading.local()
    def send(index):
        if not hasattr(local,"session"):
            local.session=requests.Session();local.session.headers.update({"X-TokenWatch-Key":args.sdk_key,"Content-Type":"application/json"})
        at=time.perf_counter(); response=local.session.post(f"{args.base_url.rstrip('/')}/v1/ingest/usage",json={"provider":"openai","model":"gpt-4o-mini","prompt_tokens":1000,"completion_tokens":400,"idempotency_key":f"{run}-{index}","project":run,"environment":"acceptance"},timeout=30)
        return response.status_code,(time.perf_counter()-at)*1000,response.json()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool: results=[future.result() for future in as_completed([pool.submit(send,i) for i in range(args.requests)])]
    latencies=[x[1] for x in results]; successes=sum(1 for x in results if x[0] in (200,201)); ids=[x[2].get("usage_id") for x in results if isinstance(x[2],dict)]
    report={"run":run,"requests":args.requests,"concurrency":args.concurrency,"successes":successes,"failures":args.requests-successes,
      "failure_rate":round((args.requests-successes)/args.requests,4),"unique_usage_ids":len(set(ids)),"elapsed_seconds":round(time.perf_counter()-started,3),
      "latency_ms":{"min":round(min(latencies),2),"mean":round(statistics.mean(latencies),2),"p50":round(percentile(latencies,.5),2),"p95":round(percentile(latencies,.95),2),"max":round(max(latencies),2)}}
    print(json.dumps(report,indent=2));raise SystemExit(0 if successes==args.requests and len(set(ids))==args.requests else 1)
if __name__=="__main__": main()
