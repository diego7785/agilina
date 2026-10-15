"""Tests for the file walkers of the test helpers (the virtualenv must be excluded)."""

import unittest

from purple_team.tests.support import (
    PURPLE_TEAM_DIR,
    iter_harness_python_files,
    iter_harness_source_files,
    iter_python_files_under,
    make_temp_dir,
)

TREE = (
    "pkg/a.py",
    "pkg/sub/b.py",
    ".venv/lib/x.py",
    "pkg/.hidden/c.py",
    "pkg/__pycache__/d.py",
    "tests/t.py",
)


class PythonFileWalkerTest(unittest.TestCase):
    def test_hidden_folders_and_caches_are_skipped(self) -> None:
        root = make_temp_dir(self)
        for relative in TREE:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        found = [path.relative_to(root).as_posix() for path in iter_python_files_under(root)]
        self.assertEqual(found, ["pkg/a.py", "pkg/sub/b.py", "tests/t.py"])

    def test_harness_walkers_only_see_the_package(self) -> None:
        every_file = list(iter_harness_python_files())
        sources = list(iter_harness_source_files())
        self.assertIn(PURPLE_TEAM_DIR / "cli.py", sources)
        self.assertIn(PURPLE_TEAM_DIR / "tests" / "support.py", every_file)
        self.assertNotIn(PURPLE_TEAM_DIR / "tests" / "support.py", sources)
        for path in every_file:
            with self.subTest(path=path.name):
                self.assertNotIn(".venv", path.relative_to(PURPLE_TEAM_DIR).parts)


if __name__ == "__main__":
    unittest.main()
