"""Builder of ``CeremonyResult``."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Self
from uuid import UUID

from agilina_shared.contract import CeremonyEvent, CeremonyResult, TranscriptSegment
from agilina_shared.enums import CeremonyStatus
from tests.shared.builders.defaults import CLOSED_AT, STARTED_AT
from tests.shared.builders.identifiers import next_id


@dataclass(frozen=True)
class CeremonyResultBuilder:
    """A completed ceremony of 15 minutes where nobody spoke and nothing was recorded."""

    ceremony_id: UUID = field(default_factory=next_id)
    status: CeremonyStatus = CeremonyStatus.COMPLETED
    started_at: datetime = STARTED_AT
    closed_at: datetime = CLOSED_AT
    present_participants: tuple[UUID, ...] = ()
    absent_participants: tuple[UUID, ...] = ()
    segments: tuple[TranscriptSegment, ...] = ()
    events: tuple[CeremonyEvent, ...] = ()
    degradation_detail: str | None = None

    def for_ceremony(self, ceremony_id: UUID) -> Self:
        return replace(self, ceremony_id=ceremony_id)

    def with_present(self, *user_ids: UUID) -> Self:
        return replace(self, present_participants=user_ids)

    def with_absent(self, *user_ids: UUID) -> Self:
        return replace(self, absent_participants=user_ids)

    def with_segments(self, *segments: TranscriptSegment) -> Self:
        return replace(self, segments=segments)

    def with_events(self, *events: CeremonyEvent) -> Self:
        return replace(self, events=events)

    def degraded(self, detail: str) -> Self:
        return replace(self, status=CeremonyStatus.DEGRADED, degradation_detail=detail)

    def build(self) -> CeremonyResult:
        return CeremonyResult(**self._fields())

    def build_unchecked(self) -> CeremonyResult:
        """The result as it is, without the contract's validation: with a segment from
        ``TranscriptSegmentBuilder.build_unchecked``, what the database must still refuse."""
        return CeremonyResult.model_construct(**self._fields())

    def _fields(self) -> dict[str, object]:
        return {
            "ceremony_id": self.ceremony_id,
            "status": self.status,
            "started_at": self.started_at,
            "closed_at": self.closed_at,
            "present_participants": list(self.present_participants),
            "absent_participants": list(self.absent_participants),
            "segments": list(self.segments),
            "events": list(self.events),
            "degraded": self.degradation_detail is not None,
            "degradation_detail": self.degradation_detail,
        }
