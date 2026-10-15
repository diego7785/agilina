"""Optional input detector based on Meta's Llama Prompt Guard 2 (86M) classifier.

Prompt Guard 2 is NOT a dependency of the harness: ``transformers`` and ``torch`` (already in
``purple_team/.venv`` because LLM Guard needs them) are imported lazily, only when a run asks
for ``prompt-guard`` or ``own-prompt-guard``. LLM Guard's ``PromptInjection`` scanner is not
used on purpose: it only understands an ``INJECTION`` label and would read the benign /
malicious scores of this model backwards.

The model comes only from the official, gated repository on Hugging Face, at a fixed
revision; the user accepts the Llama 4 license and logs in (``hf auth login``) on their own.
The harness never reads, receives or records the Hugging Face token: ``huggingface_hub``
uses the stored login by itself. When the packages, the access or the cached model are
missing, ``DefenseUnavailableError`` explains what to do and the CLI exits with code 4
before writing anything.

Each utterance (the line without its ``[hh:mm:ss] Name:`` prefix) is scored on its own, like
the other input detectors: the score is P(malicious), the softmax of the logits with the
index of the ``malicious`` label read from ``model.config.id2label``; an utterance longer than
the 512-token window is split into segments and the highest score wins (official model
card). A flagged line is redacted, never the whole transcript.
"""

import importlib
import importlib.metadata
import math
import sys
from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from types import ModuleType
from typing import Final, Protocol

from purple_team.config import PromptGuardSettings
from purple_team.defense.models import EXCERPT_MAX_CHARS, Detection, split_speaker
from purple_team.errors import DefenseUnavailableError

PROMPT_GUARD_DETECTOR_ID: Final = "prompt_guard"
PROMPT_GUARD_RULE_ID: Final = "prompt_guard_malicious"
PROMPT_GUARD_MODEL: Final = "meta-llama/Llama-Prompt-Guard-2-86M"
# Commit of "main" on 2025-04-29 (Hugging Face API), fixed so the measurements are repeatable.
PROMPT_GUARD_REVISION: Final = "a8ded8e697ce7c355e395a0df51f94adb4a2fd27"
PROMPT_GUARD_URL: Final = "https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M"
MALICIOUS_LABEL: Final = "malicious"  # compared after casefold
BENIGN_LABEL: Final = "benign"
EXPECTED_LABELS: Final = frozenset({BENIGN_LABEL, MALICIOUS_LABEL})
MAX_TOKENS: Final = 512  # context window of the model (official model card)
DEVICE: Final = "cpu"
SCORE_DECIMALS: Final = 4
TRANSFORMERS_MODULE: Final = "transformers"
TORCH_MODULE: Final = "torch"
OVERFLOW_MAPPING_KEY: Final = "overflow_to_sample_mapping"
OFFLINE_ENV_VAR: Final = "HF_HUB_OFFLINE"
# Same spellings huggingface_hub accepts as true (compared after casefold).
TRUE_TEXTS: Final = frozenset({"1", "true", "yes", "on"})
HF_CLI: Final = "purple_team/.venv/bin/hf"
VENV_PYTHON: Final = "purple_team/.venv/bin/python"
CACHE_FOLDER: Final = "~/.cache/huggingface/hub/models--meta-llama--Llama-Prompt-Guard-2-86M"
DOWNLOAD_SIZE: Final = "≈ 1,13 GB"
REASON_MAX_CHARS: Final = 300
GATED_ERROR: Final = "GatedRepoError"
NOT_FOUND_ERROR: Final = "RepositoryNotFoundError"
LOCAL_ENTRY_ERROR: Final = "LocalEntryNotFoundError"


class _Logits(Protocol):
    def tolist(self) -> list[list[float]]:
        """One row of logits per segment."""


class _ClassifierOutput(Protocol):
    @property
    def logits(self) -> _Logits:
        """Logits of the sequence classification head."""


class _Model(Protocol):
    def __call__(self, **inputs: object) -> _ClassifierOutput:
        """Run the classifier on tokenized inputs."""


class _Tokenizer(Protocol):
    def __call__(self, text: str, **options: object) -> MutableMapping[str, object]:
        """Tokenize a text into model inputs."""


class PromptGuardClassifier(Protocol):
    """What the detector needs from the model: P(malicious) of a text (max over segments)."""

    def malicious_score(self, text: str) -> float:
        """Probability that the text tries to override previous instructions."""

    def describe(self) -> dict[str, object]:
        """Labels, malicious index, device and versions for the records."""


def _import_module(name: str) -> ModuleType:
    """Module-level wrapper so the tests can fake the import without touching importlib."""
    return importlib.import_module(name)


def is_offline(environ: Mapping[str, str]) -> bool:
    """Whether ``HF_HUB_OFFLINE`` forbids downloads (``1``, ``true``, ``yes`` or ``on``)."""
    return environ.get(OFFLINE_ENV_VAR, "").strip().casefold() in TRUE_TEXTS


