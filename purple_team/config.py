"""Harness configuration with precedence defaults < TOML file < ``PTH_*`` variables < CLI.

The provider and the defensive layer are chosen here, so switching from the mock to Ollama
or to a cloud provider only changes configuration, never the logic.
"""

import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Final, Self, assert_never

from purple_team.errors import ConfigError
from purple_team.paths import display_path


class ProviderName(StrEnum):
    """Model providers the factory knows how to build."""

    MOCK = "mock"
    OLLAMA = "ollama"
    CLOUD = "cloud"


class DefenseMode(StrEnum):
    """Input scanner of a run; the system policy on the action items applies in every mode.

    The three scanner modes use the same LLM Guard ``PromptInjection`` scanner and only change
    its model, threshold, segmentation and speaker cleaning (``ScannerSettings``).
    """

    OFF = "off"  # no scanner
    LLM_GUARD_DEFAULT = "llm-guard-default"  # baseline of e12/e18, fixed in the code
    LLM_GUARD_TUNED = "llm-guard-tuned"  # ProtectAI with the settings chosen by calibrate
    PROMPT_GUARD_2 = "prompt-guard-2"  # LLM Guard with meta-llama/Llama-Prompt-Guard-2-86M


class LlmGuardMatchType(StrEnum):
    """``match_type`` of LLM Guard's ``PromptInjection`` scanner the harness allows.

    ``sentence`` is excluded on purpose: it downloads NLTK's ``punkt_tab`` at runtime.
    """

    FULL = "full"
    CHUNKS = "chunks"


class ScannerModel(StrEnum):
    """Models the LLM Guard scanner may use; each one has its pinned revision and labels."""

    PROTECTAI_V2 = "protectai/deberta-v3-base-prompt-injection-v2"
    PROMPT_GUARD_2 = "meta-llama/Llama-Prompt-Guard-2-86M"


class CloudThinkingLevel(StrEnum):
    """``generationConfig.thinkingConfig.thinkingLevel`` sent to Gemini (``default`` = omit)."""

    DEFAULT = "default"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OllamaFormat(StrEnum):
    """Value of the ``format`` field sent to Ollama's ``/api/chat``."""

    JSON = "json"  # generic JSON mode
    SCHEMA = "schema"  # JSON Schema of the ceremony closing (structured output)
    NONE = "none"  # the field is not sent


class ConfigSource(StrEnum):
    """Where an effective configuration value came from."""

    DEFAULT = "default"
    FILE = "file"
    ENV = "env"
    CLI = "cli"


@dataclass(frozen=True, slots=True)
class OllamaSettings:
    """Settings of the local Ollama adapter.

    ``think`` and ``output_format`` change what the model is asked for, so both are written
    to the run records: runs with different values are not directly comparable.
    """

    base_url: str
    model: str
    timeout_seconds: float
    temperature: float
    think: bool
    output_format: OllamaFormat


@dataclass(frozen=True, slots=True)
class CloudSettings:
    """Settings of the cloud adapter (Gemini REST); only the NAME of the key variable is kept."""

    vendor: str
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: float
    temperature: float
    thinking_level: CloudThinkingLevel


@dataclass(frozen=True, slots=True)
class ScannerSettings:
    """Settings of the LLM Guard prompt-injection scanner of one mode.

    A line is flagged when the injection score, rounded to 2 decimals by LLM Guard, is greater
    than ``threshold``. With ``strip_speaker`` the scanner sees the utterance without its
    ``[hh:mm:ss] Name:`` prefix; otherwise it sees the whole line.
    """

    model: ScannerModel
    threshold: float
    match_type: LlmGuardMatchType
    strip_speaker: bool

    def to_record(self) -> dict[str, object]:
        """JSON view for the run records and the calibration."""
        return {
            "model": self.model.value,
            "threshold": self.threshold,
            "match_type": self.match_type.value,
            "strip_speaker": self.strip_speaker,
        }


# llm-guard-default: the scanner of e12/e18, kept fixed so it stays the baseline.
BASELINE_SCANNER: Final = ScannerSettings(
    ScannerModel.PROTECTAI_V2,
    0.92,
    LlmGuardMatchType.FULL,
    strip_speaker=True,
)

