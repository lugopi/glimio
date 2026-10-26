from __future__ import annotations

import unittest

from seance.processing.minutes import (
    _FORMAT_TITLES, _OVERVIEW_HEADINGS, _draft_system_prompt, _draft_user_prompt,
    _format_instructions, _format_title, _overview_heading,
)


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

    def test_auto_summary_language_follows_the_original_transcript(self) -> None:
        prompt = _draft_user_prompt("notes de test", "summary", partial=False)
        self.assertIn("LANGUE DE SORTIE", prompt)
        self.assertIn("même langue dominante que la transcription originale", prompt)

    def test_explicit_summary_language_is_part_of_the_generation_contract(self) -> None:
        prompt = _draft_user_prompt("notes de test", "summary", partial=False, summary_language="de")
        self.assertIn("en allemand (code de)", prompt)

    def test_explicit_language_also_localizes_assembled_report_headings(self) -> None:
        self.assertEqual(_format_title("summary", "en"), "Detailed audio summary")
        self.assertEqual(_overview_heading("technical", "en"), "Technical overview")
        self.assertEqual(_format_title("narrative", "fr"), "Résumé narratif")
        self.assertEqual(_format_title("dialogue", "en"), "Conversation summary")
        self.assertEqual(_overview_heading("learning", "fr"), "Vue d'ensemble des apprentissages")

    def test_every_supported_summary_language_has_titles_for_all_new_formats(self) -> None:
        expected = {"summary", "narrative", "dialogue", "learning", "daily", "technical", "formal", "brainstorm"}
        self.assertTrue(_FORMAT_TITLES)
        self.assertTrue(_OVERVIEW_HEADINGS)
        for language in _FORMAT_TITLES:
            with self.subTest(language=language):
                self.assertTrue(expected.issubset(_FORMAT_TITLES[language]))
                self.assertTrue(expected.issubset(_OVERVIEW_HEADINGS[language]))

    def test_narrative_dialogue_and_learning_have_distinct_output_contracts(self) -> None:
        narrative = _format_instructions("narrative", partial=False).casefold()
        dialogue = _format_instructions("dialogue", partial=False).casefold()
        learning = _format_instructions("learning", partial=False).casefold()
        self.assertIn("livre audio", narrative)
        self.assertIn("roleplay", narrative)
        self.assertIn("questions", dialogue)
        self.assertIn("désaccords", dialogue)
        self.assertIn("cours", learning)
        self.assertIn("exemples", learning)
        self.assertNotIn("procès-verbal classique", narrative)

    def test_speaker_markers_are_explained_not_treated_as_names(self) -> None:
        prompt = _draft_user_prompt("notes de test", "narrative", partial=False)
        self.assertIn("métadonnées structurelles", prompt)
        self.assertIn("numéro de voix identifie le personnage", prompt)
        self.assertIn("distingue le narrateur", prompt)


if __name__ == "__main__":
    unittest.main()
