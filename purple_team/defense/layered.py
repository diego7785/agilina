"""Implementations of the ``Defense`` port; the composition root picks one by mode."""

from typing import Final

from purple_team.config import DefenseMode
from purple_team.core.models import CeremonyOutput
from purple_team.defense.input_guard import InputGuard
from purple_team.defense.models import InputScreening, OutputScreening
from purple_team.defense.output_guard import OutputGuard

MODE_KEY: Final = "mode"
INPUT_DETECTORS_KEY: Final = "input_detectors"
OUTPUT_GUARD_KEY: Final = "output_guard"


class NoDefense:
    """Defense ``off``: passes the transcript and the output through unchanged."""

    @property
    def mode(self) -> DefenseMode:
        """Always ``off``."""
        return DefenseMode.OFF

    def describe(self) -> dict[str, object]:
        """No input detector and no output guard."""
        return {MODE_KEY: self.mode.value, INPUT_DETECTORS_KEY: [], OUTPUT_GUARD_KEY: False}

    def screen_input(self, transcript: str) -> InputScreening:
        """Return the transcript as is, without detections."""
        return InputScreening(
            self.mode,
            transcript,
            detections=(),
            redacted_lines=(),
            detectors=(),
        )

    def screen_output(self, output: CeremonyOutput) -> OutputScreening:
        """Return the output as is, without blocked items."""
        return OutputScreening(self.mode, output, blocked=())


class LayeredDefense:
    """Input guard before the model and output guard before the tools.

    The same class serves ``own``, ``llm-guard`` and ``own-llm-guard``: only the detectors
    of the input guard change, the output guard is always the same policy.
    """

    def __init__(
        self,
        mode: DefenseMode,
        input_guard: InputGuard,
        output_guard: OutputGuard,
    ) -> None:
        self._mode = mode
        self._input_guard = input_guard
        self._output_guard = output_guard

    @property
    def mode(self) -> DefenseMode:
        """The mode this layered defense was built for."""
        return self._mode

    def describe(self) -> dict[str, object]:
        """Mode, input detectors (with their settings) and the output guard."""
        return {
            MODE_KEY: self._mode.value,
            INPUT_DETECTORS_KEY: list(self._input_guard.detector_ids),
            OUTPUT_GUARD_KEY: True,
            **self._input_guard.describe_detectors(),
        }

    def screen_input(self, transcript: str) -> InputScreening:
        """Detect and redact suspicious lines."""
        screened, detections, redacted = self._input_guard.screen(transcript)
        detectors = self._input_guard.detector_ids
        return InputScreening(self._mode, screened, detections, redacted, detectors)

    def screen_output(self, output: CeremonyOutput) -> OutputScreening:
        """Drop the action items that violate the policy."""
        screened, blocked = self._output_guard.screen(output)
        return OutputScreening(self._mode, screened, blocked)
