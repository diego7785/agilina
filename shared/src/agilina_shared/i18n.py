"""Catalog of Agilina's texts in the two languages of the product.

Every spoken intervention of Agilina comes from templates parameterized by
language, not from the language model (AD-19). This module is the only place
where those texts live, so that adding a language means adding a column
instead of hunting for strings across the code.
"""

from agilina_shared.enums import Language

TEMPLATES: dict[str, dict[Language, str]] = {
    "greeting": {
        Language.ES: "Hola, soy Agilina. Estamos en el día {day} de {total} del sprint. "
        "Empecemos la reunión diaria.",
        Language.EN: "Hi, I'm Agilina. We're on day {day} of {total} of the sprint. "
        "Let's start the daily stand-up.",
    },
    "standby_greeting": {
        Language.ES: "Hola, soy Agilina. Estamos en el día {day} de {total} del sprint. "
        "Cuando estén listos, pulsen «Iniciar reunión diaria».",
        Language.EN: "Hi, I'm Agilina. We're on day {day} of {total} of the sprint. "
        "When you're ready, press “Start the daily stand-up”.",
    },
    "hand_over_turn": {
        Language.ES: "{name}, es tu turno.",
        Language.EN: "{name}, it's your turn.",
    },
    "silence": {
        Language.ES: "{name}, ¿sigues ahí?",
        Language.EN: "{name}, are you still there?",
    },
    "stuck_turn": {
        Language.ES: "{name}, ¿quieres cerrar tu turno?",
        Language.EN: "{name}, would you like to wrap up your turn?",
    },
    "farewell": {
        Language.ES: "Con eso cerramos la reunión diaria. Que tengan buen día.",
        Language.EN: "That wraps up the daily stand-up. Have a good day.",
    },
    "degraded": {
        Language.ES: "No puedo escuchar en este momento: el servicio de transcripción no "
        "responde. Continúen sin mí y yo aviso cuando vuelva.",
        Language.EN: "I can't listen right now: the transcription service isn't responding. "
        "Please carry on without me and I'll let you know when I'm back.",
    },
    "context_unavailable": {
        Language.ES: "No pude obtener los datos de esta reunión, así que no voy a facilitarla. "
        "Pueden continuar sin mí.",
        Language.EN: "I couldn't get the details of this meeting, so I won't be facilitating it. "
        "Please carry on without me.",
    },
}


def render_text(key: str, language: Language, **params: object) -> str:
    """Return the template ``key`` in ``language`` with its parameters resolved.

    Fails loudly on a missing key or a missing parameter: a half-resolved text
    would reach the room turned into speech.
    """
    try:
        template = TEMPLATES[key][language]
    except KeyError as error:
        raise KeyError(f"No template '{key}' for language '{language}'") from error
    return template.format(**params)


def incomplete_keys() -> list[str]:
    """Keys that do not exist in both languages.

    The test that uses this function is what makes the Definition of Done
    criterion verifiable: every user-facing text exists in Spanish and English.
    """
    return [key for key, translations in TEMPLATES.items() if set(translations) != set(Language)]
