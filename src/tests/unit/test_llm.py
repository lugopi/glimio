from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from seance.llm import LLMError, build_completion_command, clean_model_output


class CleanModelOutputTests(unittest.TestCase):
    def test_removes_complete_reasoning_block_and_keeps_final_answer(self) -> None:
        raw = "<think>private notes</think>\n## Synthèse générale\nLe thème apparaît dans la source [1]."
        cleaned = clean_model_output(raw)
        self.assertNotIn("private notes", cleaned)
        self.assertIn("Synthèse générale", cleaned)
        self.assertIn("[1]", cleaned)

    def test_discards_unclosed_reasoning_block(self) -> None:
        raw = "## Synthèse générale\nDébut fiable.\n<think>le modèle raisonne encore et se coupe"
        cleaned = clean_model_output(raw)
        self.assertEqual(cleaned, "## Synthèse générale\nDébut fiable.")

    def test_prefers_final_channel(self) -> None:
        raw = "<|channel|>analysis\nsecret\n<|channel|>final\nRéponse [1]"
        cleaned = clean_model_output(raw)
        self.assertNotIn("secret", cleaned)
        self.assertEqual(cleaned, "Réponse [1]")

    def test_discards_truncated_analysis_channel_without_final(self) -> None:
        raw = "<|start|>assistant<|channel|>analysis<|message|>raisonnement tronqué"
        cleaned = clean_model_output(raw)
        self.assertEqual(cleaned, "")

    def test_strips_leftover_special_tokens_after_final_channel(self) -> None:
        raw = "<|channel|>final<|message|>Réponse finale<|return|>"
        cleaned = clean_model_output(raw)
        self.assertEqual(cleaned, "Réponse finale")

    def test_discards_unclosed_reflection_block(self) -> None:
        raw = "Réponse partielle.\n<reflection>je poursuis sans fermer"
        cleaned = clean_model_output(raw)
        self.assertEqual(cleaned, "Réponse partielle.")


class CompletionCommandCompatibilityTests(unittest.TestCase):
    def test_supports_long_only_prompt_and_noninteractive_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary = root / "llama-completion.exe"
            model = root / "model.gguf"
            binary.write_bytes(b"executable-placeholder")
            model.write_bytes(b"model-placeholder")
            long_help = """
--conversation
--single-turn
--no-conversation
--prompt PROMPT
--system-prompt PROMPT
--jinja
--no-display-prompt
"""
            with mock.patch("seance.llm.llama_help_text", return_value=long_help):
                command, effective_tokens = build_completion_command(
                    binary, model, context=4096, max_tokens=256, temperature=0.2,
                    system_prompt="system", user_prompt="user",
                )
            self.assertIn("--conversation", command)
            self.assertIn("--single-turn", command)
            self.assertIn("--system-prompt", command)
            self.assertIn("--prompt", command)
            self.assertIn("--jinja", command)
            self.assertIn("--no-display-prompt", command)
            self.assertGreaterEqual(effective_tokens, 128)

    def test_refuses_unknown_interaction_mode_instead_of_risk_hanging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary = root / "llama-completion.exe"
            model = root / "model.gguf"
            binary.write_bytes(b"executable-placeholder")
            model.write_bytes(b"model-placeholder")
            with mock.patch("seance.llm.llama_help_text", return_value="Usage: llama-completion\n--model FILE\n"):
                with self.assertRaises(LLMError):
                    build_completion_command(
                        binary, model, context=4096, max_tokens=256, temperature=0.2,
                        system_prompt="system", user_prompt="user",
                    )
