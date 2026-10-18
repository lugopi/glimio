from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = SRC_ROOT / "web"


class _HTMLSanityParser(HTMLParser):
    pass


class WebUiCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (WEB_ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.app_css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        cls.source_css = (WEB_ROOT / "frontend" / "src" / "components.css").read_text(encoding="utf-8")
        cls.jobs_js = (WEB_ROOT / "static" / "js" / "pages" / "jobs.js").read_text(encoding="utf-8")
        cls.library_js = (WEB_ROOT / "static" / "js" / "pages" / "library.js").read_text(encoding="utf-8")
        cls.search_js = (WEB_ROOT / "static" / "js" / "pages" / "search.js").read_text(encoding="utf-8")

    def test_html_parses_and_uses_a_mode_aware_runtime_indicator(self) -> None:
        parser = _HTMLSanityParser(convert_charrefs=True)
        parser.feed(self.html)
        parser.close()
        self.assertIn('id="runtime-indicator"', self.html)
        self.assertIn('id="runtime-mode-label"', self.html)
        self.assertIn('id="runtime-mode-detail"', self.html)
        self.assertIn("Traitement local", self.html)  # Initial fallback; runtime config controls the final value.
        self.assertNotIn("Aucune donnée envoyée au cloud", self.html)
        for duplicate in (
            "Mode local", "POSTE LOCAL", "LLAMA.CPP · LOCAL",
            "Audio et modèles restent sur ce poste", "Aucun service cloud",
        ):
            self.assertNotIn(duplicate, self.html)

    def test_audio_normalization_controls_are_preserved(self) -> None:
        self.assertIn('id="normalize-windows"', self.html)
        self.assertIn('id="normalize-windows-max-gain"', self.html)
        for css in (self.app_css, self.source_css):
            for selector in (".windows-normalization-option", ".normalization-gain-control", ".range-input"):
                self.assertIn(selector, css)

    def test_activity_and_search_copy_does_not_repeat_local_badges(self) -> None:
        all_js = self.jobs_js + self.library_js + self.search_js
        for phrase in ("Résumé local", "Génération du résumé local", "LLM LOCAL", "Préparation de la recherche locale"):
            self.assertNotIn(phrase, all_js)
        self.assertIn("Génération du résumé", all_js)
        self.assertIn("MULTI-SÉANCES", self.html)

    def test_removed_footer_badge_styles_are_not_left_behind(self) -> None:
        for css in (self.app_css, self.source_css):
            self.assertNotIn(".local-pill", css)
            self.assertNotIn(".footer-local", css)
            self.assertNotIn(".app-footer", css)


if __name__ == "__main__":
    unittest.main()
