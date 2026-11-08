from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seance.processing.minutes import _generate_global_overview, _maybe_generate_default_session_title, translate_summary
from seance.summary_languages import (
    available_summary_translations,
    detect_transcript_language,
    resolve_summary_language,
    summary_language_instruction,
    summary_translation_path,
)


class SummaryLanguageTests(unittest.TestCase):
    def test_auto_instruction_follows_source_language(self) -> None:
        self.assertIn("même langue dominante que la transcription originale", summary_language_instruction("auto"))

    def test_language_detection_identifies_long_transcripts_but_skips_short_ambiguous_text(self) -> None:
        english = (
            "The team discussed the priorities with the managers. We have defined the next steps and we are "
            "agreed on the goals. This approach is useful, but we still need to check the results. "
        ) * 5
        french = (
            "Les équipes ont discuté des priorités avec les responsables. Nous avons défini les prochaines "
            "étapes et nous sommes d’accord sur les objectifs. Cette approche est utile, mais il faut "
            "encore vérifier les résultats. "
        ) * 5
        self.assertEqual(detect_transcript_language(english), "en")
        self.assertEqual(detect_transcript_language(french), "fr")
        self.assertIsNone(detect_transcript_language("Bonjour à tous, voici une courte séance."))

    def test_explicit_summary_language_overrides_transcript_and_transcription_language(self) -> None:
        english = (
            "The team discussed the priorities with the managers. We have defined the next steps and we are "
            "agreed on the goals. This approach is useful, but we still need to check the results. "
        ) * 5

        effective, detected, source = resolve_summary_language("de", english, "fr")

        self.assertEqual(effective, "de")
        self.assertIsNone(detected)
        self.assertEqual(source, "explicit summary setting")

    def test_auto_summary_language_uses_confident_transcript_detection_first(self) -> None:
        english = (
            "The team discussed the priorities with the managers. We have defined the next steps and we are "
            "agreed on the goals. This approach is useful, but we still need to check the results. "
        ) * 5

        effective, detected, source = resolve_summary_language("auto", english, "fr")

        self.assertEqual(effective, "en")
        self.assertEqual(detected, "en")
        self.assertEqual(source, "transcript language detection")

    def test_auto_summary_language_falls_back_to_selected_transcription_language(self) -> None:
        effective, detected, source = resolve_summary_language(
            "auto", "Bonjour à tous, voici une courte séance.", "de",
        )

        self.assertEqual(effective, "de")
        self.assertIsNone(detected)
        self.assertEqual(source, "explicit transcription language fallback")

    def test_auto_summary_language_stays_automatic_when_both_signals_are_ambiguous(self) -> None:
        effective, detected, source = resolve_summary_language(
            "auto", "Short mixed sample.", "detect",
        )

        self.assertEqual(effective, "auto")
        self.assertIsNone(detected)
        self.assertEqual(source, "automatic source-language instruction (uncertain detection)")

    def test_summary_language_instruction_covers_all_visible_generated_text(self) -> None:
        instruction = summary_language_instruction("fr")

        self.assertIn("en français (code fr)", instruction)
        self.assertIn("les sous-titres", instruction)
        self.assertIn("Ne réponds pas en français ni dans la langue source", instruction)

    def test_translation_paths_accept_only_supported_language_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = summary_translation_path(temporary, "fr")
            self.assertEqual(path, Path(temporary).resolve() / "summary" / "translations" / "fr.md")
            with self.assertRaises(ValueError):
                summary_translation_path(temporary, "../../metadata/seance")

    def test_translation_is_saved_as_a_separate_variant_and_preserves_original(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            summary_dir = folder / "summary"
            summary_dir.mkdir(parents=True)
            original = "# Résumé original\n\n" + ("Cette transcription décrit les décisions de la réunion. " * 12)
            source = summary_dir / "resume_audio.md"
            source.write_text(original, encoding="utf-8")
            translated = "# Original summary\n\n" + ("This transcript describes the meeting decisions. " * 12)
            args = argparse.Namespace(
                context=8192, max_tokens=2000, analysis_retries=1,
                analysis_max_splits=3, llama_completion="llama-completion", gguf="model.gguf",
            )
            with patch("seance.processing.minutes._run_prompt_with_recursive_splitting", return_value=([translated], False)):
                result = translate_summary(folder, args, "en")
            self.assertEqual(result, summary_dir / "translations" / "en.md")
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertEqual(result.read_text(encoding="utf-8").strip(), translated.strip())
            self.assertEqual(available_summary_translations(folder), ["en"])

    def test_translation_repeats_the_target_language_in_the_user_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            summary_dir = folder / "summary"
            summary_dir.mkdir(parents=True)
            (summary_dir / "resume_audio.md").write_text("# Résumé\n\n" + ("Texte source. " * 12), encoding="utf-8")
            args = argparse.Namespace(
                context=8192, max_tokens=2000, analysis_retries=1,
                analysis_max_splits=3, llama_completion="llama-completion", gguf="model.gguf",
            )

            with patch("seance.processing.minutes._run_prompt_with_recursive_splitting", return_value=(["# Summary\n\n" + ("English text. " * 12)], False)) as run:
                translate_summary(folder, args, "en")

            system_prompt = run.call_args.args[3]
            prompt_factory = run.call_args.args[5]
            user_prompt = prompt_factory("# Résumé", True)

            self.assertIn("traduis fidèlement", system_prompt.casefold())
            self.assertIn("en anglais", system_prompt)
            self.assertIn("LANGUE CIBLE — CONSIGNE PRIORITAIRE : en anglais (code en)", user_prompt)
            self.assertIn("ne réponds pas dans la langue source", user_prompt.casefold())

    def test_global_overview_repeats_the_target_language_in_both_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch("seance.processing.minutes._run_llama_resilient", return_value=("Kurzüberblick", False)) as run:
                result = _generate_global_overview(
                    "summary", ["# Section\n\nEin wichtiges Thema."],
                    executable=Path("llama-completion"), model_path=Path("model.gguf"),
                    folder=Path(temporary), context=8192, summary_language="de",
                )

            self.assertEqual(result, "Kurzüberblick")
            system_prompt = run.call_args.args[3]
            user_prompt = run.call_args.args[4]
            self.assertIn("en allemand (code de)", system_prompt)
            self.assertIn("LANGUE DE SORTIE — CONSIGNE PRIORITAIRE", user_prompt)
            self.assertIn("en allemand (code de)", user_prompt)

    def test_automatic_title_prompt_repeats_the_target_language(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            metadata = folder / "metadata"
            metadata.mkdir()
            (metadata / "seance.json").write_text(
                '{"title": "Sans titre"}', encoding="utf-8",
            )

            with patch("seance.processing.minutes._run_llama_resilient", return_value=("Projektstart", False)) as run:
                result = _maybe_generate_default_session_title(
                    folder, "Ein neues Projekt startet.",
                    executable=Path("llama-completion"), model_path=Path("model.gguf"),
                    context=8192, summary_language="de",
                )

            self.assertEqual(result, "Projektstart")
            user_prompt = run.call_args.args[4]
            self.assertIn("LANGUE DU TITRE — CONSIGNE PRIORITAIRE", user_prompt)
            self.assertIn("en allemand (code de)", user_prompt)

    def test_short_summary_translation_is_not_rejected_by_a_fixed_minimum_length(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            summary_dir = folder / "summary"
            summary_dir.mkdir(parents=True)
            original = "# Résumé bref\n\nLa séance fixe les objectifs et les prochaines étapes."
            (summary_dir / "resume_audio.md").write_text(original, encoding="utf-8")
            translated = "# Short summary\n\nThe session sets goals and next steps."
            args = argparse.Namespace(
                context=4096, max_tokens=1000, analysis_retries=1,
                analysis_max_splits=2, llama_completion="llama-completion", gguf="model.gguf",
            )
            with patch("seance.processing.minutes._run_prompt_with_recursive_splitting", return_value=([translated], False)):
                result = translate_summary(folder, args, "en")
            self.assertEqual(result.read_text(encoding="utf-8").strip(), translated)

    def test_available_translations_ignore_unknown_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            variants = Path(temporary) / "summary" / "translations"
            variants.mkdir(parents=True)
            (variants / "fr.md").write_text("Résumé", encoding="utf-8")
            (variants / "unknown.md").write_text("ignored", encoding="utf-8")
            (variants / "junk.txt").write_text("ignored", encoding="utf-8")
            self.assertEqual(available_summary_translations(temporary), ["fr"])


if __name__ == "__main__":
    unittest.main()
