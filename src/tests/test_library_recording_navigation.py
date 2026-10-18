from __future__ import annotations

import unittest
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = SRC_ROOT / "web"


class LibraryRecordingNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = (WEB_ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.library = (WEB_ROOT / "static" / "js" / "pages" / "library.js").read_text(encoding="utf-8")
        cls.jobs = (WEB_ROOT / "static" / "js" / "pages" / "jobs.js").read_text(encoding="utf-8")
        cls.runtime_css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        cls.source_css = (WEB_ROOT / "frontend" / "src" / "components.css").read_text(encoding="utf-8")

    def test_library_contains_live_recording_banner_with_explicit_status(self) -> None:
        self.assertIn('id="library-recording-banner"', self.index)
        self.assertIn('role="status"', self.index)
        self.assertIn('aria-live="polite"', self.index)
        self.assertIn('id="library-recording-title"', self.index)
        self.assertIn('id="return-to-recording"', self.index)
        self.assertIn('Revenir à l’enregistrement', self.index)

    def test_capture_status_is_distinguished_from_post_processing(self) -> None:
        self.assertIn('Enregistrement audio en cours', self.library)
        self.assertIn('Transcription Whisper en cours', self.library)
        self.assertIn('Résumé LLM en cours', self.library)
        self.assertIn('Enregistrement en cours', self.library)
        self.assertIn('Whisper en cours', self.library)

    def test_job_polling_updates_banner_using_only_active_recording(self) -> None:
        self.assertIn("updateLibraryRecordingNotice(data.active || null)", self.jobs)
        self.assertIn("job?.kind === 'recording'", self.library)
        self.assertIn("['preparing', 'recording', 'finalizing']", self.library)

    def test_banner_button_navigates_and_focuses_recording_controls(self) -> None:
        self.assertIn("$('#return-to-recording')?.addEventListener('click'", self.library)
        self.assertIn("navigate('control')", self.library)
        self.assertIn("$('#stop-recording')", self.library)
        self.assertIn("window.matchMedia('(prefers-reduced-motion: reduce)')", self.library)
        self.assertIn('id="record-status" tabindex="-1"', self.index)

    def test_new_session_action_is_hidden_during_capture_and_kept_in_header_when_idle(self) -> None:
        self.assertIn('id="go-record"', self.index)
        self.assertIn("const newSessionButton = $('#go-record')", self.library)
        self.assertIn('newSessionButton.hidden = recordingActive', self.library)
        self.assertIn("if (newSessionButton) newSessionButton.hidden = recordingActive", self.library)
        # The page heading remains the single canonical entry point when idle.
        self.assertIn('id="library-title"', self.index)
        self.assertNotIn("label: 'Nouvelle séance'", self.library)

    def test_library_uses_return_banner_instead_of_duplicate_new_session_actions(self) -> None:
        self.assertIn('id="return-to-recording"', self.index)
        self.assertNotIn("action: button({ label: 'Nouvelle séance'", self.library)

    def test_recording_banner_styles_are_shared_between_runtime_and_source(self) -> None:
        for css in (self.runtime_css, self.source_css):
            self.assertIn('.library-recording-banner[hidden]', css)
            self.assertIn('.library-recording-banner.is-preparing', css)
            self.assertIn('.library-recording-banner.is-finalizing', css)
            self.assertIn('.library-recording-banner .btn', css)


    def test_session_detail_keeps_one_primary_action_and_compacts_secondary_actions(self) -> None:
        self.assertIn('class="session-actions-menu"', self.library)
        self.assertIn('class="session-actions-toggle"', self.library)
        self.assertIn('class="session-actions-panel"', self.library)
        self.assertIn("label: 'Tout traiter'", self.library)
        self.assertIn("label: 'Transcrire'", self.library)
        self.assertIn("label: 'Renommer'", self.library)
        self.assertIn("label: 'Supprimer'", self.library)
        self.assertIn("event.key !== 'Escape'", self.library)
        self.assertNotIn("toolbarParts.push(button({ label: 'Résumé'", self.library)
        self.assertNotIn("toolbarParts.push(button({ label: 'Transcription'", self.library)
        for css in (self.runtime_css, self.source_css):
            self.assertIn('.session-actions-panel', css)
            self.assertIn('.session-actions-toggle:focus-visible', css)


    def test_mobile_navigation_uses_collapsible_menu_not_horizontal_scroller(self) -> None:
        app_js = (WEB_ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("cameFromOpenMobileMenu", app_js)
        self.assertIn("heading?.focus({ preventScroll: true })", app_js)
        self.assertIn("event.key === 'Escape'", app_js)
        self.assertIn("aria-expanded", self.index)
        self.assertIn(".sidebar.is-nav-open #main-navigation { display: grid; }", self.runtime_css)
        self.assertNotIn(".nav-list { display: flex; gap: 5px; overflow-x: auto; }", self.runtime_css)

    def test_recording_panels_align_and_adapt_to_mobile(self) -> None:
        for css in (self.runtime_css, self.source_css):
            self.assertIn(".control-grid { align-items: stretch;", css)
            self.assertIn(".library-layout { align-items: stretch;", css)
            self.assertIn(".session-list-wrap, .session-detail { min-height: 480px;", css)

    def test_settings_autosave_has_no_manual_save_button_and_reports_result(self) -> None:
        recording = (WEB_ROOT / "static" / "js" / "pages" / "recording.js").read_text(encoding="utf-8")
        dom = (WEB_ROOT / "static" / "js" / "core" / "dom.js").read_text(encoding="utf-8")
        self.assertNotIn('id="save-settings"', self.index)
        self.assertNotIn("$('#save-settings')", recording)
        self.assertIn("Paramètres sauvegardés automatiquement.", recording)
        self.assertIn("Échec de la sauvegarde des paramètres :", recording)
        self.assertIn("item.setAttribute('role', kind === 'error' ? 'alert' : 'status')", dom)

    def test_runtime_mode_and_session_path_are_configuration_driven(self) -> None:
        recording = (WEB_ROOT / "static" / "js" / "pages" / "recording.js").read_text(encoding="utf-8")
        self.assertIn('id="runtime-indicator"', self.index)
        self.assertIn("config.processing_mode", recording)
        self.assertIn("updateSessionRoot(state.config.session_root)", recording)
        self.assertIn('id="copy-session-root"', self.index)
        self.assertNotIn("Aucune donnée envoyée au cloud</small>", self.index)

if __name__ == "__main__":
    unittest.main()
