"""Tests for the verified MITRE ATLAS catalog."""

import re
import unittest

from purple_team.atlas import ATLAS_CATALOG, ATLAS_DATA_VERSION, AtlasTechnique

ATLAS_ID_PATTERN = re.compile(r"^AML\.T\d{4}(\.\d{3})?$")


class AtlasCatalogTest(unittest.TestCase):
    def test_ids_follow_the_atlas_pattern_and_names_are_not_empty(self) -> None:
        self.assertTrue(ATLAS_CATALOG)
        for technique_id, technique in ATLAS_CATALOG.items():
            with self.subTest(technique=technique_id):
                self.assertRegex(technique_id, ATLAS_ID_PATTERN)
                self.assertEqual(technique.technique_id, technique_id)
                self.assertTrue(technique.name.strip())

    def test_catalog_holds_the_verified_names(self) -> None:
        self.assertEqual(ATLAS_DATA_VERSION, "2026.09")
        self.assertEqual(
            ATLAS_CATALOG["AML.T0086"].name,
            "Exfiltration via AI Agent Tool Invocation",
        )
        self.assertEqual(ATLAS_CATALOG["AML.T0051.001"].name, "LLM Prompt Injection: Indirect")

    def test_to_dict_uses_id_and_name(self) -> None:
        technique = AtlasTechnique("AML.T0068", "LLM Prompt Obfuscation")
        self.assertEqual(technique.to_dict(), {"id": "AML.T0068", "name": "LLM Prompt Obfuscation"})


if __name__ == "__main__":
    unittest.main()
