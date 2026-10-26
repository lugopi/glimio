from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seance.processing.minutes import _detect_auto_format, _parse_auto_format_decision


class AutomaticFormatSelectionTests(unittest.TestCase):
    def test_parser_accepts_a_high_confidence_decision_with_two_verbatim_quotes(self) -> None:
        transcript = (
            "Hier, j'ai terminé la migration vers la nouvelle version. "
            "Aujourd'hui, je dois vérifier l'importation complète. "
            "Je suis bloqué sur les tests de validation. Demain, je reprends cette priorité."
        )
        candidate = json.dumps({
            "format": "daily",
            "confidence": "high",
            "evidence": [
                "Hier, j'ai terminé la migration vers la nouvelle version",
                "Je suis bloqué sur les tests de validation",
            ],
        })
        selected, reason, evidence = _parse_auto_format_decision(candidate, transcript)
        self.assertEqual(selected, "daily")
        self.assertIn("grounded", reason)
        self.assertEqual(len(evidence), 2)

    def test_specialized_format_needs_high_confidence(self) -> None:
        transcript = "On pourrait examiner les différentes approches pour cette nouvelle fonctionnalité."
        candidate = json.dumps({
            "format": "brainstorm",
            "confidence": "medium",
            "evidence": [transcript, "On pourrait examiner les différentes approches"],
        })
        selected, reason, _ = _parse_auto_format_decision(candidate, transcript)
        self.assertIsNone(selected)
        self.assertIn("not classified with high confidence", reason)

    def test_specialized_format_needs_two_verifiable_quotes(self) -> None:
        transcript = "On pourrait examiner les différentes approches pour cette nouvelle fonctionnalité."
        candidate = json.dumps({
            "format": "brainstorm",
            "confidence": "high",
            "evidence": [
                "On pourrait examiner les différentes approches pour cette nouvelle fonctionnalité",
                "Cette phrase ne figure pas réellement dans la transcription source",
            ],
        })
        selected, reason, evidence = _parse_auto_format_decision(candidate, transcript)
        self.assertIsNone(selected)
        self.assertIn("lacked two distinct", reason)
        self.assertEqual(len(evidence), 1)

    def test_narrative_format_accepts_grounded_evidence(self) -> None:
        transcript = (
            "Lena pousse la porte de la tour et découvre une lettre cachetée sur la table. "
            "Après avoir lu le message, elle décide de quitter la ville avant le lever du soleil."
        )
        candidate = json.dumps({
            "format": "narrative",
            "confidence": "high",
            "evidence": [
                "Lena pousse la porte de la tour et découvre une lettre cachetée sur la table",
                "elle décide de quitter la ville avant le lever du soleil",
            ],
        })
        selected, reason, evidence = _parse_auto_format_decision(candidate, transcript)
        self.assertEqual(selected, "narrative")
        self.assertIn("grounded", reason)
        self.assertEqual(len(evidence), 2)

    def test_dialogue_and_learning_are_supported_classifier_formats(self) -> None:
        transcript = (
            "Pourquoi la méthode fonctionne-t-elle dans ce cas précis ? "
            "Elle fonctionne parce que la température reste constante pendant toute la réaction."
        )
        for report_format in ("dialogue", "learning"):
            candidate = json.dumps({
                "format": report_format,
                "confidence": "high",
                "evidence": [
                    "Pourquoi la méthode fonctionne-t-elle dans ce cas précis",
                    "Elle fonctionne parce que la température reste constante pendant toute la réaction",
                ],
            })
            with self.subTest(report_format=report_format):
                selected, _reason, _evidence = _parse_auto_format_decision(candidate, transcript)
                self.assertEqual(selected, report_format)

    def test_classifier_prompt_distinguishes_narrative_dialogue_learning_and_speaker_markers(self) -> None:
        transcript = (
            "**Speaker 1**: Lena ouvre la porte de la tour et découvre une lettre cachetée. "
            "**Speaker 2**: Pourquoi la température reste-t-elle constante pendant la réaction ?"
        )
        candidate = json.dumps({"format": "summary", "confidence": "medium", "evidence": []})
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "seance.processing.minutes._run_llama_resilient",
                return_value=(candidate, False),
            ) as run_generation:
                selected = _detect_auto_format(
                    transcript,
                    executable=Path(temp_dir) / "llama-completion",
                    model_path=Path(temp_dir) / "model.gguf",
                    folder=Path(temp_dir),
                    context=8192,
                )
        self.assertEqual(selected, "summary")
        system_prompt = run_generation.call_args.args[3]
        user_prompt = run_generation.call_args.args[4]
        for expected in ("narrative", "dialogue", "learning", "roleplay", "Speaker 1", "piste/source"):
            with self.subTest(expected=expected):
                self.assertIn(expected, system_prompt + user_prompt)

    def test_general_summary_is_always_a_safe_valid_choice(self) -> None:
        candidate = json.dumps({"format": "summary", "confidence": "low", "evidence": []})
        selected, reason, evidence = _parse_auto_format_decision(candidate, "Une discussion ordinaire.")
        self.assertEqual(selected, "summary")
        self.assertIn("general format", reason)
        self.assertEqual(evidence, [])

    def test_classifier_uses_original_transcript_and_requests_grounded_evidence(self) -> None:
        transcript = (
            "Hier, j'ai terminé la migration vers la nouvelle version. "
            "Aujourd'hui, je dois vérifier l'importation complète. "
            "Je suis bloqué sur les tests de validation. Demain, je reprends cette priorité."
        )
        candidate = json.dumps({
            "format": "daily",
            "confidence": "high",
            "evidence": [
                "Hier, j'ai terminé la migration vers la nouvelle version",
                "Je suis bloqué sur les tests de validation",
            ],
        })
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "seance.processing.minutes._run_llama_resilient",
                return_value=(candidate, False),
            ) as run_generation:
                selected = _detect_auto_format(
                    transcript,
                    executable=Path(temp_dir) / "llama-completion",
                    model_path=Path(temp_dir) / "model.gguf",
                    folder=Path(temp_dir),
                    context=8192,
                )

            self.assertEqual(selected, "daily")
            prompt = run_generation.call_args.args[4]
            system_prompt = run_generation.call_args.args[3]
            self.assertIn("TRANSCRIPTION ORIGINALE", prompt)
            self.assertIn("migration vers la nouvelle version", prompt)
            self.assertIn("plusieurs indices explicites", system_prompt)
            self.assertIn("deux courts extraits distincts", system_prompt)
            self.assertEqual(run_generation.call_args.kwargs["max_tokens"], 220)
            selection_record = (Path(temp_dir) / "analysis" / "format_selection.txt").read_text(encoding="utf-8")
            self.assertIn("Selected format: daily", selection_record)
            self.assertIn("Classification source: original transcript excerpts", selection_record)
            self.assertIn("Verified evidence excerpts:", selection_record)

    def test_unstructured_or_ungrounded_decision_falls_back_to_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "seance.processing.minutes._run_llama_resilient",
                return_value=("I think the best format is technical", False),
            ):
                selected = _detect_auto_format(
                    "Une discussion sur un sujet technique.",
                    executable=Path(temp_dir) / "llama-completion",
                    model_path=Path(temp_dir) / "model.gguf",
                    folder=Path(temp_dir),
                    context=8192,
                )
            self.assertEqual(selected, "summary")
            selection_record = (Path(temp_dir) / "analysis" / "format_selection.txt").read_text(encoding="utf-8")
            self.assertIn("Selected format: summary", selection_record)
            self.assertIn("not valid JSON", selection_record)

    def test_classifier_failure_falls_back_to_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "seance.processing.minutes._run_llama_resilient",
                side_effect=SystemExit("model unavailable"),
            ):
                selected = _detect_auto_format(
                    "Une discussion générale.",
                    executable=Path(temp_dir) / "llama-completion",
                    model_path=Path(temp_dir) / "model.gguf",
                    folder=Path(temp_dir),
                    context=8192,
                )
            self.assertEqual(selected, "summary")
            selection_record = (Path(temp_dir) / "analysis" / "format_selection.txt").read_text(encoding="utf-8")
            self.assertIn("Classifier failed", selection_record)


if __name__ == "__main__":
    unittest.main()
