from typing import Any

from utils.database import get_db


class Repository:
    def __init__(self, table: str):
        self.table = table

    @property
    def query(self):
        return get_db().table(self.table)

    def insert(self, values: dict[str, Any]) -> dict[str, Any]:
        result = self.query.insert(values).execute().data or []
        if not result:
            raise RuntimeError(f"{self.table} insert returned no row")
        return result[0]

    def by_id_for_organization(self, record_id: str, organization_id: str) -> dict[str, Any] | None:
        rows = self.query.select("*").eq("id", record_id).eq("organization_id", organization_id).limit(1).execute().data or []
        return rows[0] if rows else None
