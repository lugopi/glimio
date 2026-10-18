from __future__ import annotations

import unittest
from pathlib import Path
import re
from pydantic import ValidationError

from web.app import (
    DEFAULT_WHISPER_MODEL, DEFAULT_WHISPER_CLI, DEFAULT_GGUF, DEFAULT_LLAMA_COMPLETION, Settings,
)


class WebSettingsContractTests(unittest.TestCase):
    def test_rejects_context_below_minutes_engine_minimum(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(context=1024)

    def test_rejects_output_budget_below_minutes_engine_minimum(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(max_tokens=400)

    def test_rejects_analysis_budget_below_minutes_engine_minimum(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(analysis_tokens=80)


    def test_settings_form_paths_match_backend_defaults(self) -> None:
        # Full Angular : le formulaire ne code plus les chemins en dur ; il
        # affiche settings.* renvoyé par GET /api/preferences. Contrat : chaque
        # clé a un champ [ngModel]="value.<clé>" et le modèle du backend fournit
        # les valeurs par défaut attendues.
        html = (Path(__file__).parents[1] / "web" / "frontend" / "src" / "app"
                / "pages" / "settings" / "settings.page.html").read_text(encoding="utf-8")
        expected = {
            "model": DEFAULT_WHISPER_MODEL,
            "whisper_cli": DEFAULT_WHISPER_CLI,
            "gguf": DEFAULT_GGUF,
            "llama_completion": DEFAULT_LLAMA_COMPLETION,
        }
        defaults = Settings()
        for key, path in expected.items():
            self.assertIn(f'[ngModel]="value.{key}"', html, f"Missing UI field for {key}")
            self.assertEqual(getattr(defaults, key), path, f"Backend default mismatch for {key}")

    def test_cli_fallbacks_use_upstream_executable_names(self) -> None:
        src_root = Path(__file__).parents[1]
        pipeline = (src_root / "seance" / "pipeline.py").read_text(encoding="utf-8")
        minutes = (src_root / "seance" / "minutes.py").read_text(encoding="utf-8")
        self.assertIn('"bin/asr/whisper-cli.exe"', pipeline)
        self.assertIn('"bin/asr/whisper-cli.exe"', minutes)
        self.assertIn('"bin/llm/llama-completion.exe"', pipeline)
        app_source = (src_root / "web" / "app.py").read_text(encoding="utf-8")
        self.assertIn('DEFAULT_WHISPER_CLI = "bin/asr/whisper-cli.exe"', app_source)
        self.assertIn('DEFAULT_LLAMA_COMPLETION = "bin/llm/llama-completion.exe"', app_source)


if __name__ == "__main__":
    unittest.main()
