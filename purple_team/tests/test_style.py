"""Stdlib approximation of the root ruff rules (plan section 10.3); ruff is not installed."""

import ast
import io
import tokenize
import unicodedata
import unittest
from collections.abc import Iterator
from pathlib import Path

from purple_team.tests.support import PURPLE_TEAM_DIR, iter_harness_python_files

MAX_LINE_LENGTH = 100
AMBIGUOUS_NAMES = frozenset({"l", "O", "I"})
# Network, process and randomness modules, plus the optional model stack: LLM Guard (with
# transformers/torch) is only ever imported lazily (importlib) by defense/llm_guard.py, never
# with an import statement.
FORBIDDEN_MODULES = frozenset(
    {
        "random",
        "subprocess",
        "pickle",
        "urllib",
        "http",
        "socket",
        "llm_guard",
        "torch",
        "transformers",
        "huggingface_hub",
    }
)
# The shared HTTP transport is the only module allowed to use the network (urllib); the
# provider tests only need the exception classes of urllib.error to fake failures.
ALLOWED_FORBIDDEN_IMPORTS = {
    "providers/http_transport.py": frozenset({"urllib.error", "urllib.parse", "urllib.request"}),
    "tests/test_ollama_provider.py": frozenset({"urllib.error"}),
    "tests/test_cloud_provider.py": frozenset({"urllib.error"}),
    # In-memory handler that proves redirections are refused (no socket is ever opened).
    "tests/test_http_transport.py": frozenset({"urllib.request", "urllib.response"}),
}
FORBIDDEN_TYPING_NAMES = frozenset({"TypeVar", "TypeAlias", "TYPE_CHECKING"})
BROAD_EXCEPTIONS = frozenset({"Exception", "BaseException"})
SINGLE_QUOTE = "'"
DOUBLE_QUOTE = '"'
STRING_PREFIX_CHARS = "rRbBuUfF"
# Unicode "format" characters (zero-width space, joiners, BOM...) must be written as escapes.
INVISIBLE_CATEGORY = "Cf"


def label(path: Path, line: int) -> str:
    """Return ``relative/path.py:line`` for messages."""
    return f"{path.relative_to(PURPLE_TEAM_DIR).as_posix()}:{line}"


def layout_problems(path: Path) -> list[str]:
    """Line length, tabs, trailing spaces, CRLF and final newline."""
    raw = path.read_bytes()
    problems = []
    if b"\r" in raw:
        problems.append(label(path, 1) + " contains CR characters")
    text = raw.decode()
    if not text.endswith("\n") or text.endswith("\n\n"):
        problems.append(label(path, 1) + " must end with exactly one newline")
    long_lines_allowed = path.name == "__init__.py"
    for number, line in enumerate(text.split("\n"), start=1):
        if len(line) > MAX_LINE_LENGTH and not long_lines_allowed:
            problems.append(label(path, number) + " is longer than 100 characters")
        if "\t" in line:
            problems.append(label(path, number) + " contains a tab")
        if line != line.rstrip():
            problems.append(label(path, number) + " has trailing whitespace")
        if any(unicodedata.category(char) == INVISIBLE_CATEGORY for char in line):
            problems.append(label(path, number) + " contains a literal invisible character")
    return problems


def quote_of(literal: str) -> str:
    """Return the opening quote character of a string or f-string start token."""
    return literal.lstrip(STRING_PREFIX_CHARS)[:1]


def quote_problems(path: Path) -> list[str]:
    """String literals must use double quotes unless they contain a double quote."""
    problems = []
    source = path.read_text(encoding="utf-8")
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    for index, tok in enumerate(tokens):
        if tok.type == tokenize.STRING:
            body = tok.string.lstrip(STRING_PREFIX_CHARS)
            if quote_of(tok.string) == SINGLE_QUOTE and DOUBLE_QUOTE not in body[1:-1]:
                problems.append(label(path, tok.start[0]) + " uses single quotes")
        elif tok.type == tokenize.FSTRING_START and quote_of(tok.string) == SINGLE_QUOTE:
            if DOUBLE_QUOTE not in fstring_text(tokens, index):
                problems.append(label(path, tok.start[0]) + " uses a single-quoted f-string")
    return problems


def fstring_text(tokens: list[tokenize.TokenInfo], start: int) -> str:
    """Return the literal parts of the f-string that opens at ``tokens[start]``."""
    depth = 0
    parts = []
    for tok in tokens[start:]:
        if tok.type == tokenize.FSTRING_START:
            depth += 1
        elif tok.type == tokenize.FSTRING_END:
            depth -= 1
            if depth == 0:
                break
        elif tok.type == tokenize.FSTRING_MIDDLE:
            parts.append(tok.string)
    return "".join(parts)


def is_forbidden_module(path: Path, module: str) -> bool:
    """Forbidden top-level module, unless this file is explicitly allowed to import it."""
    if module.split(".")[0] not in FORBIDDEN_MODULES:
        return False
    relative = path.relative_to(PURPLE_TEAM_DIR).as_posix()
    return module not in ALLOWED_FORBIDDEN_IMPORTS.get(relative, frozenset())


