"""Builder of ``TranscriptSegment``."""

from dataclasses import dataclass, field, replace
from typing import Self
from uuid import UUID

from agilina_shared.contract import TranscriptSegment
from tests.shared.builders.identifiers import next_id


@dataclass(frozen=True)
class TranscriptSegmentBuilder:
    """The first 2.4 seconds of someone's turn, attributed by their room identity."""

    user_id: UUID = field(default_factory=next_id)
    text: str = "Yesterday I finished the migration"
    start_ms: int = 0
    end_ms: int = 2400

    def said_by(self, user_id: UUID) -> Self:
        return replace(self, user_id=user_id)

    def saying(self, text: str) -> Self:
        return replace(self, text=text)

    def spanning(self, start_ms: int, end_ms: int) -> Self:
        return replace(self, start_ms=start_ms, end_ms=end_ms)

    def build(self) -> TranscriptSegment:
        return TranscriptSegment(**self._fields())

    def build_unchecked(self) -> TranscriptSegment:
        """The segment as it is, without the contract's validation: what the database must
        still refuse (an end before the start, for instance)."""
        return TranscriptSegment.model_construct(**self._fields())

    def _fields(self) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "room_identity": str(self.user_id),
            "text": self.text,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
        }
