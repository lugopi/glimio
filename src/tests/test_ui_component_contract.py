from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "web"


class UiComponentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.ui = (ROOT / "static" / "js" / "components" / "ui.js").read_text(encoding="utf-8")
        cls.jobs = (ROOT / "static" / "js" / "pages" / "jobs.js").read_text(encoding="utf-8")
        cls.library = (ROOT / "static" / "js" / "pages" / "library.js").read_text(encoding="utf-8")
        cls.runtime_css = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
        cls.source_css = (ROOT / "frontend" / "src" / "components.css").read_text(encoding="utf-8")

    def test_burger_icons_use_locally_bundled_heroicons_and_no_i_hack(self):
        self.assertIn("'bars-3'", self.ui)
        self.assertIn("icon('bars-3')", self.library)
        self.assertIn('class="mobile-nav-icon"', self.html)
        self.assertIn("iconContainer.innerHTML = icon(isOpen ? 'x-mark' : 'bars-3')", (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8"))
        self.assertNotIn('class="burger-glyph"', self.library)
        self.assertNotIn(".burger-glyph i", self.runtime_css)
        self.assertTrue((ROOT / "static" / "vendor" / "heroicons" / "LICENSE").is_file())

    def test_pagination_markup_and_behavior_are_shared(self):
        self.assertIn("paginationMarkup", self.ui)
        self.assertIn("updatePagination", self.ui)
        self.assertIn("paginationMarkup", self.jobs)
        self.assertIn("paginationMarkup", self.library)
        self.assertIn('id="jobs-pagination" hidden></div>', self.html)
        self.assertIn('id="library-pagination"></div>', self.html)

    def test_activity_delete_button_is_positioned_inside_the_card(self):
        self.assertIn('class="job-row-wrap">${row}${remove}</div>', self.jobs)
        for css in (self.runtime_css, self.source_css):
            self.assertIn(".job-row-wrap { position: relative;", css)
            self.assertIn(".job-row-delete { position: absolute;", css)
            self.assertIn(".job-row-wrap > .job-row { box-sizing: border-box; width: 100%;", css)


if __name__ == "__main__":
    unittest.main()
