"""Implementations of the ``Defense`` port; the composition root picks one by mode."""

from typing import Final

from purple_team.config import DefenseMode
from purple_team.defense.input_guard import InputGuard
from purple_team.defense.models import InputScreening

MODE_KEY: Final = "mode"
INPUT_DETECTORS_KEY: Final = "input_detectors"


class NoDefense:
    """Defense ``off``: passes the transcript through unchanged."""

    @property
    def mode(self) -> DefenseMode:
        """Always ``off``."""
        return DefenseMode.OFF

    def describe(self) -> dict[str, object]:
        """No input detector."""
        return {MODE_KEY: self.mode.value, INPUT_DETECTORS_KEY: []}

    def screen_input(self, transcript: str) -> InputScreening:
        """Return the transcript as is, without detections."""
        return InputScreening(
            self.mode,
            transcript,
            detections=(),
            redacted_lines=(),
            detectors=(),
        )


class InputGuardDefense:
    """The scanner modes: the input guard with the model detector of the mode."""

    def __init__(self, mode: DefenseMode, input_guard: InputGuard) -> None:
        self._mode = mode
        self._input_guard = input_guard

    @property
    def mode(self) -> DefenseMode:
        """The mode this defense was built for."""
        return self._mode

    def describe(self) -> dict[str, object]:
        """Mode and input detectors (with their settings)."""
        return {
            MODE_KEY: self._mode.value,
            INPUT_DETECTORS_KEY: list(self._input_guard.detector_ids),
            **self._input_guard.describe_detectors(),
        }

    def screen_input(self, transcript: str) -> InputScreening:
        """Detect and redact suspicious lines."""
        screened, detections, redacted = self._input_guard.screen(transcript)
        detectors = self._input_guard.detector_ids
        return InputScreening(self._mode, screened, detections, redacted, detectors)