MOCK_TEMPERATURE: Final = 0.0
DEFAULT_CONFIG_FILE: Final = Path(__file__).resolve().parent / "config.toml"
CONFIG_ENV_VAR: Final = "PTH_CONFIG"
CLI_CONFIG_KEY: Final = "config"
CONFIG_FILE_KEY: Final = "config_file"
DEFENSE_KEY: Final = "defense"
DEFENSE_SEPARATOR: Final = ","
_OWN_RETIRED: Final = (
    "la defensa propia por reglas se retiró en el ciclo 5; la política de destinos ya se "
    "aplica en todos los modos"
)
# Mode names of earlier cycles: old runs keep them, new runs reject them with a hint.
RETIRED_MODES: Final[Mapping[str, str]] = {
    "on": _OWN_RETIRED,
    "own": _OWN_RETIRED,
    "own-llm-guard": f"{_OWN_RETIRED}; usa llm-guard-default o prompt-guard-2",
    "own-prompt-guard": f"{_OWN_RETIRED}; usa llm-guard-default o prompt-guard-2",
    "llm-guard": "ahora se llama llm-guard-default (misma configuración que e12/e18)",
    "prompt-guard": "ahora es prompt-guard-2 (Prompt Guard 2 a través de LLM Guard)",
}

# Default values, identical to the versioned config.toml. Keys are flattened: harness keys
# keep their name and the other tables use the prefixes of _SECTIONS.
DEFAULTS: Final[Mapping[str, object]] = {
    "provider": "mock",
    "defense": "off",
    "cases_dir": "cases",
    "calibration_dir": "calibration",
    "inputs_dir": "inputs",
    "outputs_dir": "outputs",
    "system_prompt_file": "prompts/system_prompt.es.txt",
    "team_context_file": "team_context.json",
    "ollama.base_url": "http://localhost:11434",
    "ollama.model": "qwen3.5:4b",
    "ollama.timeout_seconds": 120,
    "ollama.temperature": 0.0,
    "ollama.think": False,
    "ollama.format": "json",
    "cloud.vendor": "gemini",
    "cloud.base_url": "https://generativelanguage.googleapis.com/v1beta",
    "cloud.model": "gemini-3.8-flash",
    "cloud.api_key_env": "PTH_CLOUD_API_KEY",
    "cloud.timeout_seconds": 120,
    "cloud.temperature": 1.0,
    "cloud.thinking_level": "low",
    "system_policy.max_content_chars": 1500,
    # Chosen by `calibrate` (20261024T231908Z_calibration_impl26, handoff/26); see config.toml.
    "llm_guard_tuned.threshold": 0.99,
    "llm_guard_tuned.match_type": "full",
    "llm_guard_tuned.strip_speaker": False,
    "prompt_guard_2.threshold": 0.01,
    "prompt_guard_2.match_type": "full",
    "prompt_guard_2.strip_speaker": True,
}

# Keys of the policy table that no longer exist: the destinations come from the team context.
REMOVED_POLICY_KEYS: Final = frozenset(
    {"allowed_email_domains", "allowed_onedrive_root", "allowed_jira_projects"},
)
POLICY_SECTIONS: Final = frozenset({("defense", "policy"), ("system_policy",)})
# Tables of earlier cycles, each with the migration hint shown instead of "unknown key".
REMOVED_SECTIONS: Final[Mapping[tuple[str, ...], str]] = {
    ("defense", "policy"): (
        "La sección [defense.policy] ahora es [system_policy]: la política de destinos es parte "
        "del sistema y se aplica en todos los modos (README §10)"
    ),
    ("defense", "llm_guard"): (
        "La sección [defense.llm_guard] ya no existe: llm-guard-default está fijado en el código "
        "(línea base) y llm-guard-tuned se configura en [defense.llm_guard_tuned] (README §10)"
    ),
    ("defense", "prompt_guard"): (
        "La sección [defense.prompt_guard] ahora es [defense.prompt_guard_2] (Prompt Guard 2 a "
        "través de LLM Guard; README §10)"
    ),
}

_SECTIONS: Final[Mapping[tuple[str, ...], str]] = {
    ("harness",): "",
    ("providers", "ollama"): "ollama.",
    ("providers", "cloud"): "cloud.",
    ("system_policy",): "system_policy.",
    ("defense", "llm_guard_tuned"): "llm_guard_tuned.",
    ("defense", "prompt_guard_2"): "prompt_guard_2.",
}

ENV_OVERRIDES: Final[Mapping[str, str]] = {
    "PTH_PROVIDER": "provider",
    "PTH_DEFENSE": "defense",
    "PTH_TEAM_CONTEXT_FILE": "team_context_file",
    "PTH_OLLAMA_BASE_URL": "ollama.base_url",
    "PTH_OLLAMA_MODEL": "ollama.model",
    "PTH_OLLAMA_THINK": "ollama.think",
    "PTH_OLLAMA_FORMAT": "ollama.format",
    "PTH_CLOUD_VENDOR": "cloud.vendor",
    "PTH_CLOUD_BASE_URL": "cloud.base_url",
    "PTH_CLOUD_MODEL": "cloud.model",
    "PTH_CLOUD_TEMPERATURE": "cloud.temperature",
    "PTH_CLOUD_THINKING_LEVEL": "cloud.thinking_level",
}
# Environment values that must be converted to numbers before validation.
NUMERIC_ENV_KEYS: Final = frozenset({"cloud.temperature"})

