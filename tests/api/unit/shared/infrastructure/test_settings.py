"""Which server delivers the email is only configuration (AD-23)."""

import pytest

from agilina_api.shared.infrastructure.settings import Settings


def test_the_defaults_point_to_mailpit():
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert (settings.smtp_host, settings.smtp_port) == ("mailpit", 1025)
    assert settings.smtp_security == "none"
    assert settings.smtp_user == ""


def test_the_environment_can_point_to_a_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGILINA_SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
    monkeypatch.setenv("AGILINA_SMTP_PORT", "587")
    monkeypatch.setenv("AGILINA_SMTP_USER", "AKIA-EXAMPLE")
    monkeypatch.setenv("AGILINA_SMTP_PASSWORD", "top-secret")
    monkeypatch.setenv("AGILINA_SMTP_SECURITY", "starttls")
    monkeypatch.setenv("AGILINA_MAIL_FROM", "Agilina <verified@example.test>")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.smtp_host == "email-smtp.us-east-1.amazonaws.com"
    assert settings.smtp_port == 587
    assert settings.smtp_security == "starttls"
    assert settings.smtp_password.get_secret_value() == "top-secret"
    assert settings.mail_from == "Agilina <verified@example.test>"


def test_the_smtp_password_never_shows_in_the_representation():
    settings = Settings(_env_file=None, smtp_password="top-secret")  # type: ignore[call-arg, arg-type]

    assert "top-secret" not in repr(settings)
    assert "top-secret" not in str(settings)


def test_an_unknown_security_mode_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGILINA_SMTP_SECURITY", "maybe")

    with pytest.raises(ValueError):  # noqa: PT011 - pydantic's ValidationError is a ValueError
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_the_livekit_secret_is_read_from_the_environment_and_never_shown(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AGILINA_LIVEKIT_API_SECRET", "livekit-top-secret")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.livekit_api_secret.get_secret_value() == "livekit-top-secret"
    assert "livekit-top-secret" not in repr(settings)
    assert "livekit-top-secret" not in str(settings)


def test_without_the_variable_the_livekit_secret_is_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGILINA_LIVEKIT_API_SECRET", raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.livekit_api_secret.get_secret_value() == ""
