from __future__ import annotations

import unittest
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = SRC_ROOT / "web"


class TailwindComponentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_css = (WEB_ROOT / "frontend" / "src" / "components.css").read_text(encoding="utf-8")
        cls.tokens = (WEB_ROOT / "frontend" / "src" / "tokens.css").read_text(encoding="utf-8")
        cls.runtime_css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        cls.ui_js = (WEB_ROOT / "static" / "js" / "components" / "ui.js").read_text(encoding="utf-8")
        cls.recording_js = (WEB_ROOT / "static" / "js" / "pages" / "recording.js").read_text(encoding="utf-8")
        cls.search_js = (WEB_ROOT / "static" / "js" / "pages" / "search.js").read_text(encoding="utf-8")
        cls.jobs_js = (WEB_ROOT / "static" / "js" / "pages" / "jobs.js").read_text(encoding="utf-8")
        cls.app_js = (WEB_ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

    def test_reusable_styles_are_built_from_tailwind_apply(self) -> None:
        self.assertGreaterEqual(self.source_css.count("@apply"), 70)
        for component in (
            ".nav-link { @apply", ".btn { @apply", ".card { @apply",
            ".input, .select, .textarea { @apply", ".badge { @apply",
            ".source-card, .choice-card, .diarize-card { @apply", ".spinner { @apply",
        ):
            self.assertIn(component, self.source_css)

    def test_semantic_theme_tokens_cover_reusable_component_colors(self) -> None:
        for token in (
            "--color-sidebar", "--color-surface-hover", "--color-border-soft",
            "--color-subtle", "--color-accent-contrast", "--color-accent-soft",
            "--color-danger-soft", "--shadow-panel",
        ):
            self.assertIn(token, self.tokens)

    def test_disabled_and_loading_cursors_are_distinct(self) -> None:
        # Source CSS expresses these states through Tailwind utilities; the checked-in
        # runtime stylesheet contains their equivalent CSS property values.
        self.assertIn("button:disabled", self.source_css)
        self.assertIn("cursor-not-allowed", self.source_css)
        self.assertIn("button.is-loading:disabled", self.source_css)
        self.assertIn("cursor-wait", self.source_css)
        self.assertIn(".btn .btn-label", self.source_css)

        self.assertIn("button:disabled", self.runtime_css)
        self.assertIn("cursor: not-allowed", self.runtime_css)
        self.assertIn("button.is-loading:disabled", self.runtime_css)
        self.assertIn("cursor: wait", self.runtime_css)
        self.assertIn(".btn .btn-label", self.runtime_css)

    def test_off_source_card_remains_clickable_to_reenable(self) -> None:
        self.assertIn(".source-card.is-disabled-source { @apply cursor-pointer; }", self.source_css)
        self.assertIn(".source-card.is-disabled-source { cursor: pointer; }", self.runtime_css)

    def test_shared_loading_helper_restores_original_button_state(self) -> None:
        self.assertIn("export function setButtonLoading", self.ui_js)
        self.assertIn("loadingSnapshots", self.ui_js)
        self.assertIn("aria-busy", self.ui_js)
        self.assertIn("element.disabled = snapshot.disabled", self.ui_js)
        self.assertIn("loading ? 'is-loading' : ''", self.ui_js)

    def test_async_actions_use_the_shared_spinner_component(self) -> None:
        for source in (self.recording_js, self.search_js, self.jobs_js, self.app_js):
            self.assertIn("setButtonLoading", source)
        for label in ("Démarrage…", "Arrêt…", "Envoi en cours…"):
            self.assertIn(label, self.recording_js)
        self.assertIn("Recherche…", self.search_js)
        self.assertIn("Annulation…", self.search_js)


    def test_recording_controls_have_stable_layout_and_manual_speaker_count(self) -> None:
        html = (WEB_ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="diarization-num-speakers" data-setting="diarization_num_speakers" type="number"', html)
        self.assertIn('id="diarization-num-speakers-auto" checked', html)
        self.assertIn("#windows-device-field { grid-column: 2; }", self.runtime_css)
        self.assertIn(".record-buttons #start-recording { flex: 1 1 100%;", self.runtime_css)
        self.assertIn(".record-status #stop-recording[hidden] { display: none !important; }", self.runtime_css)
        self.assertIn(".record-status #stop-recording { flex: 0 0 auto;", self.runtime_css)
        self.assertIn(".record-buttons:has(#start-recording[hidden]) { display: none; }", self.runtime_css)
        html = (WEB_ROOT / "static" / "index.html").read_text(encoding="utf-8")
        status_row = html.split('id="record-status"', 1)[1].split('</div>', 1)[0]
        self.assertIn('id="stop-recording"', status_row)
        self.assertNotIn('id="stop-recording"', html.split('class="record-buttons"', 1)[1].split('</div>', 1)[0])
        self.assertIn("grid-column: 1 / -1; min-width: 0; margin: 17px 0 0", self.runtime_css)
        self.assertIn("settings.diarization_num_speakers = automaticSpeakers.checked", self.recording_js)
        self.assertIn("automaticSpeakers.checked", self.recording_js)

    def test_interactive_list_rows_fill_the_available_width(self) -> None:
        # Runtime and Tailwind source keep list backgrounds aligned with their
        # container edges and use a collapsed accessible mobile navigation menu.
        for css in (self.source_css, self.runtime_css):
            self.assertIn(".nav-list {\n    padding: 0;", css)
            self.assertIn(".session-list {\n    gap: 0;\n    padding: 4px 0;", css)
            self.assertIn(".jobs-list {\n    gap: 7px;\n    padding: 2px 0;\n    margin-inline: 0;", css)
            self.assertIn(".job-row--clickable {\n    box-sizing: border-box;\n    width: 100%;", css)
            self.assertIn(".source-item {\n    box-sizing: border-box;\n    width: 100%;", css)
            self.assertIn(".sidebar #main-navigation { display: none;", css)
            self.assertIn(".sidebar.is-nav-open #main-navigation { display: grid; }", css)
            self.assertNotIn(".nav-list {\n    overflow-x: auto;", css)

    def test_accessible_cursor_rules_preserve_text_selection_and_raise_text_contrast(self) -> None:
        self.assertIn("body { cursor: default; }", self.runtime_css)
        self.assertIn("input:not([type=\"checkbox\"]):not([type=\"radio\"]):not([type=\"range\"]), textarea, [contenteditable=\"true\"] { cursor: text; }", self.runtime_css)
        self.assertIn("user-select: text;", self.runtime_css)

        # Check the principal text/status tokens against the raised surface in each theme.
        import re
        def luminance(hex_color: str) -> float:
            channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
            return sum(weight * channel for weight, channel in zip((0.2126, 0.7152, 0.0722), linear))

        def contrast(first: str, second: str) -> float:
            light, dark = sorted((luminance(first), luminance(second)), reverse=True)
            return (light + 0.05) / (dark + 0.05)

        blocks = re.findall(r'(:root(?:\[data-theme="[^"]+"\])?)\s*\{([^}]*)\}', self.tokens)
        for theme, block in blocks:
            tokens = dict(re.findall(r'(--c-[\w-]+):\s*(#[0-9a-fA-F]{6})', block))
            if "--c-text" not in tokens:
                continue
            surface = tokens["--c-surface-raised"]
            for key in ("--c-text", "--c-muted", "--c-subtle", "--c-accent", "--c-success", "--c-warning", "--c-danger"):
                self.assertGreaterEqual(contrast(tokens[key], surface), 7.0, f"{theme} {key} must reach AAA text contrast")
            self.assertGreaterEqual(contrast(tokens["--c-accent-contrast"], tokens["--c-accent"]), 7.0, f"{theme} primary button text must reach AAA contrast")


if __name__ == "__main__":
    unittest.main()
    def test_reviewed_layout_rules_are_present_in_source_and_served_css(self) -> None:
        for css in (self.source_css, self.runtime_css):
            self.assertIn('.brand > div:nth-child(2) { flex: 1 1 0%; width: 0; min-width: 0; }', css)
            self.assertIn('.session-actions-toggle > .burger-glyph { display: flex; width: 100%;', css)
            self.assertIn('.job-row-wrap { display: grid;', css)
            self.assertIn('.settings-autosave-icon { display: grid;', css)
            self.assertIn('.participant-count-field:not([hidden]) { display: grid; gap: 8px; padding: 12px 14px; }', css)
        self.assertIn("job.state === 'completed' ? iconSvg('completed')", self.jobs_js)
        self.assertIn('data-delete-job', self.jobs_js)

