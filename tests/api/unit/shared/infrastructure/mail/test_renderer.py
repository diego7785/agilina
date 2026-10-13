"""Emails are rendered from templates, never written inside the code."""

import pytest
from jinja2 import UndefinedError

from agilina_api.bootstrap.send_test_email import build_test_email
from agilina_api.shared.infrastructure.mail.renderer import TEMPLATES_DIR, JinjaEmailRenderer
from agilina_api.shared.infrastructure.mail.texts import LAYOUT, TEMPLATES
from agilina_api.shared.infrastructure.mail.theme import LIGHT
from agilina_api.shared.infrastructure.settings import Settings
from agilina_shared.enums import Language

PARAMS = {
    "server": "mailpit:1025",
    "security": "none",
    "sender": "Agilina <no-reply@agilina.local>",
}


def _render(language: Language = Language.ES, **overrides: object):
    return JinjaEmailRenderer().render("test", language, **{**PARAMS, **overrides})


def test_the_html_is_a_complete_document_in_the_requested_language():
    html = _render(Language.ES).html_body

    assert html.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="es">' in html
    assert "El correo funciona" in html
    assert '<html lang="en">' in _render(Language.EN).html_body


def test_each_language_gets_its_own_subject_and_texts():
    spanish, english = _render(Language.ES), _render(Language.EN)

    assert spanish.subject == "Agilina: prueba de correo"
    assert english.subject == "Agilina: email test"
    assert "Servidor" in spanish.html_body and "Server" in english.html_body


def test_the_values_are_shown_in_both_the_html_and_the_text_versions():
    rendered = _render()

    for version in (rendered.html_body, rendered.text_body):
        assert "mailpit:1025" in version


def test_the_text_version_is_plain_text_without_markup():
    text = _render(sender="Agilina <no-reply@agilina.local>").text_body

    assert "<html" not in text and "<table" not in text
    assert "Agilina <no-reply@agilina.local>" in text  # not escaped: it is not HTML


def test_the_security_mode_is_shown_as_a_readable_label_in_each_language():
    assert "Sin cifrar" in _render(Language.ES, security="none").html_body
    assert "Cifrado con STARTTLS" in _render(Language.ES, security="starttls").text_body
    assert "Encrypted with TLS" in _render(Language.EN, security="tls").html_body


def test_html_values_are_escaped_so_they_cannot_inject_markup():
    html = _render(sender='<script>alert("x")</script>', server="a&b").html_body

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a&amp;b" in html


def test_a_missing_parameter_fails_instead_of_rendering_a_half_empty_email():
    with pytest.raises(UndefinedError):
        JinjaEmailRenderer().render("test", Language.ES, server="x", security="none")


def test_an_unknown_template_fails_with_a_clear_error():
    with pytest.raises(KeyError, match="nope"):
        JinjaEmailRenderer().render("nope", Language.ES)


def test_the_design_does_not_depend_on_remote_resources():
    """Clients block remote images and stylesheets by default: the email must stand alone."""
    html = _render().html_body.lower()

    assert "<img" not in html and "<link" not in html and "@import" not in html


def test_every_template_exists_in_both_languages_with_the_same_texts():
    for name, translations in TEMPLATES.items():
        assert set(translations) == set(Language), name
        assert translations[Language.ES].keys() == translations[Language.EN].keys(), name
    assert LAYOUT[Language.ES].keys() == LAYOUT[Language.EN].keys()


def test_the_tagline_says_reunion_diaria_in_spanish_and_keeps_the_daily_stand_up_in_english():
    assert LAYOUT[Language.ES]["tagline"] == "Tu Scrum Master virtual para la reunión diaria"
    assert LAYOUT[Language.EN]["tagline"] == "Your virtual Scrum Master for the Daily Stand-up"
    assert "stand-up" not in LAYOUT[Language.ES]["tagline"].lower()


def test_no_spanish_email_calls_the_meeting_only_daily():
    spanish = [
        text
        for texts in [LAYOUT, *TEMPLATES.values()]
        for language, values in texts.items()
        if language is Language.ES
        for text in values.values()
    ]

    assert all("la daily" not in text.lower() for text in spanish)
    assert any("reunión diaria" in text for text in spanish)


def test_every_template_has_an_html_and_a_text_file():
    for name in TEMPLATES:
        assert (TEMPLATES_DIR / f"{name}.html").is_file(), name
        assert (TEMPLATES_DIR / f"{name}.txt").is_file(), name


def test_the_test_email_is_built_from_the_settings_and_addressed_to_the_recipient():
    settings = Settings(_env_file=None, smtp_host="smtp.example.test", smtp_port=587)  # type: ignore[call-arg]

    message = build_test_email(settings, "julian@example.test", Language.EN)

    assert message.to == "julian@example.test"
    assert message.subject == "Agilina: email test"
    assert message.html_body and "smtp.example.test:587" in message.html_body
    assert "smtp.example.test:587" in message.text_body


LIGHT_PRIMARY = LIGHT["primary"]

# ------------------------------------------------------------ invitation email --
INVITATION = {
    "name": "Julián Torres",
    "team_name": "Atlas",
    "inviter_name": "Diego",
    "activation_url": "https://app.example.test/activate#t=" + "T" * 43,
    "expires_on": "2026-10-11",
}


def _invitation(language: Language = Language.ES, **overrides: object):
    return JinjaEmailRenderer().render("invitation", language, **{**INVITATION, **overrides})


