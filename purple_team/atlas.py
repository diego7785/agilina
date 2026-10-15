"""Verified catalog of the MITRE ATLAS techniques the cases can declare (no dependencies).

Source: ``mitre-atlas/atlas-data``, ``dist/v6/ATLAS-2026.09.yaml``. Add a technique here only
after checking its id and name on atlas.mitre.org; ``cases.py`` rejects unknown ids.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

ATLAS_DATA_VERSION: Final = "2026.09"


@dataclass(frozen=True, slots=True)
class AtlasTechnique:
    """One ATLAS technique (or sub-technique) with the name written to the records."""

    technique_id: str
    name: str

    def to_dict(self) -> dict[str, str]:
        """JSON view."""
        return {"id": self.technique_id, "name": self.name}


_TECHNIQUES: Final = (
    AtlasTechnique("AML.T0051.000", "LLM Prompt Injection: Direct"),
    AtlasTechnique("AML.T0051.001", "LLM Prompt Injection: Indirect"),
    AtlasTechnique("AML.T0053", "AI Agent Tool Invocation"),
    AtlasTechnique("AML.T0068", "LLM Prompt Obfuscation"),
    AtlasTechnique("AML.T0086", "Exfiltration via AI Agent Tool Invocation"),
)

ATLAS_CATALOG: Final[Mapping[str, AtlasTechnique]] = {
    technique.technique_id: technique for technique in _TECHNIQUES
}
