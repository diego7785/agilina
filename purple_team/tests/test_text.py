"""Tests for the text normalizations shared by the mock, the cases and the evaluator."""

import unicodedata
import unittest

from purple_team.core.text import fold_for_match, normalize_for_match


class FoldForMatchTest(unittest.TestCase):
    def test_ignores_accents_case_and_repeated_spaces(self) -> None:
        folded = fold_for_match("Migración  de DATOS")
        self.assertEqual(folded, fold_for_match("migracion de datos"))
        self.assertEqual(fold_for_match("Guía de Instalación"), "guia de instalacion")

    def test_decomposed_and_composed_forms_fold_equally(self) -> None:
        decomposed = unicodedata.normalize("NFD", "migración")
        composed = unicodedata.normalize("NFC", "migración")
        self.assertNotEqual(decomposed, composed)
        self.assertEqual(fold_for_match(decomposed), fold_for_match(composed))

    def test_enye_folds_to_its_base_letter(self) -> None:
        self.assertEqual(fold_for_match("año"), "ano")

    def test_normalize_for_match_keeps_accents(self) -> None:
        self.assertEqual(normalize_for_match("Migración  de\nDATOS"), "migración de datos")


if __name__ == "__main__":
    unittest.main()
