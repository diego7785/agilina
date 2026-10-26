"""Agent pipeline: optional input scanner -> core -> system policy (always) -> tools -> outputs.

The modeled operation mode is *autonomous*: every allowed action item is executed without
human approval. Agilina's support mode (approval request) is out of scope. After the action
items, the system always delivers its automatic outputs (summary Excel and Slack DMs), whose
destinations come from the team configuration, never from the model.
"""

from dataclasses import dataclass
from typing import Final

from purple_team.core.ceremony import CeremonyCloser, CeremonyClosing
from purple_team.core.models import CeremonyOutput
from purple_team.core.prompts import SystemPrompt
from purple_team.defense.models import Defense, InputScreening
from purple_team.policy import PolicyScreening, SystemPolicy
from purple_team.providers.base import RequestTrace
from purple_team.tools.base import SystemOutputRecord, ToolCallRecord
from purple_team.tools.simulated import ToolDispatcher
from purple_team.tools.system_outputs import SystemOutputs

OPERATION_MODE: Final = "autonomous"


@dataclass(frozen=True, slots=True)
class PipelineTrace:
    """Everything that happened to one transcript, step by step."""

    input_screening: InputScreening
    closing: CeremonyClosing
    policy_screening: PolicyScreening | None
    tool_calls: tuple[ToolCallRecord, ...]
    system_outputs: tuple[SystemOutputRecord, ...]

    @property
    def final_output(self) -> CeremonyOutput | None:
        """What was delivered and executed (``None`` when the model output was invalid)."""
        return self.policy_screening.output if self.policy_screening is not None else None


class AgentPipeline:
    """Runs one transcript through the scanner, the core, the system policy and the tools."""

    def __init__(
        self,
        closer: CeremonyCloser,
        defense: Defense,
        policy: SystemPolicy,
        tools: ToolDispatcher,
        system_outputs: SystemOutputs,
    ) -> None:
        self._closer = closer
        self._defense = defense
        self._policy = policy
        self._tools = tools
        self._system_outputs = system_outputs

    def process(
        self,
        transcript: str,
        system_prompt: SystemPrompt,
        trace: RequestTrace,
    ) -> PipelineTrace:
        """Screen, close the ceremony, apply the policy, execute the allowed items and deliver.

        An invalid model output produces neither tool calls nor system outputs.
        """
        input_screening = self._defense.screen_input(transcript)
        closing = self._closer.close(input_screening.transcript, system_prompt, trace)
        if closing.output is None:
            return PipelineTrace(
                input_screening,
                closing,
                policy_screening=None,
                tool_calls=(),
                system_outputs=(),
            )
        policy_screening = self._policy.screen(closing.output)
        final_output = policy_screening.output
        tool_calls = self._tools.dispatch(final_output.action_items)
        system_outputs = self._system_outputs.deliver(final_output, trace.case_id)
        return PipelineTrace(input_screening, closing, policy_screening, tool_calls, system_outputs)