# Accepted spellings of a boolean that comes from an environment variable.
BOOLEAN_TEXTS: Final[Mapping[str, bool]] = {"true": True, "false": False}

CLI_OVERRIDES: Final[Mapping[str, str]] = {
    "provider": "provider",
    "defense": "defense",
}


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Effective configuration; every path is absolute and resolved against ``base_dir``."""

    provider: ProviderName
    defense: DefenseMode
    base_dir: Path
    config_file: Path
    cases_dir: Path
    calibration_dir: Path
    inputs_dir: Path
    outputs_dir: Path
    system_prompt_file: Path
    team_context_file: Path
    ollama: OllamaSettings
    cloud: CloudSettings
    max_content_chars: int
    llm_guard_tuned: ScannerSettings
    prompt_guard_2: ScannerSettings
    sources: Mapping[str, ConfigSource]

    @property
    def temperature(self) -> float:
        """Single source of the temperature: the section of the active provider."""
        match self.provider:
            case ProviderName.MOCK:
                return MOCK_TEMPERATURE
            case ProviderName.OLLAMA:
                return self.ollama.temperature
            case ProviderName.CLOUD:
                return self.cloud.temperature

    def scanner_settings(self, mode: DefenseMode) -> ScannerSettings | None:
        """Scanner settings of a mode (``None`` for ``off``)."""
        match mode:
            case DefenseMode.OFF:
                return None
            case DefenseMode.LLM_GUARD_DEFAULT:
                return BASELINE_SCANNER
            case DefenseMode.LLM_GUARD_TUNED:
                return self.llm_guard_tuned
            case DefenseMode.PROMPT_GUARD_2:
                return self.prompt_guard_2
            case _:
                assert_never(mode)

    def with_defense(self, mode: DefenseMode, source: ConfigSource) -> Self:
        """Return a copy with another defense mode (one per run of a measurement)."""
        sources = {**self.sources, "defense": source}
        return replace(self, defense=mode, sources=sources)

    def to_record(self) -> dict[str, object]:
        """Serializable view for the run records; secrets are never included."""
        return {
            "provider": self.provider.value,
            "defense": self.defense.value,
            "config_file": self.display(self.config_file),
            "cases_dir": self.display(self.cases_dir),
            "calibration_dir": self.display(self.calibration_dir),
            "inputs_dir": self.display(self.inputs_dir),
            "outputs_dir": self.display(self.outputs_dir),
            "system_prompt_file": self.display(self.system_prompt_file),
            "team_context_file": self.display(self.team_context_file),
            "temperature": self.temperature,
            "ollama": {
                "base_url": self.ollama.base_url,
                "model": self.ollama.model,
                "timeout_seconds": self.ollama.timeout_seconds,
                "temperature": self.ollama.temperature,
                "think": self.ollama.think,
                "format": self.ollama.output_format.value,
            },
            "cloud": {
                "vendor": self.cloud.vendor,
                "base_url": self.cloud.base_url,
                "model": self.cloud.model,
                "api_key_env": self.cloud.api_key_env,
                "timeout_seconds": self.cloud.timeout_seconds,
                "temperature": self.cloud.temperature,
                "thinking_level": self.cloud.thinking_level.value,
            },
            "llm_guard_default": BASELINE_SCANNER.to_record(),
            "llm_guard_tuned": self.llm_guard_tuned.to_record(),
            "prompt_guard_2": self.prompt_guard_2.to_record(),
            "sources": {key: source.value for key, source in sorted(self.sources.items())},
        }

    def display(self, path: Path) -> str:
        """Apply the single path rule (plan section 7.3) with this config's ``base_dir``."""
        return display_path(path, self.base_dir)


def parse_defense_mode(value: object, source: str) -> DefenseMode:
    """Resolve a defense mode; ``ConfigError`` (with a hint for retired names) otherwise."""
    accepted = {member.value: member for member in DefenseMode}
    if isinstance(value, str) and value in accepted:
        return accepted[value]
    options = ", ".join(member.value for member in DefenseMode)
    hint = RETIRED_MODES.get(value) if isinstance(value, str) else None
    retired = f"{hint[0].upper()}{hint[1:]}. " if hint else ""
    message = (
        f"Valor inválido para defense (origen: {source}): {value!r}. "
        f"{retired}Opciones válidas: {options}"
    )
    raise ConfigError(message)


