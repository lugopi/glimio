from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seance.processing.minutes import translate_summary
from seance.summary_languages import (
    available_summary_translations,
    detect_transcript_language,
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
