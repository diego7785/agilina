"""Input guard: asks the model detectors about every line and redacts the flagged lines.

When any detector flags a line, the speaker prefix ``[hh:mm:ss] Name:`` is kept and the rest
of the line is replaced by ``REDACTION_MARKER``.
"""

from collections.abc import Sequence
from typing import Final

from purple_team.defense.models import Detection, LineDetector, split_speaker

REDACTION_MARKER: Final = "[contenido retirado por la capa defensiva: posible instrucción]"
LINE_SEPARATOR: Final = "\n"


class InputGuard:
    """Asks every detector about every line and redacts the flagged lines."""

    def __init__(self, detectors: Sequence[LineDetector]) -> None:
        if not detectors:
            raise ValueError("InputGuard necesita al menos un detector")
        self._detectors = tuple(detectors)

    @property
    def detector_ids(self) -> tuple[str, ...]:
        """Detectors in the order they are asked."""
        return tuple(detector.detector_id for detector in self._detectors)

    def describe_detectors(self) -> dict[str, object]:
        """Merged extra settings of every detector, for the records."""
        merged: dict[str, object] = {}
        for detector in self._detectors:
            merged.update(detector.describe())
        return merged

    def screen(self, transcript: str) -> tuple[str, tuple[Detection, ...], tuple[int, ...]]:
        """Return the screened transcript, every detection and the redacted line numbers.

        A line is redacted when ANY detector flags it; detections are listed by detector, so
        a line may produce several of them.
        """
        detections: list[Detection] = []
        redacted: list[int] = []
        screened_lines: list[str] = []
        for number, line in enumerate(transcript.split(LINE_SEPARATOR), start=1):
            line_detections = [
                detection
                for detector in self._detectors
                for detection in detector.detect(number, line)
            ]
            if line_detections:
                detections.extend(line_detections)
                redacted.append(number)
                screened_lines.append(_redact(line))
            else:
                screened_lines.append(line)
        screened = LINE_SEPARATOR.join(screened_lines)
        return screened, tuple(detections), tuple(redacted)


def _redact(line: str) -> str:
    prefix, _utterance = split_speaker(line)
    return prefix + REDACTION_MARKER