def parse_defense_modes(text: str) -> tuple[DefenseMode, ...]:
    """Parse ``off,llm-guard-default,...`` from the command line into distinct modes, in order."""
    names = [name.strip() for name in text.split(DEFENSE_SEPARATOR)]
    if any(not name for name in names):
        example = "off,llm-guard-default,prompt-guard-2"
        raise ConfigError(f"Lista de defensas inválida: {text!r}. Ejemplo: {example}")
    modes = tuple(parse_defense_mode(name, ConfigSource.CLI.value) for name in names)
    if len(set(modes)) != len(modes):
        shown = ", ".join(mode.value for mode in modes)
        raise ConfigError(f"Lista de defensas con modos repetidos: {shown}")
    return modes


def load_config(*, cli_overrides: Mapping[str, str], environ: Mapping[str, str]) -> HarnessConfig:
    """Build the effective configuration; raise ``ConfigError`` when something is invalid."""
    unknown = sorted(set(cli_overrides) - set(CLI_OVERRIDES) - {CLI_CONFIG_KEY})
    if unknown:
        names = ", ".join(unknown)
        raise ConfigError(f"Opciones de configuración desconocidas: {names}")
    config_file, file_source = _choose_config_file(cli_overrides, environ)
    values: dict[str, object] = dict(DEFAULTS)
    sources: dict[str, ConfigSource] = dict.fromkeys(DEFAULTS, ConfigSource.DEFAULT)
    for key, value in _read_config_file(config_file).items():
        values[key] = value
        sources[key] = ConfigSource.FILE
    for variable, key in ENV_OVERRIDES.items():
        if environ.get(variable):
            values[key] = _env_value(variable, key, environ[variable])
            sources[key] = ConfigSource.ENV
    for option, key in CLI_OVERRIDES.items():
        if cli_overrides.get(option):
            values[key] = cli_overrides[option]
            sources[key] = ConfigSource.CLI
    sources[CONFIG_FILE_KEY] = file_source
    return _build(values, sources, config_file)


def _env_value(variable: str, key: str, raw: str) -> object:
    """Environment text, converted to a finite number for the numeric keys."""
    if key not in NUMERIC_ENV_KEYS:
        return raw
    try:
        number = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{variable} debe ser un número: {raw!r}") from exc
    if not math.isfinite(number):
        raise ConfigError(f"{variable} debe ser un número finito: {raw!r}")
    return number


def _choose_config_file(
    cli_overrides: Mapping[str, str],
    environ: Mapping[str, str],
) -> tuple[Path, ConfigSource]:
    if cli_overrides.get(CLI_CONFIG_KEY):
        return Path(cli_overrides[CLI_CONFIG_KEY]).resolve(), ConfigSource.CLI
    if environ.get(CONFIG_ENV_VAR):
        return Path(environ[CONFIG_ENV_VAR]).resolve(), ConfigSource.ENV
    return DEFAULT_CONFIG_FILE, ConfigSource.DEFAULT


def _read_config_file(config_file: Path) -> dict[str, object]:
    try:
        with config_file.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"El archivo {config_file} no es TOML válido: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"No se pudo leer el archivo de configuración {config_file}") from exc
    flat: dict[str, object] = {}
    for leaf_path, value in _iter_leaves(data, ()):
        section = leaf_path[:-1]
        if section in POLICY_SECTIONS and leaf_path[-1] in REMOVED_POLICY_KEYS:
            dotted = ".".join(leaf_path)
            message = (
                f"La clave {dotted} ya no existe: los destinos permitidos se derivan de "
                "team_context.json (ver README §10)"
            )
            raise ConfigError(message)
        if section in REMOVED_SECTIONS:
            raise ConfigError(f"{REMOVED_SECTIONS[section]} ({config_file})")
        prefix = _SECTIONS.get(section)
        key = None if prefix is None else prefix + leaf_path[-1]
        if key is None or key not in DEFAULTS:
            dotted = ".".join(leaf_path)
            raise ConfigError(f"Clave desconocida en {config_file}: {dotted}")
        flat[key] = value
    return flat


def _iter_leaves(
    table: Mapping[str, object],
    prefix: tuple[str, ...],
) -> list[tuple[tuple[str, ...], object]]:
    leaves: list[tuple[tuple[str, ...], object]] = []
    for name, value in table.items():
        if isinstance(value, Mapping):
            leaves.extend(_iter_leaves(value, (*prefix, name)))
        else:
            leaves.append(((*prefix, name), value))
    return leaves


