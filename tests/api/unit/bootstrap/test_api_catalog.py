"""``docs/api.md`` says what the API does: this fails when the two stop agreeing."""

import re
from pathlib import Path

import pytest

from agilina_api.bootstrap.app import create_app
from agilina_api.ceremonies.presentation.http.errors import CeremoniesErrors
from agilina_api.identity.presentation.http.errors import IdentityErrors
from agilina_api.shared.presentation.http.api_error import SharedErrors, catalog_of
from agilina_api.teams.presentation.http.errors import TeamsErrors

DOC = (Path(__file__).parents[4] / "docs" / "api.md").read_text(encoding="utf-8")
CATALOG = (
    *catalog_of(SharedErrors),
    *catalog_of(IdentityErrors),
    *catalog_of(TeamsErrors),
    *catalog_of(CeremoniesErrors),
)
# What every route may answer by the very nature of HTTP, so the doc says it once, in the
# conventions. The 500 is not here: every endpoint declares it and lists it.
EVERYWHERE = {"404", "405"}


def _operations() -> dict[tuple[str, str], dict]:
    paths = create_app().openapi()["paths"]
    return {
        (method, path): operation
        for path, methods in paths.items()
        for method, operation in methods.items()
    }


def _sections() -> dict[tuple[str, str], str]:
    parts = re.split(
        r"^### `(GET|POST|PUT|PATCH|DELETE) ([^\s?`]+)(?:\?[^`]*)?`\n", DOC, flags=re.MULTILINE
    )
    # [intro, method, path, body, method, path, body, ...]
    return {
        (parts[i].lower(), parts[i + 1]): parts[i + 2].split("\n## ")[0]
        for i in range(1, len(parts), 3)
    }


def _documented_statuses(section: str) -> set[str]:
    cells = re.findall(r"^\| ([\d /]+) \|", section, flags=re.MULTILINE)
    return {status.strip() for cell in cells for status in cell.split("/")}


def test_every_route_is_in_the_catalog_and_every_entry_is_a_route():
    assert set(_sections()) == set(_operations())


@pytest.mark.parametrize("operation", sorted(_operations()), ids=str)
def test_the_statuses_of_a_route_are_the_ones_the_doc_lists(operation):
    declared = set(_operations()[operation]["responses"]) - EVERYWHERE
    documented = _documented_statuses(_sections()[operation]) - EVERYWHERE

    assert declared == documented


@pytest.mark.parametrize("operation", sorted(_operations()), ids=str)
def test_every_error_code_a_route_declares_is_in_its_section(operation):
    section = _sections()[operation]
    declared = _operations()[operation]["responses"].values()
    codes = {
        code
        for response in declared
        for code in re.findall(r"`([a-z_]+)`:", response.get("description", ""))
    }

    assert {code for code in codes if f"`{code}`" not in section} == set()


def test_the_code_table_of_the_doc_is_the_catalog():
    table = DOC.split("### Catálogo de códigos")[1].split("\n## ")[0]
    documented = set(re.findall(r"^\| \d+ \| `([a-z_]+)` \|", table, flags=re.MULTILINE))
    everywhere = {"not_found", "method_not_allowed", "internal_error"}  # their own table

    assert documented == {error.code for error in CATALOG} - everywhere
