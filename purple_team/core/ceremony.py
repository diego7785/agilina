"""The core: imitates Agilina's ceremony closing (transcript + system prompt -> JSON)."""

from dataclasses import dataclass

from purple_team.core.models import CeremonyOutput
from purple_team.core.output_parser import OutputFormatError, parse_ceremony_output
from purple_team.core.prompts import SystemPrompt, build_user_content
from purple_team.providers.base import ModelProvider, ModelRequest, ModelResponse, RequestTrace
from purple_team.team_context import TeamContext


@dataclass(frozen=True, slots=True)
class CeremonyClosing:
    """Request, raw response and parsed output (``None`` when the output is invalid)."""

    request: ModelRequest
    response: ModelResponse
    output: CeremonyOutput | None
    parse_error: str | None


class CeremonyCloser:
    """Calls the model once to close the ceremony; it never executes tools."""

    def __init__(
        self,
        provider: ModelProvider,
        temperature: float,
        team_context: TeamContext,
    ) -> None:
        self._provider = provider
        self._temperature = temperature
        self._team_context = team_context

    def close(
        self,
        transcript: str,
        system_prompt: SystemPrompt,
        trace: RequestTrace,
    ) -> CeremonyClosing:
        """Build the request, call the provider and try to parse its answer."""
        request = ModelRequest(
            system_prompt=system_prompt.text,
            user_content=build_user_content(transcript, self._team_context),
            trace=trace,
            temperature=self._temperature,
        )
        response = self._provider.complete(request)
        try:
            output = parse_ceremony_output(response.text)
        except OutputFormatError as exc:
            return CeremonyClosing(request, response, output=None, parse_error=str(exc))
        return CeremonyClosing(request, response, output=output, parse_error=None)
