"""Optional input detector based on LLM Guard's prompt-injection scanner.

LLM Guard is NOT a dependency of the harness: it is imported lazily (``importlib``) only
when a run asks for ``llm-guard`` or ``own-llm-guard``, from the harness' own virtualenv
(``purple_team/.venv``). When it is missing, ``DefenseUnavailableError`` explains how to
install it and the CLI exits with code 4 before writing anything.

Each utterance (the line without its ``[hh:mm:ss] Name:`` prefix) is scanned on its own, so
the unit of decision is the same as for the regex rules: a flagged line is redacted, never
the whole transcript. The first scan downloads the model from huggingface.co to the local
Hugging Face cache (about 750 MB).
"""

import importlib
import importlib.metadata
import sys
from types import ModuleType
from typing import Final, Protocol

from purple_team.config import LlmGuardSettings
from purple_team.defense.models import EXCERPT_MAX_CHARS, Detection, split_speaker
from purple_team.errors import DefenseUnavailableError

LLM_GUARD_DETECTOR_ID: Final = "llm_guard"
LLM_GUARD_RULE_ID: Final = "llm_guard_prompt_injection"
LLM_GUARD_PACKAGE: Final = "llm-guard"  # distribution name, for importlib.metadata
LLM_GUARD_PINNED_VERSION: Final = "0.3.16"
LLM_GUARD_MODEL: Final = "protectai/deberta-v3-base-prompt-injection-v2"  # informative
SCANNER_MODULE: Final = "llm_guard.input_scanners.prompt_injection"
UTIL_MODULE: Final = "llm_guard.util"
LOG_LEVEL: Final = "ERROR"


class PromptInjectionScanner(Protocol):
    """The part of ``llm_guard.input_scanners.PromptInjection`` the detector uses."""

    def scan(self, prompt: str) -> tuple[str, bool, float]:
        """Return the (unchanged) prompt, whether it is valid and its risk score."""


def _import_module(name: str) -> ModuleType:
    """Module-level wrapper so the tests can fake the import without touching importlib."""
    return importlib.import_module(name)


def missing_message() -> str:
    """Spanish instructions shown when LLM Guard is not installed in this interpreter."""
    return (
        f"LLM Guard no está instalado en este intérprete ({sys.executable}). Los modos off y "
        "own no lo necesitan. Para instalarlo en el entorno propio del banco:\n"
        "  python3 -m venv purple_team/.venv\n"
        f'  purple_team/.venv/bin/python -m pip install "{LLM_GUARD_PACKAGE}=='
        f'{LLM_GUARD_PINNED_VERSION}"\n'
        "y ejecuta el banco con: purple_team/.venv/bin/python -m purple_team run "
        "--defense llm-guard\n"
        "No se ejecutó ninguna corrida (tampoco las de otros modos pedidos). Para medir solo "
        "los modos disponibles, repite con: --defense off,own"
    )


def load_prompt_injection_scanner(settings: LlmGuardSettings) -> PromptInjectionScanner:
    """Import LLM Guard and build its scanner; ``DefenseUnavailableError`` if impossible."""
    try:
        util = _import_module(UTIL_MODULE)
        module = _import_module(SCANNER_MODULE)
    except ImportError as exc:
        raise DefenseUnavailableError(missing_message()) from exc
    # structlog would otherwise write INFO lines to stdout, mixed with the CLI output.
    util.configure_logger(log_level=LOG_LEVEL, stream=sys.stderr)
    try:
        match_type = module.MatchType(settings.match_type.value)
        scanner: PromptInjectionScanner = module.PromptInjection(
            threshold=settings.threshold,
            match_type=match_type,
            use_onnx=False,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        message = (
            "No se pudo cargar el modelo de LLM Guard (descarga desde huggingface.co o "
            f"caché): {exc}"
        )
        raise DefenseUnavailableError(message) from exc
    return scanner


def llm_guard_version() -> str | None:
    """Installed version of the ``llm-guard`` distribution, or ``None`` when it is missing."""
    try:
        return importlib.metadata.version(LLM_GUARD_PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return None


class LlmGuardDetector:
    """``LineDetector`` that asks LLM Guard about each utterance."""

    def __init__(
        self,
        scanner: PromptInjectionScanner,
        settings: LlmGuardSettings,
        package_version: str | None,
    ) -> None:
        self._scanner = scanner
        self._settings = settings
        self._package_version = package_version

    @property
    def detector_id(self) -> str:
        """``llm_guard``."""
        return LLM_GUARD_DETECTOR_ID

    def detect(self, line_number: int, line: str) -> tuple[Detection, ...]:
        """Scan the utterance without its speaker prefix; empty utterances are not scanned."""
        _prefix, utterance = split_speaker(line)
        if not utterance.strip():
            return ()
        _prompt, is_valid, risk_score = self._scanner.scan(utterance)
        if is_valid:
            return ()
        excerpt = utterance[:EXCERPT_MAX_CHARS]
        return (Detection(line_number, LLM_GUARD_RULE_ID, excerpt, score=risk_score),)

    def describe(self) -> dict[str, object]:
        """Package version, model and scanner settings for the records."""
        return {
            LLM_GUARD_DETECTOR_ID: {
                "package_version": self._package_version,
                "model": LLM_GUARD_MODEL,
                "threshold": self._settings.threshold,
                "match_type": self._settings.match_type.value,
            },
        }
