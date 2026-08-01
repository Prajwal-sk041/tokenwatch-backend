import hashlib

from fastapi import HTTPException, Request

from utils.database import get_db


def consume(request: Request, scope: str, limit: int, window_seconds: int) -> None:
    forwarded = request.headers.get("x-forwarded-for", "")
    source = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown")
    digest = hashlib.sha256(f"{scope}:{source}".encode()).hexdigest()
    rows = get_db().rpc("consume_rate_limit", {"p_key": digest, "p_window_seconds": window_seconds, "p_limit": limit}).execute().data
    allowed = rows if isinstance(rows, bool) else bool(rows and rows[0])
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(window_seconds)})
