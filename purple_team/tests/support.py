"""Shared helpers for the harness tests: fixed clock, temporary configurations and doubles."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from purple_team.cli import main
from purple_team.composition import build_tools
from purple_team.config import BASELINE_SCANNER, DefenseMode, ScannerSettings
from purple_team.core.ceremony import CeremonyCloser
from purple_team.defense.input_guard import InputGuard
from purple_team.defense.layered import InputGuardDefense
from purple_team.defense.llm_guard import LlmGuardDetector
from purple_team.defense.models import Defense
from purple_team.pipeline import AgentPipeline
from purple_team.policy import SystemPolicy
from purple_team.team_context import TeamContext, load_team_context
from purple_team.tools.system_outputs import SystemOutputs

PURPLE_TEAM_DIR = Path(__file__).resolve().parent.parent
REAL_CASES_DIR = PURPLE_TEAM_DIR / "cases"
REAL_CALIBRATION_DIR = PURPLE_TEAM_DIR / "calibration"
REAL_SYSTEM_PROMPT = PURPLE_TEAM_DIR / "prompts" / "system_prompt.es.txt"
REAL_TEAM_CONTEXT = PURPLE_TEAM_DIR / "team_context.json"
FIXED_INSTANT = datetime(2026, 10, 11, 15, 30, tzinfo=UTC)
TEMP_CONFIG_NAME = "config.toml"
HIDDEN_PREFIX: Final = "."
EXCLUDED_DIR_NAMES: Final = frozenset({"__pycache__"})
TESTS_DIR_NAME: Final = "tests"
PYTHON_SUFFIX: Final = ".py"
DEFAULT_MAX_CONTENT_CHARS: Final = 1500
# Words that the LLM Guard double flags: they only appear in the injected lines of c01, c02,
# c03, c04 and c06 (never in c00, c05 or c07), see handoff/08 section 8.2.
KEYWORD_SCANNER_WORDS: Final = ("asistente", "agilina", "<!--", "meeting bot")
FLAGGED_SCORE: Final = 1.0
CLEAN_SCORE: Final = -1.0


def real_team_context() -> TeamContext:
    """The versioned ``team_context.json``."""
    return load_team_context(REAL_TEAM_CONTEXT)


def default_policy(max_content_chars: int = DEFAULT_MAX_CONTENT_CHARS) -> SystemPolicy:
    """System policy derived from the versioned team context."""
    return SystemPolicy.from_team_context(real_team_context(), max_content_chars)


def simulated_pipeline(closer: CeremonyCloser, defense: Defense) -> AgentPipeline:
    """Pipeline with the system policy, the simulated tools and the system outputs."""
    context = real_team_context()
    return AgentPipeline(closer, defense, default_policy(), build_tools(), SystemOutputs(context))


class KeywordScanner:
    """Test double of LLM Guard's ``PromptInjection``: flags a few fixed keywords.

    It never loads a model; it records every prompt it was asked about.
    """

    def __init__(self, words: Sequence[str] = KEYWORD_SCANNER_WORDS) -> None:
        self._words = tuple(word.casefold() for word in words)
        self.prompts: list[str] = []

    def scan(self, prompt: str) -> tuple[str, bool, float]:
        """``(prompt, False, 1.0)`` when a keyword is present, else ``(prompt, True, -1.0)``."""
        self.prompts.append(prompt)
        folded = prompt.casefold()
        if any(word in folded for word in self._words):
            return prompt, False, FLAGGED_SCORE
        return prompt, True, CLEAN_SCORE


def scanner_defense(
    mode: DefenseMode = DefenseMode.LLM_GUARD_DEFAULT,
    scanner: KeywordScanner | None = None,
    settings: ScannerSettings = BASELINE_SCANNER,
) -> InputGuardDefense:
    """A scanner mode with the ``KeywordScanner`` double instead of a real model."""
    chosen = KeywordScanner() if scanner is None else scanner
    detector = LlmGuardDetector(chosen, settings, None)
    return InputGuardDefense(mode, InputGuard((detector,)))


class FixedClock:
    """Clock that always returns the same instant."""

    def __init__(self, moment: datetime = FIXED_INSTANT) -> None:
        self._moment = moment

    def now(self) -> datetime:
        """Return the fixed instant."""
        return self._moment


@dataclass(frozen=True, slots=True)
class CliResult:
    """Exit code and captured output of one CLI invocation."""

    code: int
    stdout: str
    stderr: str


def iter_python_files_under(root: Path) -> Iterator[Path]:
    """Every ``*.py`` under ``root``, sorted, skipping hidden parts and caches.

    A path is skipped when any part relative to ``root`` starts with ``.`` (``.venv``,
    ``.git``, hidden files) or is ``__pycache__``: the optional virtualenv of LLM Guard lives
    inside the package and must never be checked as harness code.
    """
    found: list[Path] = []
    for directory, dir_names, file_names in root.walk():
        # Pruning in place keeps the walk out of the virtualenv (thousands of files).
        dir_names[:] = [name for name in dir_names if not _is_skipped(name)]
        python_names = [name for name in file_names if name.endswith(PYTHON_SUFFIX)]
        found.extend(directory / name for name in python_names if not _is_skipped(name))
    yield from sorted(found)


def _is_skipped(name: str) -> bool:
    return name.startswith(HIDDEN_PREFIX) or name in EXCLUDED_DIR_NAMES


def iter_harness_python_files() -> Iterator[Path]:
    """Python files of the package and its tests (used by ``test_style``)."""
    yield from iter_python_files_under(PURPLE_TEAM_DIR)


def iter_harness_source_files() -> Iterator[Path]:
    """Python files of the package without ``tests/`` (used by ``test_import_graph``)."""
    for path in iter_harness_python_files():
        if path.relative_to(PURPLE_TEAM_DIR).parts[0] != TESTS_DIR_NAME:
            yield path


def make_temp_dir(test: unittest.TestCase) -> Path:
    """Create a temporary directory that is removed when the test finishes."""
    holder = tempfile.TemporaryDirectory()
    test.addCleanup(holder.cleanup)
    return Path(holder.name)


def toml_string(value: str) -> str:
    """Quote a value as a TOML basic string (JSON escapes are valid TOML escapes)."""
    return json.dumps(value)


def write_temp_config(
    directory: Path,
    *,
    cases_dir: Path = REAL_CASES_DIR,
    calibration_dir: Path = REAL_CALIBRATION_DIR,
    harness_lines: Sequence[str] = (),
    extra: str = "",
) -> Path:
    """Write a TOML config whose runs land inside ``directory`` and return its path.

    ``inputs_dir`` and ``outputs_dir`` are relative (they stay inside the temporary
    directory) while the cases, the calibration set, the system prompt and the team context
    point to the real files.
    """
    lines = [
        "[harness]",
        f"cases_dir = {toml_string(str(cases_dir))}",
        f"calibration_dir = {toml_string(str(calibration_dir))}",
        'inputs_dir = "inputs"',
        'outputs_dir = "outputs"',
        f"system_prompt_file = {toml_string(str(REAL_SYSTEM_PROMPT))}",
        f"team_context_file = {toml_string(str(REAL_TEAM_CONTEXT))}",
        *harness_lines,
        "",
        extra,
    ]
    path = directory / TEMP_CONFIG_NAME
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def copy_case(case_id: str, cases_dir: Path) -> Path:
    """Copy a real case folder into ``cases_dir`` and return the copy."""
    destination = cases_dir / case_id
    shutil.copytree(REAL_CASES_DIR / case_id, destination)
    return destination


def read_json(path: Path) -> dict[str, object]:
    """Load a JSON object from a UTF-8 file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} does not contain a JSON object")
    return data


def run_cli(argv: Sequence[str], environ: Mapping[str, str] | None = None) -> CliResult:
    """Run ``main`` with a fixed clock and an isolated environment, capturing the output."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(list(argv), environ={} if environ is None else environ, clock=FixedClock())
    return CliResult(code=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())
