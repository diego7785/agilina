"""The worker settings: a secret per tenant, a folder for pending results, and no database."""

from pathlib import Path

import pytest

from agilina_agent.infrastructure.settings import DEFAULT_PENDING_DIR, Settings


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_the_worker_secret_of_a_tenant_is_read_from_its_own_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGILINA_TENANT_ACME_KEYCLOAK_WORKER_SECRET", "acme-secret")
    monkeypatch.setenv("AGILINA_TENANT_ECOMODA_KEYCLOAK_WORKER_SECRET", "ecomoda-secret")

    settings = _settings()

    assert settings.worker_secret("acme").get_secret_value() == "acme-secret"
    assert settings.worker_secret("ecomoda").get_secret_value() == "ecomoda-secret"
    assert "acme-secret" not in repr(settings.worker_secret("acme"))


def test_a_tenant_without_a_secret_has_an_empty_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGILINA_TENANT_INITECH_KEYCLOAK_WORKER_SECRET", raising=False)

    assert _settings().worker_secret("initech").get_secret_value() == ""


@pytest.mark.parametrize("value", [None, ""])
def test_the_pending_folder_defaults_to_the_repository_data_folder(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("AGILINA_AGENT_PENDING_DIR", raising=False)
    else:
        monkeypatch.setenv("AGILINA_AGENT_PENDING_DIR", value)

    assert _settings().agent_pending_dir == DEFAULT_PENDING_DIR
    assert DEFAULT_PENDING_DIR.parts[-3:] == ("infra", "datos", "agent-pending")


def test_the_pending_folder_can_be_moved(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGILINA_AGENT_PENDING_DIR", str(tmp_path))

    assert _settings().agent_pending_dir == tmp_path


def test_the_worker_has_no_database_setting() -> None:
    assert not [name for name in Settings.model_fields if "database" in name or "db" in name]