def imported_names(tree: ast.Module) -> Iterator[tuple[str, int]]:
    """Yield the local name bound by every import with its line."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield (alias.asname or alias.name.split(".")[0]), node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                yield (alias.asname or alias.name), node.lineno


def raises_without_cause(handler: ast.ExceptHandler) -> Iterator[ast.Raise]:
    """Yield ``raise X`` statements of an except body that lack ``from`` (B904)."""
    pending: list[ast.AST] = list(handler.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(node, ast.Raise) and node.exc is not None and node.cause is None:
            yield node
        pending.extend(ast.iter_child_nodes(node))


def ast_problems(path: Path) -> list[str]:
    """B904, B905, S110/S112, E722, B017, E741, F401 (approximate) and forbidden imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems = []
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for name, line in imported_names(tree):
        if name not in used_names:
            problems.append(label(path, line) + f" imports {name} without using it")
        if name in FORBIDDEN_TYPING_NAMES:
            problems.append(label(path, line) + f" imports forbidden name {name}")
    for node in ast.walk(tree):
        problems.extend(node_problems(path, node))
    return problems


def node_problems(path: Path, node: ast.AST) -> list[str]:
    """Rules that can be decided looking at a single node."""
    problems = []
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        if is_forbidden_module(path, node.module):
            problems.append(label(path, node.lineno) + f" imports from {node.module}")
    if isinstance(node, ast.Import):
        for alias in node.names:
            if is_forbidden_module(path, alias.name):
                problems.append(label(path, node.lineno) + f" imports {alias.name}")
    if isinstance(node, ast.ExceptHandler):
        if node.type is None:
            problems.append(label(path, node.lineno) + " has a bare except")
        only_statement = node.body[0] if len(node.body) == 1 else None
        if isinstance(only_statement, ast.Pass | ast.Continue):
            problems.append(label(path, node.lineno) + " silences an exception")
        for raise_node in raises_without_cause(node):
            problems.append(label(path, raise_node.lineno) + " raises without 'from'")
    if isinstance(node, ast.Call):
        problems.extend(call_problems(path, node))
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        if node.id in AMBIGUOUS_NAMES:
            problems.append(label(path, node.lineno) + f" uses ambiguous name {node.id}")
    if isinstance(node, ast.arg) and node.arg in AMBIGUOUS_NAMES:
        problems.append(label(path, node.lineno) + f" uses ambiguous name {node.arg}")
    return problems


def call_problems(path: Path, node: ast.Call) -> list[str]:
    """``zip`` without ``strict`` (B905) and ``assertRaises(Exception)`` (B017)."""
    problems = []
    func = node.func
    if isinstance(func, ast.Name) and func.id == "zip":
        if not any(keyword.arg == "strict" for keyword in node.keywords):
            problems.append(label(path, node.lineno) + " calls zip without strict=")
    if isinstance(func, ast.Attribute) and func.attr == "assertRaises" and node.args:
        first = node.args[0]
        if isinstance(first, ast.Name) and first.id in BROAD_EXCEPTIONS:
            problems.append(label(path, node.lineno) + " asserts a broad exception")
    return problems


class StyleTest(unittest.TestCase):
    def test_layout(self) -> None:
        files = iter_harness_python_files()
        problems = [problem for path in files for problem in layout_problems(path)]
        self.assertEqual(problems, [])

    def test_double_quotes(self) -> None:
        files = iter_harness_python_files()
        problems = [problem for path in files for problem in quote_problems(path)]
        self.assertEqual(problems, [])

    def test_ast_rules(self) -> None:
        files = iter_harness_python_files()
        problems = [problem for path in files for problem in ast_problems(path)]
        self.assertEqual(problems, [])

    def test_network_imports_are_only_allowed_in_the_http_transport(self) -> None:
        transport = PURPLE_TEAM_DIR / "providers" / "http_transport.py"
        ollama_tests = PURPLE_TEAM_DIR / "tests" / "test_ollama_provider.py"
        self.assertFalse(is_forbidden_module(transport, "urllib.request"))
        self.assertTrue(is_forbidden_module(transport, "http.client"))
        self.assertTrue(is_forbidden_module(transport, "socket"))
        self.assertFalse(is_forbidden_module(ollama_tests, "urllib.error"))
        self.assertTrue(is_forbidden_module(ollama_tests, "urllib.request"))
        self.assertTrue(is_forbidden_module(PURPLE_TEAM_DIR / "runner.py", "urllib.request"))
        for name in ("ollama.py", "cloud.py"):
            path = PURPLE_TEAM_DIR / "providers" / name
            self.assertTrue(is_forbidden_module(path, "urllib.request"))

    def test_llm_guard_stack_is_never_imported_statically(self) -> None:
        llm_guard = PURPLE_TEAM_DIR / "defense" / "llm_guard.py"
        for module in ("llm_guard.input_scanners", "llm_guard.model", "torch", "transformers"):
            with self.subTest(module=module):
                self.assertTrue(is_forbidden_module(llm_guard, module))
        self.assertFalse(is_forbidden_module(llm_guard, "importlib"))


if __name__ == "__main__":
    unittest.main()