def resolve_malicious_index(id2label: Mapping[int, str]) -> int:
    """Index of the ``malicious`` label; the order is read from the model, never assumed."""
    labels = {int(index): str(name).casefold() for index, name in id2label.items()}
    if len(labels) != len(EXPECTED_LABELS) or set(labels.values()) != EXPECTED_LABELS:
        message = (
            f"Etiquetas inesperadas en el modelo: {dict(id2label)}; se esperaba "
            f"{BENIGN_LABEL}/{MALICIOUS_LABEL}. No se ejecutó ninguna corrida."
        )
        raise DefenseUnavailableError(message)
    return next(index for index, name in labels.items() if name == MALICIOUS_LABEL)


def malicious_probability(logits: Sequence[float], index: int) -> float:
    """Softmax (temperature 1, numerically stable) of one row of logits, at ``index``."""
    highest = max(logits)
    weights = [math.exp(value - highest) for value in logits]
    return weights[index] / sum(weights)


def distribution_version(name: str) -> str | None:
    """Installed version of a distribution, or ``None`` when it is missing."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def missing_message(missing: str) -> str:
    """Spanish instructions shown when ``transformers`` or ``torch`` are not installed."""
    return (
        "Llama Prompt Guard 2 necesita los paquetes transformers y torch, que no están en este "
        f"intérprete ({sys.executable}; falta: {missing}). Los modos off, own, llm-guard y "
        "own-llm-guard no lo necesitan. Están en el entorno propio del banco (los instala "
        "LLM Guard):\n"
        f"  {VENV_PYTHON} -m purple_team run --defense prompt-guard\n"
        "Si el entorno no existe: python3 -m venv purple_team/.venv\n"
        f'  {VENV_PYTHON} -m pip install "llm-guard==0.3.16"\n'
        "No se ejecutó ninguna corrida (tampoco las de otros modos pedidos). Para medir solo "
        "los modos disponibles, repite sin prompt-guard ni own-prompt-guard."
    )


def converter_message(exc: ImportError) -> str:
    """Spanish message when ``transformers`` asks for an optional tokenizer dependency."""
    missing = exc.name or _first_line(str(exc))
    return (
        "No se pudo cargar el tokenizador de Llama Prompt Guard 2: transformers pide un "
        f"paquete opcional que no está instalado (falta: {missing}). Solo se instalaría en el "
        "entorno propio del banco y con autorización del usuario (nunca en pyproject.toml, "
        "uv.lock ni el workspace de uv):\n"
        f"  {VENV_PYTHON} -m pip install sentencepiece protobuf\n"
        "No se ejecutó ninguna corrida; los modos off, own, llm-guard y own-llm-guard siguen "
        "disponibles."
    )


def unavailable_message(exc: BaseException, environ: Mapping[str, str]) -> str:
    """Spanish diagnosis and steps when the model cannot be downloaded or loaded.

    The diagnosis looks at the class names of the exception chain (``transformers`` wraps
    the ``huggingface_hub`` errors with ``raise OSError(...) from e``), so ``huggingface_hub``
    is never imported here. No environment value is ever written to the message.
    """
    header = (
        f"No se pudo cargar Llama Prompt Guard 2 ({PROMPT_GUARD_MODEL}, revisión "
        f"{PROMPT_GUARD_REVISION}): {type(exc).__name__}: {_first_line(str(exc))}"
    )
    steps = (
        f"1) Acepta la licencia (Llama 4 Community License) en {PROMPT_GUARD_URL} con tu cuenta "
        "de Hugging Face.\n"
        f"2) Inicia sesión en este equipo: {HF_CLI} auth login (el token lo gestiona Hugging "
        "Face; el banco nunca lo lee).\n"
        f"3) La primera vez, ejecuta sin {OFFLINE_ENV_VAR} para descargar el modelo "
        f"({DOWNLOAD_SIZE}) a {CACHE_FOLDER}; después puedes usar {OFFLINE_ENV_VAR}=1.\n"
        "No se ejecutó ninguna corrida (tampoco las de otros modos pedidos)."
    )
    return f"{header}\nDiagnóstico: {_diagnosis(exc, environ)}\n{steps}"


def _diagnosis(exc: BaseException, environ: Mapping[str, str]) -> str:
    names = {cls.__name__ for error in _exception_chain(exc) for cls in type(error).__mro__}
    if GATED_ERROR in names:
        return (
            "no hay acceso al repositorio restringido: sin sesión iniciada, licencia Llama 4 no "
            f"aceptada en {PROMPT_GUARD_URL} o aprobación (manual) pendiente."
        )
    if NOT_FOUND_ERROR in names:
        return "el repositorio no es visible: inicia sesión o revisa el acceso."
    if is_offline(environ):
        return f"el modelo no está en la caché local y {OFFLINE_ENV_VAR}=1 impide descargarlo."
    if LOCAL_ENTRY_ERROR in names:
        return (
            "el modelo no está en la caché local y no se pudo descargar de huggingface.co "
            "(revisa la conexión)."
        )
    return "revisa la conexión, la sesión de Hugging Face y el acceso al repositorio."


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """The exception and its causes or contexts, each once."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0][:REASON_MAX_CHARS] if lines else ""


