"""Contract tests for the offline-first FR/EN interface localization layer."""
from __future__ import annotations

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src" / "web" / "static"


class _TextInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.phrases: set[str] = set()

    def handle_data(self, data: str) -> None:
        phrase = " ".join(data.split())
        if phrase and not phrase.isnumeric() and any(character.isalnum() for character in phrase):
            self.phrases.add(phrase)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"placeholder", "title", "aria-label", "aria-description", "aria-placeholder", "alt"} and value:
                self.phrases.add(value)


class LocalizationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (STATIC / "index.html").read_text(encoding="utf-8")
        cls.i18n_js = (STATIC / "js" / "i18n.js").read_text(encoding="utf-8")
        cls.en = json.loads((STATIC / "locales" / "en.json").read_text(encoding="utf-8"))
        cls.fr = json.loads((STATIC / "locales" / "fr.json").read_text(encoding="utf-8"))

    def test_supported_catalogs_have_matching_source_messages(self) -> None:
        self.assertGreaterEqual(len(self.en), 250)
        self.assertEqual(set(self.en), set(self.fr))
        self.assertTrue(all(source == value for source, value in self.fr.items()))
        self.assertNotEqual(self.en["Bibliothèque"], "Bibliothèque")
        self.assertNotEqual(self.en["Enregistrement"], "Enregistrement")

    def test_interpolation_messages_exist_for_dynamic_labels(self) -> None:
        required = {
            "{{start}}–{{end}} sur {{total}}",
            "Page {{page}} / {{pages}}",
            "Toutes les séances ({{total}})",
            "{{count}} résumé sur cette page",
            "{{count}} résumés sur cette page",
            "{{count}} en attente. Les étapes sont exécutées séquentiellement.",
        }
        self.assertTrue(required.issubset(self.en))

    def test_language_selector_and_runtime_wiring_are_present(self) -> None:
        self.assertIn('id="language-select"', self.html)
        self.assertIn('<option value="fr">Français</option>', self.html)
        self.assertIn('<option value="en">English</option>', self.html)
        app_js = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("import { initI18n } from './i18n.js';", app_js)
        self.assertIn('await initI18n();', app_js)
        self.assertIn("localStorage.setItem(STORAGE_KEY, selected)", self.i18n_js)
        self.assertIn("document.documentElement.lang = activeLanguage", self.i18n_js)
        self.assertIn("navigator.languages", self.i18n_js)

    def test_catalog_assets_are_included_in_python_package_data(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"static/locales/*.json"', pyproject)
        self.assertTrue((STATIC / "locales" / "fr.json").is_file())
        self.assertTrue((STATIC / "locales" / "en.json").is_file())

    def test_static_interface_phrases_are_catalogued_or_are_identifiers(self) -> None:
        inventory = _TextInventory()
        inventory.feed(self.html)
        intentional_identifiers = {"Glimio", "English", "Français", "FFmpeg", "seances/", "0,50"}
        missing = sorted(inventory.phrases - set(self.en) - intentional_identifiers)
        self.assertEqual(missing, [])

    def test_explicit_font_sizes_remain_relative(self) -> None:
        stylesheet_files = [STATIC / "app.css", ROOT / "src" / "web" / "frontend" / "src" / "components.css"]
        for stylesheet in stylesheet_files:
            css = stylesheet.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"font-size\s*:\s*[^;}]*\b\d+(?:\.\d+)?px", css), str(stylesheet))
            self.assertIsNone(re.search(r"font\s*:\s*[^;}]*\b\d+(?:\.\d+)?px", css), str(stylesheet))


    def test_transcription_language_mode_can_follow_ui_or_use_whisper_detection(self) -> None:
        recording_js = (STATIC / "js" / "pages" / "recording.js").read_text(encoding="utf-8")
        self.assertIn('<option value="auto">Auto — suivre la langue de l’interface</option>', self.html)
        self.assertIn('<option value="detect">Détecter la langue parlée (Whisper)</option>', self.html)
        self.assertIn("window.glimioI18n?.language", recording_js)
        self.assertIn("selectedLanguage === 'detect'", recording_js)
        self.assertIn("settings: settingsFromUI({ resolveAutoLanguage: false })", recording_js)
        self.assertTrue(any("Ce réglage n’effectue pas de traduction vers une autre langue." in value for value in self.fr.values()))
        self.assertTrue(any("This setting does not translate speech into another language." in value for value in self.en.values()))

if __name__ == "__main__":
    unittest.main()
