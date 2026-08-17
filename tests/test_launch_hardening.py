from pathlib import Path

from services.pricing import calculate_cost, pricing_catalog


ROOT = Path(__file__).parents[1]


def test_pricing_catalog_is_the_same_catalog_used_for_calculation():
    catalog = pricing_catalog()
    row = next(item for item in catalog["models"] if item["provider"] == "openai" and item["model"] == "gpt-4o-mini")
    assert catalog["currency"] == "USD"
    assert catalog["effective_date"] == "2026-08-18"
    assert row["input_per_1m_tokens"] == "0.15"
    assert row["source_url"].startswith("https://")
    assert str(calculate_cost("openai", "gpt-4o-mini", 1_000_000, 0)) == row["input_per_1m_tokens"]


def test_policy_history_is_tenant_scoped_and_bounded():
    source = (ROOT / "routers" / "policy.py").read_text()
    section = source.split('def policy_history', 1)[1].split('@router.get("/check")', 1)[0]
    assert '.eq("organization_id", tenant.organization_id)' in section
    assert 'le=100' in section


def test_account_export_explicitly_excludes_sensitive_columns():
    source = (ROOT / "routers" / "auth.py").read_text()
    section = source.split('def export_account', 1)[1].split('def get_current_user', 1)[0]
    assert "hashed_password" not in section
    assert "key_value" not in section
    assert "refresh_token_hash" not in section


def test_policy_decision_ledger_has_rls_and_no_client_grants():
    migration = (ROOT / "migrations" / "202608180002_launch_hardening.sql").read_text()
    assert "enable row level security" in migration
    assert "revoke all on table public.policy_decisions from anon, authenticated" in migration


def test_member_api_returns_human_readable_identity_without_secrets():
    source = (ROOT / "routers" / "organizations.py").read_text()
    section = source.split("def list_members", 1)[1].split('@router.patch', 1)[0]
    assert 'select("email,full_name")' in section
    assert 'member["display_name"]' in section
    assert 'member["email"]' in section
    assert "hashed_password" not in section
