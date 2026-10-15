"""Checks with ``ast`` that internal imports follow the acyclic graph of plan section 2.11."""

import ast
import unittest
from collections.abc import Iterator
from pathlib import Path

from purple_team.tests.support import PURPLE_TEAM_DIR, iter_harness_source_files

PACKAGE = "purple_team"
ROOT_MODULE = PACKAGE
CORE_MODULES = frozenset(
    {
        "core",
        "core.text",
        "core.models",
        "core.prompts",
        "core.output_parser",
        "core.ceremony",
    }
)
LEVEL_ZERO = frozenset(
    {
        ROOT_MODULE,
        "errors",
        "paths",
        "clock",
        "atlas",
        "core.text",
        "providers.base",
        "core.models",
        "core",
        "providers",
        "tools",
        "defense",
        "evaluation",
    }
)

# Level of every module (a module may only import modules of a strictly lower level).
LEVELS: dict[str, int] = {
    **dict.fromkeys(LEVEL_ZERO, 0),
    "config": 1,
    "team_context": 1,
    "core.prompts": 2,
    "core.output_parser": 2,
    "tools.base": 2,
    "providers.http_transport": 2,
    "policy": 2,
    "core.ceremony": 3,
    "providers.mock": 3,
    "providers.ollama": 3,
    "providers.cloud": 3,
    "tools.simulated": 3,
    "tools.system_outputs": 3,
    "defense.models": 3,
    "evaluation.spec": 3,
    "providers.factory": 4,
    "defense.input_guard": 4,
    "defense.output_guard": 4,
    "defense.llm_guard": 4,
    "defense.prompt_guard": 4,
    "cases": 4,
    "defense.layered": 5,
    "pipeline": 5,
    "evaluation.evaluator": 6,
    "records": 7,
    "recording": 8,
    "aggregation": 8,
    "runner": 9,
    "composition": 10,
    "cli": 11,
    "__main__": 12,
}

# Allowed internal imports per module. Additions to the table of the plan (review round 2
# and implementation): config -> paths, runner -> providers.mock, runner -> core.output_parser,
# runner -> purple_team (HARNESS_VERSION) and core.prompts -> core.text (level 0).
# Ollama stage (handoff/07): providers.ollama -> core.models (JSON Schema of the closing).
# Corrections stage (handoff/08 section 11): atlas, team_context, policy, http_transport,
# defense.llm_guard and aggregation, all pointing to lower levels.
# Prompt Guard stage (handoff/14 section 2.9): defense.prompt_guard, same edges as llm_guard.
# Cycle 4 (handoff/18 section 9.2): tools.system_outputs; pipeline -> tools.system_outputs.
ALLOWED: dict[str, frozenset[str]] = {
    **{module: frozenset() for module in LEVEL_ZERO},
    "config": frozenset({"errors", "paths"}),
    "team_context": frozenset({"errors", "core.text"}),
    "core.prompts": frozenset({"core.models", "core.text", "errors", "team_context"}),
    "core.output_parser": frozenset({"core.models", "errors"}),
    "tools.base": frozenset({"core.models"}),
    "providers.http_transport": frozenset({"providers.base", "errors"}),
    "policy": frozenset({"team_context", "core.models"}),
    "core.ceremony": frozenset(
        {"core.models", "core.prompts", "core.output_parser", "providers.base", "team_context"}
    ),
    "providers.mock": frozenset({"providers.base", "core.text"}),
    "providers.ollama": frozenset(
        {"providers.base", "providers.http_transport", "config", "errors", "core.models"}
    ),
    "providers.cloud": frozenset(
        {"providers.base", "providers.http_transport", "config", "errors"}
    ),
    "tools.simulated": frozenset({"tools.base", "core.models"}),
    "tools.system_outputs": frozenset({"tools.base", "core.models", "team_context"}),
    "defense.models": frozenset({"config", "core.models", "policy"}),
    "evaluation.spec": frozenset({"core.models", "core.text", "errors"}),
    "providers.factory": frozenset(
        {"config", "providers.base", "providers.mock", "providers.ollama", "providers.cloud"}
    ),
    "defense.input_guard": frozenset({"defense.models"}),
    "defense.output_guard": frozenset({"core.models", "defense.models", "policy"}),
    "defense.llm_guard": frozenset({"config", "defense.models", "errors"}),
    "defense.prompt_guard": frozenset({"config", "defense.models", "errors"}),
    "cases": frozenset(
        {
            "errors",
            "core.text",
            "core.models",
            "core.output_parser",
            "evaluation.spec",
            "providers.mock",
            "atlas",
            "team_context",
            "policy",
        }
    ),
    "defense.layered": frozenset(
        {
            "config",
            "core.models",
            "defense.models",
            "defense.input_guard",
            "defense.output_guard",
        }
    ),
    "pipeline": frozenset(
        {
            *CORE_MODULES,
            "providers.base",
            "defense.models",
            "tools.base",
            "tools.simulated",
            "tools.system_outputs",
        }
    ),
    "evaluation.evaluator": frozenset(
        {
            *CORE_MODULES,
            "cases",
            "pipeline",
            "evaluation.spec",
            "defense.models",
            "tools.base",
        }
    ),
    "records": frozenset(
        {
            *CORE_MODULES,
            "config",
            "paths",
            "cases",
            "pipeline",
            "evaluation.evaluator",
            "evaluation.spec",
            "defense.models",
            "tools.base",
        }
    ),
    "recording": frozenset(
        {
            "records",
            "paths",
            "errors",
            "cases",
            "core.prompts",
            "pipeline",
            "evaluation.evaluator",
        }
    ),
    "runner": frozenset(
        {
            ROOT_MODULE,
            "clock",
            "config",
            "errors",
            "cases",
            "core.prompts",
            "core.output_parser",
            "providers.base",
            "providers.mock",
            "pipeline",
            "evaluation.evaluator",
            "records",
            "recording",
        }
    ),
    "aggregation": frozenset({"config", "records"}),
    "composition": frozenset(name for name, level in LEVELS.items() if level <= 9),
    "cli": frozenset(
        {
            "composition",
            "config",
            "clock",
            "errors",
            "paths",
            "providers.base",
            "runner",
            "cases",
            "records",
            "aggregation",
        }
    ),
    "__main__": frozenset({"cli"}),
}


