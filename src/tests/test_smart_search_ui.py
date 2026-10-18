from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "src" / "web"


class SmartSearchUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (WEB / "static" / "index.html").read_text(encoding="utf-8")
        cls.app_js = (WEB / "static" / "js" / "app.js").read_text(encoding="utf-8")
        cls.search_js = (WEB / "static" / "js" / "pages" / "search.js").read_text(encoding="utf-8")
        cls.runtime_css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
        cls.source_css = (WEB / "frontend" / "src" / "components.css").read_text(encoding="utf-8")
        cls.changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    def test_search_feature_name_is_consistent(self) -> None:
        self.assertIn("<span>Recherche intelligente</span>", self.html)
        self.assertIn('id="search-title" tabindex="-1">Recherche intelligente</h1>', self.html)
        self.assertIn("search: 'Recherche intelligente'", self.app_js)
        self.assertNotIn("Recherche IA", self.html)

    def test_search_composer_groups_question_and_actions(self) -> None:
        self.assertIn('class="ai-composer"', self.html)
        self.assertIn('class="ai-composer-footer"', self.html)
        footer = self.html.split('class="ai-composer-footer"', 1)[1].split('</div>', 1)[0]
        self.assertIn('id="run-ai-search"', footer)
        self.assertIn('id="cancel-ai-search"', footer)
        self.assertIn('aria-describedby="ai-query-hint ai-query-shortcut"', self.html)

    def test_query_field_auto_grows_and_has_keyboard_shortcut(self) -> None:
        self.assertIn("const maxHeight = 260", self.search_js)
        self.assertIn("queryInput.scrollHeight", self.search_js)
        self.assertIn("event.ctrlKey || event.metaKey", self.search_js)
        self.assertIn("event.preventDefault()", self.search_js)

    def test_composer_and_border_tokens_exist_in_runtime_and_source_css(self) -> None:
        for css in (self.runtime_css, self.source_css):
            self.assertIn(".ai-composer:focus-within", css)
            self.assertIn(".ai-query-input.textarea.is-overflowing", css)
            self.assertIn(".source-card, .choice-card, .diarize-card", css)
            self.assertIn("border-color: color-mix(in srgb, var(--c-border) 68%, var(--c-surface))", css)
            self.assertNotIn(".ai-input-row", css)

    def test_ui_changes_are_recorded_in_changelog_and_version_is_bumped(self) -> None:
        self.assertIn("## 0.2.0 — Persistance, reprise et interface aplatie", self.changelog)
        self.assertIn("## 0.1.0 — File de traitement", self.changelog)
        self.assertIn('version = "0.4.2"', self.pyproject)

    def test_flat_surface_effects_and_recording_stop_alignment_are_documented(self) -> None:
        for css in (self.runtime_css, self.source_css):
            self.assertIn("Glimio 0.2.0 — flatter surfaces", css)
            self.assertIn("box-shadow: inset 0 1px 0", css)
            self.assertIn(".record-status #stop-recording", css)
        self.assertIn("bouton **Arrêter** dans la barre d’état", self.changelog)


if __name__ == "__main__":
    unittest.main()
