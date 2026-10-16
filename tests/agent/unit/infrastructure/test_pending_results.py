"""A result the API has not accepted is kept on disk, one file per ceremony (CA6)."""

import logging
import os
from pathlib import Path

import pytest

from agilina_agent.infrastructure.pending_results import PendingResults
from tests.shared.builders import CeremonyResultBuilder


def test_a_kept_result_is_listed_with_its_tenant(tmp_path: Path) -> None:
    pending = PendingResults(tmp_path)
    acme = CeremonyResultBuilder().build()
    ecomoda = CeremonyResultBuilder().build()

    pending.save("acme", acme)
    pending.save("ecomoda", ecomoda)

    assert pending.pending() == [("acme", acme), ("ecomoda", ecomoda)]


def test_the_result_lives_in_the_folder_of_its_tenant(tmp_path: Path) -> None:
    result = CeremonyResultBuilder().build()

    path = PendingResults(tmp_path).save("acme", result)

    assert path == tmp_path / "acme" / f"{result.ceremony_id}.json"
    assert path.read_text(encoding="utf-8") == result.model_dump_json()


def test_the_file_is_written_aside_and_moved_into_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moves: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def recording_replace(source: Path, target: Path) -> None:
        moves.append((Path(source), Path(target)))
        assert Path(source).read_text(encoding="utf-8")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", recording_replace)

    path = PendingResults(tmp_path).save("acme", CeremonyResultBuilder().build())

    [(source, target)] = moves
    assert target == path
    assert source != path
    assert source.parent == path.parent
    assert not source.exists()


def test_saving_again_replaces_the_kept_result(tmp_path: Path) -> None:
    pending = PendingResults(tmp_path)
    first = CeremonyResultBuilder().build()
    degraded = CeremonyResultBuilder().for_ceremony(first.ceremony_id).degraded("no stt").build()

    pending.save("acme", first)
    pending.save("acme", degraded)

    assert pending.pending() == [("acme", degraded)]
    assert [path.name for path in (tmp_path / "acme").iterdir()] == [f"{first.ceremony_id}.json"]


def test_a_removed_result_is_no_longer_pending(tmp_path: Path) -> None:
    pending = PendingResults(tmp_path)
    result = CeremonyResultBuilder().build()
    pending.save("acme", result)

    pending.remove("acme", result.ceremony_id)
    pending.remove("acme", result.ceremony_id)

    assert pending.pending() == []


def test_nothing_is_pending_in_a_folder_that_does_not_exist(tmp_path: Path) -> None:
    assert PendingResults(tmp_path / "missing").pending() == []


def test_an_unreadable_file_stays_on_disk_and_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pending = PendingResults(tmp_path)
    good = CeremonyResultBuilder().build()
    pending.save("acme", good)
    broken = tmp_path / "acme" / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    assert pending.pending() == [("acme", good)]
    assert broken.exists()
    assert any(
        record.levelno == logging.ERROR and "broken.json" in record.getMessage()
        for record in caplog.records
    )


def test_a_folder_that_is_not_a_tenant_is_ignored(tmp_path: Path) -> None:
    stray = tmp_path / "Not_A_Tenant"
    stray.mkdir()
    (stray / "x.json").write_text(CeremonyResultBuilder().build().model_dump_json())

    assert PendingResults(tmp_path).pending() == []


@pytest.mark.parametrize("tenant", ["../x", "acme/..", ""])
def test_a_tenant_that_is_not_a_slug_never_becomes_a_path(tmp_path: Path, tenant: str) -> None:
    pending = PendingResults(tmp_path / "pending")
    result = CeremonyResultBuilder().build()

    with pytest.raises(ValueError, match="slug"):
        pending.save(tenant, result)
    with pytest.raises(ValueError, match="slug"):
        pending.remove(tenant, result.ceremony_id)

    assert list(tmp_path.rglob("*")) == []
