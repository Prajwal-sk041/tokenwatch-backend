from pathlib import Path

from utils.email import responsive_email


def test_responsive_email_escapes_content_and_has_mobile_viewport():
    html = responsive_email("Hello <script>", "Safe & useful", "https://example.com/action", "Continue")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert 'name="viewport"' in html
    assert 'role="presentation"' in html


def test_phase5_migration_hardens_indexes_rls_and_rate_limits():
    sql = Path("migrations/202608010005_phase5_launch.sql").read_text(encoding="utf-8")
    for token in ("invoices_subscription_idx", "email_deliveries_user_idx", "enable row level security", "consume_rate_limit"):
        assert token in sql
    assert "revoke all on function private.consume_rate_limit" in sql


def test_phase55_rate_limit_rpc_is_exposed_only_to_service_role():
    sql = Path("migrations/202608010006_phase55_rate_limit_rpc.sql").read_text(encoding="utf-8")
    assert "function public.consume_rate_limit" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "drop function if exists private.consume_rate_limit" in sql


def test_official_sdks_use_sdk_key_header_not_login_jwt():
    node = Path("sdks/node/src/index.ts").read_text(encoding="utf-8")
    python = Path("sdks/python/src/tokenwatch/client.py").read_text(encoding="utf-8")
    for source in (node, python):
        assert "tw_live_" in source
    assert "x-tokenwatch-key" in node.lower()
    assert "X-TokenWatch-Key" in python


def test_ci_has_approval_gated_release_and_audits():
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "pip-audit" in ci
    assert "environment: production" in release
    assert "concurrency" in release
