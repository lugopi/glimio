from __future__ import annotations

import unittest
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = SRC_ROOT / "web"


class ActivitySessionNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jobs_js = (WEB_ROOT / "static" / "js" / "pages" / "jobs.js").read_text(encoding="utf-8")
        cls.library_js = (WEB_ROOT / "static" / "js" / "pages" / "library.js").read_text(encoding="utf-8")
        cls.app_js = (WEB_ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        cls.runtime_css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        cls.source_css = (WEB_ROOT / "frontend" / "src" / "components.css").read_text(encoding="utf-8")

    def test_job_with_session_is_rendered_as_keyboard_accessible_button(self) -> None:
        self.assertIn("const canOpenSession = Boolean(job.session_id);", self.jobs_js)
        self.assertIn("const rowTag = canOpenSession ? 'button' : 'article';", self.jobs_js)
        self.assertIn("job-row--clickable", self.jobs_js)
        self.assertIn('data-session-id=', self.jobs_js)
        self.assertIn('type="button"', self.jobs_js)
        self.assertIn("Ouvrir dans la bibliothèque", self.jobs_js)

    def test_click_dispatches_session_navigation_event(self) -> None:
        self.assertIn("export function bindJobsEvents()", self.jobs_js)
        self.assertIn("seance:open-session", self.jobs_js)
        self.assertIn("detail: { sessionId: row.dataset.sessionId }", self.jobs_js)
        self.assertIn("bindJobsEvents();", self.app_js)

    def test_app_resets_library_filters_then_opens_requested_session(self) -> None:
        self.assertIn("window.addEventListener('seance:open-session'", self.app_js)
        self.assertIn("query.value = '';", self.app_js)
        self.assertIn("filter.value = 'all';", self.app_js)
        self.assertIn("await loadSessions();", self.app_js)
        self.assertIn("await ensureSessionVisible(sessionId);", self.app_js)
        self.assertIn("await openSession(sessionId);", self.app_js)

    def test_old_job_rows_without_sessions_are_not_clickable(self) -> None:
        self.assertIn("const rowTag = canOpenSession ? 'button' : 'article';", self.jobs_js)
        self.assertIn("const rowAttrs = canOpenSession", self.jobs_js)
        self.assertIn("if (!row || !list.contains(row)) return;", self.jobs_js)

    def test_stale_detail_responses_do_not_overwrite_another_session(self) -> None:
        self.assertIn("state.selectedId !== sessionId || detail.dataset.sessionId !== sessionId", self.library_js)
        self.assertIn("requestedSessionId = state.selectedId", self.library_js)
        self.assertIn("state.selectedId !== requestedSessionId", self.library_js)

    def test_clickable_row_styles_match_runtime_and_tailwind_source(self) -> None:
        for css in (self.runtime_css, self.source_css):
            self.assertIn(".job-row--clickable", css)
            self.assertIn(".job-row--clickable:focus-visible", css)
            self.assertIn(".job-open-hint", css)


if __name__ == "__main__":
    unittest.main()
