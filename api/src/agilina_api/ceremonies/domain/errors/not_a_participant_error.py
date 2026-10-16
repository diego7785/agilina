from agilina_api.shared_kernel import DomainError


class NotAParticipantError(DomainError):
    """Something in the result is attributed to someone who is not a participant of the
    ceremony.

    ``fields`` names where (``segments.3.user_id``), never who: the value does not travel back.
    """

    def __init__(self, fields: tuple[str, ...]) -> None:
        super().__init__("Not attributed to a participant: " + ", ".join(fields))
        self.fields = fields