def load_prompt_guard_classifier(environ: Mapping[str, str]) -> PromptGuardClassifier:
    """Import ``transformers``, load the pinned model on CPU; ``DefenseUnavailableError``.

    ``HF_HUB_OFFLINE`` (read from ``environ``) becomes ``local_files_only``. No ``token``
    argument is ever passed.
    """
    try:
        transformers = _import_module(TRANSFORMERS_MODULE)
        torch = _import_module(TORCH_MODULE)
    except ImportError as exc:
        raise DefenseUnavailableError(missing_message(exc.name or TRANSFORMERS_MODULE)) from exc
    # Before loading: called afterwards it would not silence the warnings of the load itself.
    transformers.logging.set_verbosity_error()
    options: dict[str, object] = {
        "revision": PROMPT_GUARD_REVISION,
        "local_files_only": is_offline(environ),
    }
    try:
        tokenizer = transformers.AutoTokenizer.from_pretrained(
            PROMPT_GUARD_MODEL,
            use_fast=True,
            **options,
        )
        model = transformers.AutoModelForSequenceClassification.from_pretrained(
            PROMPT_GUARD_MODEL,
            **options,
        )
    except ImportError as exc:
        raise DefenseUnavailableError(converter_message(exc)) from exc
    except (OSError, ValueError, RuntimeError) as exc:
        raise DefenseUnavailableError(unavailable_message(exc, environ)) from exc
    model.to(DEVICE)
    model.eval()
    id2label = dict(model.config.id2label)
    return TransformersPromptGuard(
        tokenizer=tokenizer,
        model=model,
        torch=torch,
        id2label=id2label,
        malicious_index=resolve_malicious_index(id2label),
    )


class TransformersPromptGuard:
    """Real classifier: tokenizer + ``AutoModelForSequenceClassification``, CPU, no gradients."""

    def __init__(
        self,
        *,
        tokenizer: _Tokenizer,
        model: _Model,
        torch: ModuleType,
        id2label: Mapping[int, str],
        malicious_index: int,
    ) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch
        self._id2label = dict(id2label)
        self._index = malicious_index

    def malicious_score(self, text: str) -> float:
        """Highest P(malicious) over the segments of at most ``MAX_TOKENS`` tokens."""
        encoded = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_TOKENS,
            padding=True,
            return_overflowing_tokens=True,
        )
        # Only the tokenizer knows this key; the model would reject it.
        encoded.pop(OVERFLOW_MAPPING_KEY, None)
        with self._torch.inference_mode():
            rows = self._model(**encoded).logits.tolist()
        score = max(malicious_probability(row, self._index) for row in rows)
        return round(score, SCORE_DECIMALS)

    def describe(self) -> dict[str, object]:
        """The label mapping read from the model, the device and the library versions."""
        return {
            "labels": {str(index): name for index, name in sorted(self._id2label.items())},
            "malicious_index": self._index,
            "device": DEVICE,
            "transformers_version": distribution_version(TRANSFORMERS_MODULE),
            "torch_version": distribution_version(TORCH_MODULE),
        }


class PromptGuardDetector:
    """``LineDetector`` that asks Llama Prompt Guard 2 about each utterance."""

    def __init__(self, classifier: PromptGuardClassifier, settings: PromptGuardSettings) -> None:
        self._classifier = classifier
        self._settings = settings

    @property
    def detector_id(self) -> str:
        """``prompt_guard``."""
        return PROMPT_GUARD_DETECTOR_ID

    def detect(self, line_number: int, line: str) -> tuple[Detection, ...]:
        """Score the utterance without its speaker prefix; flag it when score > threshold."""
        _prefix, utterance = split_speaker(line)
        if not utterance.strip():
            return ()
        score = self._classifier.malicious_score(utterance)
        if score <= self._settings.threshold:
            return ()
        excerpt = utterance[:EXCERPT_MAX_CHARS]
        return (Detection(line_number, PROMPT_GUARD_RULE_ID, excerpt, score=score),)

    def describe(self) -> dict[str, object]:
        """Model, revision, threshold, decision rule and what the classifier reports."""
        return {
            PROMPT_GUARD_DETECTOR_ID: {
                "model": PROMPT_GUARD_MODEL,
                "revision": PROMPT_GUARD_REVISION,
                "threshold": self._settings.threshold,
                "decision": "score > threshold",
                "score": "softmax P(malicious)",
                "max_tokens": MAX_TOKENS,
                **self._classifier.describe(),
            },
        }
