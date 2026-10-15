"""Tests for the single path rule used in every record."""

import os
import unittest
from pathlib import Path

from purple_team.paths import display_path
from purple_team.tests.support import make_temp_dir


class DisplayPathTest(unittest.TestCase):
    def test_returns_posix_relative_path_inside_base(self) -> None:
        base = make_temp_dir(self)
        target = base / "outputs" / "run-1" / "c01"
        self.assertEqual(display_path(target, base), "outputs/run-1/c01")

    def test_returns_absolute_path_outside_base(self) -> None:
        base = make_temp_dir(self)
        other = make_temp_dir(self)
        result = display_path(other / "cases", base)
        self.assertTrue(Path(result).is_absolute())
        self.assertEqual(result, (other / "cases").resolve().as_posix())

    def test_resolves_symbolic_links_before_comparing(self) -> None:
        root = make_temp_dir(self)
        real_base = root / "real"
        real_base.mkdir()
        link = root / "link"
        os.symlink(real_base, link)
        self.assertEqual(display_path(real_base / "inputs", link), "inputs")
        self.assertEqual(display_path(link / "inputs", real_base), "inputs")

    def test_base_itself_is_shown_as_dot(self) -> None:
        base = make_temp_dir(self)
        self.assertEqual(display_path(base, base), ".")


if __name__ == "__main__":
    unittest.main()
