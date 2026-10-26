"""Values and ports of the input scanner (no implementation here)."""

import re
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from purple_team.config import DefenseMode

EXCERPT_MAX_CHARS: Final = 160
# "[hh:mm:ss] Name Surname: " at the start of a transcript line.
SPEAKER_PREFIX: Final = re.compile(r"^\s*\[[^\]]*\]\s*[^:]+:\s*")


def split_speaker(line: str) -> tuple[str, str]:
    """Split a transcript line into its speaker prefix (maybe empty) and the utterance."""
    match = SPEAKER_PREFIX.match(line)
    prefix = match.group(0) if match else ""
    return prefix, line[len(prefix) :]


@dataclass(frozen=True, slots=True)
class Detection:
    """An input detector flagged a line of the original transcript.

    ``score`` is the risk score of LLM Guard (``calculate_risk_score``, from -1 to 1).
    """

    line_number: int
    rule_id: str
    excerpt: str
    score: float | None = None

    def to_dict(self) -> dict[str, object]:
        """JSON view (``score`` is always present)."""
        return {
            "line_number": self.line_number,
            "rule_id": self.rule_id,
            "excerpt": self.excerpt,
            "score": self.score,
        }


@runtime_checkable
class LineDetector(Protocol):
    """Decides, line by line, whether a transcript line carries an instruction."""

    @property
    def detector_id(self) -> str:
        """Short name written to the records (``llm_guard``)."""

    def detect(self, line_number: int, line: str) -> tuple[Detection, ...]:
        """Detections of this line (empty when the line looks harmless)."""

    def describe(self) -> dict[str, object]:
        """Extra settings for the records, keyed by detector (may be empty)."""


@dataclass(frozen=True, slots=True)
class InputScreening:
    """Result of screening the transcript; ``transcript`` is what the model receives."""

    mode: DefenseMode
    transcript: str
    detections: tuple[Detection, ...]
    redacted_lines: tuple[int, ...]
    detectors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """JSON view without the transcript (it is written to its own file)."""
        return {
            "mode": self.mode.value,
            "detectors": list(self.detectors),
            "detections": [detection.to_dict() for detection in self.detections],
            "redacted_lines": list(self.redacted_lines),
        }


@runtime_checkable
class Defense(Protocol):
    """Optional input scanner applied before the core (the system policy is not part of it)."""

    @property
    def mode(self) -> DefenseMode:
        """Defense mode written to the records."""

    def describe(self) -> dict[str, object]:
        """Setup for the records: mode and input detectors with their settings."""

    def screen_input(self, transcript: str) -> InputScreening:
        """Screen the transcript before it reaches the model."""