def _build(
    values: Mapping[str, object],
    sources: Mapping[str, ConfigSource],
    config_file: Path,
) -> HarnessConfig:
    reader = _ValueReader(values, sources)
    base_dir = config_file.parent.resolve()
    return HarnessConfig(
        provider=reader.enum("provider", ProviderName),
        defense=reader.defense_mode(DEFENSE_KEY),
        base_dir=base_dir,
        config_file=config_file,
        cases_dir=reader.path("cases_dir", base_dir),
        calibration_dir=reader.path("calibration_dir", base_dir),
        inputs_dir=reader.path("inputs_dir", base_dir),
        outputs_dir=reader.path("outputs_dir", base_dir),
        system_prompt_file=reader.path("system_prompt_file", base_dir),
        team_context_file=reader.path("team_context_file", base_dir),
        ollama=OllamaSettings(
            base_url=reader.text("ollama.base_url"),
            model=reader.text("ollama.model"),
            timeout_seconds=reader.positive_number("ollama.timeout_seconds"),
            temperature=reader.temperature("ollama.temperature"),
            think=reader.boolean("ollama.think"),
            output_format=reader.enum("ollama.format", OllamaFormat),
        ),
        cloud=CloudSettings(
            vendor=reader.text("cloud.vendor"),
            base_url=reader.text("cloud.base_url"),
            model=reader.text("cloud.model"),
            api_key_env=reader.text("cloud.api_key_env"),
            timeout_seconds=reader.positive_number("cloud.timeout_seconds"),
            temperature=reader.temperature("cloud.temperature"),
            thinking_level=reader.enum("cloud.thinking_level", CloudThinkingLevel),
        ),
        max_content_chars=reader.positive_int("system_policy.max_content_chars"),
        llm_guard_tuned=reader.scanner("llm_guard_tuned.", ScannerModel.PROTECTAI_V2),
        prompt_guard_2=reader.scanner("prompt_guard_2.", ScannerModel.PROMPT_GUARD_2),
        sources=dict(sources),
    )


class _ValueReader:
    """Typed access to the merged values with error messages that name the source."""

    def __init__(self, values: Mapping[str, object], sources: Mapping[str, ConfigSource]) -> None:
        self._values = values
        self._sources = sources

    def _invalid(self, key: str, expected: str) -> ConfigError:
        value = self._values[key]
        source = self._sources[key].value
        return ConfigError(f"Valor inválido para {key} (origen: {source}): {value!r}. {expected}")

    def enum[E: StrEnum](self, key: str, enum_type: type[E]) -> E:
        options = ", ".join(member.value for member in enum_type)
        try:
            return enum_type(self._values[key])
        except ValueError as exc:
            raise self._invalid(key, f"Opciones válidas: {options}") from exc

    def defense_mode(self, key: str) -> DefenseMode:
        return parse_defense_mode(self._values[key], self._sources[key].value)

    def boolean(self, key: str) -> bool:
        value = self._values[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().casefold() in BOOLEAN_TEXTS:
            return BOOLEAN_TEXTS[value.strip().casefold()]
        raise self._invalid(key, "Se esperaba true o false")

    def text(self, key: str) -> str:
        value = self._values[key]
        if not isinstance(value, str) or not value.strip():
            raise self._invalid(key, "Se esperaba un texto no vacío")
        return value

    def path(self, key: str, base_dir: Path) -> Path:
        return (base_dir / self.text(key)).resolve()

    def positive_number(self, key: str) -> float:
        value = self._values[key]
        if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
            raise self._invalid(key, "Se esperaba un número mayor que cero")
        return float(value)

    def temperature(self, key: str) -> float:
        value = self._values[key]
        if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
            raise self._invalid(key, "Se esperaba un número mayor o igual que cero")
        return float(value)

    def positive_int(self, key: str) -> int:
        value = self._values[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise self._invalid(key, "Se esperaba un entero mayor que cero")
        return value

    def scanner(self, prefix: str, model: ScannerModel) -> ScannerSettings:
        # The model is fixed by the mode: each one needs its revision and label mapping.
        return ScannerSettings(
            model=model,
            threshold=self.open_unit_interval(f"{prefix}threshold"),
            match_type=self.enum(f"{prefix}match_type", LlmGuardMatchType),
            strip_speaker=self.boolean(f"{prefix}strip_speaker"),
        )

    def open_unit_interval(self, key: str) -> float:
        value = self._values[key]
        if isinstance(value, bool) or not isinstance(value, int | float) or not 0 < value < 1:
            raise self._invalid(key, "Se esperaba un número entre 0 y 1 (sin incluirlos)")
        return float(value)
