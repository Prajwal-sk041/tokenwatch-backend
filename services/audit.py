from typing import Any

from repositories.base import Repository


def record_audit(
    action: str,
    *,
    organization_id: str | None = None,
    actor_user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    Repository("audit_logs").insert({
        "action": action,
        "organization_id": organization_id,
        "actor_user_id": actor_user_id,
        "target_type": target_type,
        "target_id": target_id,
        "request_id": request_id,
        "metadata": metadata or {},
    })
