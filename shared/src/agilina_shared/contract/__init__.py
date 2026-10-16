"""Contract between the agent worker and the API.

The worker only needs two operations (architecture document, 5.3):

* get the ceremony context before joining the room;
* deliver the result when the ceremony ends.

Everything that crosses that boundary is here. An incompatible change in these
models breaks the contract between deployables and must be flagged with
``BREAKING CHANGE`` in the commit footer, besides bumping ``CONTRACT_VERSION``.
"""

from agilina_shared.contract.ceremony_context import CeremonyContext
from agilina_shared.contract.ceremony_event import CeremonyEvent
from agilina_shared.contract.ceremony_result import CeremonyResult
from agilina_shared.contract.contract_model import ContractModel
from agilina_shared.contract.participant_context import ParticipantContext
from agilina_shared.contract.result_receipt import ResultReceipt
from agilina_shared.contract.transcript_segment import TranscriptSegment

__all__ = [
    "CeremonyContext",
    "CeremonyEvent",
    "CeremonyResult",
    "ContractModel",
    "ParticipantContext",
    "ResultReceipt",
    "TranscriptSegment",
]
