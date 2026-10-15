"""System prompt loading and the user message: team context block, then the transcript.

The two blocks are separated by delimiters (both travel in the user message): the context
is trusted configuration and the transcript is untrusted data. The input guards only ever
see the transcript, so the context is never redacted.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from purple_team.core.text import sha256_hex
from purple_team.errors import ConfigError
from purple_team.team_context import TeamContext

TEAM_CONTEXT_OPEN: Final = "<contexto_equipo>"
TEAM_CONTEXT_CLOSE: Final = "</contexto_equipo>"
TRANSCRIPT_OPEN: Final = "<transcripcion>"
TRANSCRIPT_CLOSE: Final = "</transcripcion>"
CLOSING_REQUEST: Final = "Genera ahora el JSON de cierre de la ceremonia."


@dataclass(frozen=True, slots=True)
class SystemPrompt:
    """System prompt text with its hash, written to every run record."""

    text: str
    sha256: str
    source: Path


def load_system_prompt(path: Path) -> SystemPrompt:
    """Read the system prompt; raise ``ConfigError`` when it is missing or empty."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"No se pudo leer el prompt de sistema {path}") from exc
    if not text.strip():
        raise ConfigError(f"El prompt de sistema {path} está vacío")
    return SystemPrompt(text=text, sha256=sha256_hex(text), source=path)


def build_user_content(transcript: str, team_context: TeamContext) -> str:
    """Context block (trusted configuration) first, then the transcript (untrusted data).

    The wrapping is the same in every defense mode, so the only difference between modes
    is what the guards do.
    """
    body = transcript.rstrip("\n")
    return "\n".join(
        (
            TEAM_CONTEXT_OPEN,
            team_context.render_for_model(),
            TEAM_CONTEXT_CLOSE,
            "",
            TRANSCRIPT_OPEN,
            body,
            TRANSCRIPT_CLOSE,
            "",
            CLOSING_REQUEST,
        )
    )
