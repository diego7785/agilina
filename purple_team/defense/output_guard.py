"""Output guard: drops the action items that the ``DefensePolicy`` does not allow.

The allowed destinations come from the team context (``policy.py``). The summary is never
modified: there is no reliable rule to validate it, which is a documented limitation
(case c05).
"""

from purple_team.core.models import ActionItem, CeremonyOutput
from purple_team.defense.models import BlockedAction
from purple_team.policy import BlockReason, DefensePolicy


class OutputGuard:
    """Keeps only the action items allowed by the ``DefensePolicy``."""

    def __init__(self, policy: DefensePolicy) -> None:
        self._policy = policy

    def screen(self, output: CeremonyOutput) -> tuple[CeremonyOutput, tuple[BlockedAction, ...]]:
        """Return the output with the allowed items only and the blocked ones."""
        allowed: list[ActionItem] = []
        blocked: list[BlockedAction] = []
        for index, item in enumerate(output.action_items):
            reason = self.reason_to_block(item)
            if reason is None:
                allowed.append(item)
            else:
                blocked.append(BlockedAction(index=index, item=item, reason=reason))
        screened = CeremonyOutput(summary=output.summary, action_items=tuple(allowed))
        return screened, tuple(blocked)

    def reason_to_block(self, item: ActionItem) -> BlockReason | None:
        """First applicable reason of the policy (destination, then content size) or ``None``."""
        return self._policy.block_reason(item)
