"""Which provider modules may import network modules (only the shared HTTP transport)."""

import ast
import unittest

from purple_team.tests.support import PURPLE_TEAM_DIR

NETWORK_MODULES = frozenset({"urllib", "http", "socket", "ollama", "google", "requests", "httpx"})
# Network modules each provider module may import (everything else must import none).
ALLOWED_NETWORK_IMPORTS = {"http_transport.py": frozenset({"urllib"})}
PROVIDER_MODULES = (
    "http_transport.py",
    "ollama.py",
    "cloud.py",
    "mock.py",
    "factory.py",
    "base.py",
)


class NetworkImportsTest(unittest.TestCase):
    def test_only_the_http_transport_imports_urllib(self) -> None:
        for name in PROVIDER_MODULES:
            path = PURPLE_TEAM_DIR / "providers" / name
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported.add(node.module.split(".")[0])
            allowed = ALLOWED_NETWORK_IMPORTS.get(name, frozenset())
            with self.subTest(module=name):
                self.assertEqual(imported & NETWORK_MODULES, set(allowed))


if __name__ == "__main__":
    unittest.main()
