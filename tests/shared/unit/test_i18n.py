"""The Definition of Done requires every user-facing text to exist in both
languages. This test is what makes that criterion verifiable."""

import pytest

from agilina_shared.enums import Language
from agilina_shared.i18n import TEMPLATES, incomplete_keys, render_text


def test_no_template_is_left_untranslated():
    assert incomplete_keys() == []


@pytest.mark.parametrize("language", list(Language))
def test_greeting_includes_the_sprint_day_in_both_languages(language: Language):
    result = render_text("greeting", language, day=3, total=15)
    assert "3" in result
    assert "15" in result


@pytest.mark.parametrize(
    ("language", "start_button"),
    [(Language.ES, "«Iniciar reunión diaria»"), (Language.EN, "“Start the daily stand-up”")],
)
def test_standby_greeting_names_the_sprint_day_and_the_start_button(
    language: Language, start_button: str
):
    result = render_text("standby_greeting", language, day=3, total=15)
    assert "3" in result
    assert "15" in result
    assert start_button in result


def test_the_spanish_standby_greeting_does_not_leak_english():
    result = render_text("standby_greeting", Language.ES, day=3, total=15)
    assert "reunión diaria" in result
    assert "daily" not in result.lower()


def test_a_missing_key_fails_instead_of_returning_empty():
    with pytest.raises(KeyError):
        render_text("missing_key", Language.ES)


def test_every_template_resolves_its_parameters():
    params = {"day": 1, "total": 15, "name": "Angélica"}
    for key, translations in TEMPLATES.items():
        for language in translations:
            assert render_text(key, language, **params)