def test_the_invitation_subject_and_greeting_use_the_name_and_the_team():
    spanish, english = _invitation(Language.ES), _invitation(Language.EN)

    assert spanish.subject == "Te invitaron a Atlas en Agilina"
    assert english.subject == "You were invited to Atlas on Agilina"
    assert "Hola Julián Torres," in spanish.text_body and "Hi Julián Torres," in english.text_body


def test_the_invitation_has_a_button_and_a_plain_link_to_the_same_address():
    email = _invitation()

    # the button's href, the fallback link's href and the fallback link's visible text
    assert email.html_body.count(INVITATION["activation_url"]) == 3
    assert 'href="' + INVITATION["activation_url"] + '"' in email.html_body
    assert "Activar mi cuenta" in email.html_body
    assert INVITATION["activation_url"] in email.text_body


def test_the_invitation_says_who_invited_when_it_is_known_and_stays_neutral_when_not():
    assert "Diego te invitó" in _invitation().text_body
    anonymous = _invitation(inviter_name="")
    assert "Te invitaron a unirte al equipo Atlas" in anonymous.text_body
    assert "te invitó" not in anonymous.text_body


def test_the_invitation_states_the_expiry_in_both_languages():
    assert "vence el 2026-10-11" in _invitation(Language.ES).text_body
    assert "expires on 2026-10-11" in _invitation(Language.EN).text_body


def test_a_name_or_team_cannot_inject_markup_into_the_invitation():
    html = _invitation(name='<img src=x onerror="alert(1)">', team_name="<b>Atlas</b>").html_body

    assert "<img" not in html and "<b>Atlas" not in html
    assert "&lt;img" in html and "&lt;b&gt;Atlas" in html


def test_the_invitation_button_follows_the_dark_theme_too():
    html = _invitation().html_body

    assert LIGHT_PRIMARY in html  # the button fill
    assert ".btn { background-color: " in html and "prefers-color-scheme: dark" in html


def test_the_request_for_a_new_invitation_explains_the_reason_in_each_language():
    def render(language, reason):
        return JinjaEmailRenderer().render(
            "new_invitation_request",
            language,
            admin_name="Diego",
            requester_name="Julián",
            requester_email="julian@example.test",
            team_name="Atlas",
            reason=reason,
        )

    assert "venció" in render(Language.ES, "expired").text_body
    assert "ya se había usado" in render(Language.ES, "accepted").text_body
    assert "had already been used" in render(Language.EN, "accepted").text_body
    assert "Hola Diego," in render(Language.ES, "expired").text_body
    assert "julian@example.test" in render(Language.ES, "expired").html_body
    assert render(Language.EN, "expired").subject == "Julián needs a new invitation to Atlas"


# -------------------------------------------------- member added notice (HU-06) --
MEMBER_ADDED = {
    "name": "Julián Torres",
    "team_name": "Atlas",
    "inviter_name": "Diego",
    "team_url": "https://app.example.test/teams/0000-atlas",
}


def _member_added(language: Language = Language.ES, **overrides: object):
    return JinjaEmailRenderer().render("member_added", language, **{**MEMBER_ADDED, **overrides})


def test_the_member_added_notice_names_the_person_and_the_team_in_each_language():
    spanish, english = _member_added(Language.ES), _member_added(Language.EN)

    assert spanish.subject == "Ahora formas parte de Atlas en Agilina"
    assert english.subject == "You are now part of Atlas on Agilina"
    assert "Hola Julián Torres," in spanish.text_body and "Hi Julián Torres," in english.text_body
    assert '<html lang="es">' in spanish.html_body and '<html lang="en">' in english.html_body


def test_the_member_added_notice_links_to_the_team_and_never_to_an_activation():
    for email in (_member_added(Language.ES), _member_added(Language.EN)):
        assert 'href="' + MEMBER_ADDED["team_url"] + '"' in email.html_body
        assert MEMBER_ADDED["team_url"] in email.text_body
        for version in (email.html_body, email.text_body):
            assert "/activate" not in version and "#t=" not in version
    assert "Abrir el equipo" in _member_added(Language.ES).html_body
    assert "Open the team" in _member_added(Language.EN).html_body


def test_the_member_added_notice_says_who_added_them_when_it_is_known():
    assert "Diego te agregó al equipo Atlas" in _member_added().text_body
    anonymous = _member_added(inviter_name="")
    assert "Te agregaron al equipo Atlas" in anonymous.text_body
    assert "te agregó" not in anonymous.text_body
    assert "Diego added you to the Atlas team" in _member_added(Language.EN).text_body


def test_the_member_added_notice_says_there_is_nothing_to_activate():
    assert "no hace falta activar nada" in _member_added(Language.ES).text_body
    assert "there is nothing to activate" in _member_added(Language.EN).html_body


def test_a_name_or_team_cannot_inject_markup_into_the_member_added_notice():
    html = _member_added(name="<i>Julián</i>", team_name="<b>Atlas</b>").html_body

    assert "<i>Julián" not in html and "<b>Atlas" not in html
    assert "&lt;i&gt;Julián" in html and "&lt;b&gt;Atlas" in html


def test_the_member_added_notice_does_not_depend_on_remote_resources():
    html = _member_added().html_body.lower()

    assert "<img" not in html and "<link" not in html and "@import" not in html


def test_the_member_added_notice_needs_the_team_link():
    params = {key: value for key, value in MEMBER_ADDED.items() if key != "team_url"}

    with pytest.raises(UndefinedError):
        JinjaEmailRenderer().render("member_added", Language.ES, **params)


def test_the_invitation_still_carries_its_activation_link():
    """Regression: HU-06 reuses the HU-02 invitation, whose link opens /activate."""
    email = _invitation(Language.EN)

    assert "/activate#t=" in email.text_body and "/activate#t=" in email.html_body
