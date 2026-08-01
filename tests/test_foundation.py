import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import main
from config import get_settings, load_settings
from routers import keys
from routers.auth import get_current_user
from schemas.requests import AlertCreate, UsageLog
from utils.auth import create_access_token, decode_token
from utils.encryption import decrypt_api_key, encrypt_api_key
from services.tenant import TenantContext


def test_configuration_validation_rejects_missing_required_values():
    with pytest.raises(ValidationError):
        load_settings({"CORS_ALLOWED_ORIGINS": "http://localhost:3000"})


def test_jwt_requires_configured_secret_and_round_trips():
    token = create_access_token({"sub": "user-1"})
    assert decode_token(token)["sub"] == "user-1"
    assert get_settings().jwt_secret not in token


def test_authentication_does_not_log_token_or_payload(caplog):
    token = create_access_token({"sub": "private-user", "email": "private@example.com"})
    with caplog.at_level(logging.DEBUG):
        decode_token(token)
    assert token not in caplog.text
    assert "private@example.com" not in caplog.text


def test_api_key_encryption_is_authenticated_and_not_plaintext():
    plaintext = "sk-example-secret-123456789"
    ciphertext = encrypt_api_key(plaintext)
    assert plaintext not in ciphertext
    assert decrypt_api_key(ciphertext) == plaintext


class FakeQuery:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.inserted = None
    def table(self, _): return self
    def insert(self, data): self.inserted = data; return self
    def select(self, *_args, **_kwargs): return self
    def eq(self, *_args): return self
    def is_(self, *_args): return self
    def limit(self, *_args): return self
    def order(self, *_args, **_kwargs): return self
    def execute(self):
        if self.inserted:
            return SimpleNamespace(data=[{"id": "key-1", **self.inserted}])
        return SimpleNamespace(data=self.rows)


def test_key_create_encrypts_storage_and_returns_only_mask(monkeypatch):
    db = FakeQuery()
    monkeypatch.setattr(keys, "get_db", lambda: db)
    monkeypatch.setattr(keys, "record_audit", lambda *args, **kwargs: None)
    response = keys.add_key(
        keys.AddKeyRequest(name="Primary", provider="openai", key_value="sk-example-secret-123456"),
        TenantContext("org-1", "user-1", "owner"),
    )
    assert "sk-example-secret" not in db.inserted["encrypted_key"]
    assert response["masked_key"].startswith("sk-e")
    assert "key_value" not in response and "encrypted_key" not in response


def test_key_list_masks_and_never_exposes_ciphertext(monkeypatch):
    ciphertext = encrypt_api_key("sk-example-secret-123456")
    row = {"id": "key-1", "name": "Primary", "provider": "openai", "is_active": True,
           "encrypted_key": ciphertext, "created_at": "2026-01-01T00:00:00Z"}
    monkeypatch.setattr(keys, "get_db", lambda: FakeQuery([row]))
    response = keys.list_keys(TenantContext("org-1", "user-1", "owner"))
    assert response[0]["masked_key"] == "sk-e••••3456"
    assert "encrypted_key" not in response[0]


@pytest.mark.parametrize("threshold", [0, -1])
def test_invalid_alert_thresholds(threshold):
    with pytest.raises(ValidationError):
        AlertCreate(alert_type="cost", threshold=threshold)


@pytest.mark.parametrize("payload", [
    {"provider": "openai", "model": "gpt-5", "prompt_tokens": -1},
    {"provider": "unknown", "model": "gpt-5"},
    {"provider": "openai", "model": "gpt-5", "cost": -0.1},
])
def test_invalid_usage_payloads(payload):
    with pytest.raises(ValidationError):
        UsageLog(**payload)


def test_protected_route_rejects_missing_authentication():
    response = TestClient(main.app).get("/keys/list")
    assert response.status_code in {401, 403}


def test_health_endpoints(monkeypatch):
    client = TestClient(main.app)
    assert client.get("/health/live").json() == {"status": "ok"}
    monkeypatch.setattr(main, "check_database_connection", lambda: True)
    assert client.get("/health/ready").json() == {"status": "ready"}
    monkeypatch.setattr(main, "check_database_connection", lambda: False)
    assert client.get("/health/ready").status_code == 503


def test_scheduler_is_disabled_by_default():
    settings = load_settings({
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_KEY": "audit-service-key-placeholder",
        "JWT_SECRET": "audit-jwt-secret-with-at-least-32-characters",
        "API_KEY_ENCRYPTION_KEY": get_settings().api_key_encryption_key,
    })
    assert settings.alert_scheduler_enabled is False
