"""Results the API has not accepted yet, kept on disk until it does (CA6).

One file per ceremony, ``<dir>/<tenant>/<ceremony_id>.json``. It is written to a temporary
file and moved into place with ``os.replace``, so a process that dies mid-write never leaves
a half-written transcript in place of the good one.
"""

import os
from pathlib import Path
from uuid import UUID

from agilina_agent.infrastructure.logging_setup import get_logger
from agilina_agent.infrastructure.tenant_slug import is_tenant_slug
from agilina_shared.contract import CeremonyResult

logger = get_logger(__name__)


class PendingResults:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def save(self, tenant: str, result: CeremonyResult) -> Path:
        target = self._path_of(tenant, result.ceremony_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(result.model_dump_json(), encoding="utf-8")
        os.replace(temporary, target)
        return target

    def remove(self, tenant: str, ceremony_id: UUID) -> None:
        self._path_of(tenant, ceremony_id).unlink(missing_ok=True)

    def pending(self) -> list[tuple[str, CeremonyResult]]:
        """Every kept result with its tenant. A file that cannot be read stays where it is."""
        results: list[tuple[str, CeremonyResult]] = []
        for path in sorted(self._directory.glob("*/*.json")):
            tenant = path.parent.name
            if not is_tenant_slug(tenant):
                continue
            try:
                result = CeremonyResult.model_validate_json(path.read_bytes())
            except (OSError, ValueError):
                logger.error("Pending result %s cannot be read; it stays on disk", path)
                continue
            results.append((tenant, result))
        return results

    def _path_of(self, tenant: str, ceremony_id: UUID) -> Path:
        # The tenant comes from a room name: it never becomes a path before this check.
        if not is_tenant_slug(tenant):
            raise ValueError("The tenant is not a valid slug")
        return self._directory / tenant / f"{ceremony_id}.json"
