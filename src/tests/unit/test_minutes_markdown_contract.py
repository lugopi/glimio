from __future__ import annotations

import unittest

from seance.processing.minutes import _draft_system_prompt, _draft_user_prompt


class MarkdownRenderingContractTests(unittest.TestCase):
    def test_draft_prompt_describes_markdown_supported_by_the_interface(self) -> None:
        prompt = _draft_user_prompt("notes de test", "summary", partial=False)
        for expected in (
            "rendu Markdown volontairement simple",
            "titres Markdown de niveaux # à ####",
            "listes simples",
            "tableaux Markdown",
            "N'écris pas de HTML brut",
            "NOTES DÉTAILLÉES",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, prompt)

    def test_system_prompt_reinforces_the_same_markdown_limitations(self) -> None:
        prompt = _draft_system_prompt()
        self.assertIn("contrat Markdown compatible avec Glimio", prompt)
        self.assertIn("évite le HTML brut", prompt)


if __name__ == "__main__":
    unittest.main()