def module_name(path: Path) -> str:
    """Map a file to its dotted name relative to the package (``__init__`` -> package)."""
    parts = list(path.relative_to(PURPLE_TEAM_DIR).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else ROOT_MODULE


def internal_name(imported: str) -> str | None:
    """Translate ``purple_team.x.y`` into ``x.y``; return ``None`` for external modules."""
    if imported == PACKAGE:
        return ROOT_MODULE
    prefix = f"{PACKAGE}."
    if imported.startswith(prefix):
        return imported.removeprefix(prefix)
    return None


def imported_modules(tree: ast.Module) -> Iterator[tuple[str, ast.stmt]]:
    """Yield the internal modules imported anywhere in the tree with their statement."""
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names = [node.module]
        for name in names:
            internal = internal_name(name)
            if internal is not None:
                yield internal, node


class ImportGraphTest(unittest.TestCase):
    def setUp(self) -> None:
        self.trees = {
            module_name(path): ast.parse(path.read_text(encoding="utf-8"))
            for path in iter_harness_source_files()
        }

    def test_every_module_has_a_level(self) -> None:
        unknown = sorted(set(self.trees) - set(LEVELS))
        self.assertEqual(unknown, [], "modules missing from the graph table")

    def test_only_allowed_edges_towards_lower_levels(self) -> None:
        violations = []
        for module, tree in self.trees.items():
            for imported, _node in imported_modules(tree):
                allowed = imported in ALLOWED.get(module, frozenset())
                lower = LEVELS.get(imported, 99) < LEVELS.get(module, -1)
                if not (allowed and lower):
                    violations.append(f"{module} -> {imported}")
        self.assertEqual(violations, [])

    def test_graph_has_no_cycles(self) -> None:
        edges = {
            module: {imported for imported, _node in imported_modules(tree)}
            for module, tree in self.trees.items()
        }
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(module: str, chain: tuple[str, ...]) -> None:
            if module in done:
                return
            if module in visiting:
                cycle = " -> ".join((*chain, module))
                self.fail(f"import cycle: {cycle}")
            visiting.add(module)
            for imported in sorted(edges.get(module, set())):
                visit(imported, (*chain, module))
            visiting.discard(module)
            done.add(module)

        for module in sorted(edges):
            visit(module, ())

    def test_internal_imports_are_module_level_statements(self) -> None:
        nested = []
        for module, tree in self.trees.items():
            top_level = set(map(id, tree.body))
            for imported, node in imported_modules(tree):
                if id(node) not in top_level:
                    nested.append(f"{module} -> {imported}")
        self.assertEqual(nested, [])

    def test_type_checking_guard_is_not_used(self) -> None:
        offenders = [
            module
            for module, tree in self.trees.items()
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == "TYPE_CHECKING"
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
