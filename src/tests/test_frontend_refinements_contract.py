"""Regression contracts for shared Angular UI behavior and build boundaries.

These checks cover cross-layer contracts that are hard to infer from Python
unit tests alone; visual details should additionally be checked in the browser.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "src" / "web" / "frontend"
APP = FRONTEND / "src" / "app"


def read_app(relative_path: str) -> str:
    return (APP / relative_path).read_text(encoding="utf-8")


def test_global_sass_uses_module_syntax_and_tailwind_has_a_plain_css_entrypoint() -> None:
    main_scss = (FRONTEND / "src" / "styles" / "main.scss").read_text(encoding="utf-8")
    tailwind_css = (FRONTEND / "src" / "styles" / "tailwind.css").read_text(encoding="utf-8")
    angular = json.loads((FRONTEND / "angular.json").read_text(encoding="utf-8"))
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((FRONTEND / "package-lock.json").read_text(encoding="utf-8"))
    global_styles = angular["projects"]["glimio-web-ui"]["architect"]["build"]["options"]["styles"]
    expected_node = "^22.22.3 || ^24.15.0 || >=26.0.0"

    assert package["engines"]["node"] == expected_node
    assert lock["packages"][""]["engines"]["node"] == expected_node
    assert (FRONTEND / ".nvmrc").read_text(encoding="utf-8").strip() == "22.22.3"
    assert not re.search(r"^\s*@import\b", main_scss, flags=re.MULTILINE)
    assert "@use './components.scss';" in main_scss
    assert '@import "tailwindcss";' in tailwind_css
    assert global_styles[0] == "src/styles/tailwind.css"
    assert global_styles[1] == "src/styles/main.scss"


def test_library_duration_status_and_artifact_tabs_keep_their_visual_contracts() -> None:
    template = read_app("pages/library/library.page.html")
    styles = (FRONTEND / "src" / "app" / "pages" / "library" / "library.page.scss").read_text(encoding="utf-8")
    shared = (FRONTEND / "src" / "styles" / "components.scss").read_text(encoding="utf-8")

    assert 'class="session-markers"' in template and 'name="clock"' in template
    assert 'class="session-card-progress session-card-status" role="status"' in template
    assert 'session-card-status-button' not in template
    assert ".session-markers .badge > glimio-icon" in styles
    assert "flex: 0 0 12px" in styles and "min-width: 12px" in styles
    assert ':host .artifact-tabs { @apply mt-0 flex flex-wrap items-stretch gap-0 rounded-t-xl border border-b-0' in styles
    assert ".available-documents .artifact-content-pane" in shared
    assert "rounded-b-xl border border-border-soft" in shared


def test_pagination_keeps_range_and_page_size_controls_without_wrapping_desktop_controls() -> None:
    pagination_html = (APP / "shared" / "pagination.component.html").read_text(encoding="utf-8")
    pagination_scss = (APP / "shared" / "pagination.component.scss").read_text(encoding="utf-8")
    library = read_app("pages/library/library.page.html")
    search = read_app("pages/search/search.page.html")
    search_ts = read_app("pages/search/search.page.ts")

    assert pagination_html.index('class="pagination-summary"') < pagination_html.index("@if (totalPages() > 1)")
    assert ".pagination { @apply flex w-full min-w-0 flex-nowrap items-center justify-end" in pagination_scss
    assert ".pagination-summary { @apply m-0 shrink-0 whitespace-nowrap" in pagination_scss
    assert "container-type: inline-size" in pagination_scss
    assert "@container (max-width: 300px)" in pagination_scss
    assert 'id="session-page-size"' in library and 'glimio-pagination' in library
    assert 'id="search-source-page-size"' in search and 'glimio-pagination' in search
    assert "this.sources().slice(start, start + this.pageSize())" in search_ts
    assert "changePageSize" in search_ts and "this.page.set(1)" in search_ts


def test_checkbox_radio_labels_share_first_line_alignment_and_speaker_fields_spacing() -> None:
    global_styles = (FRONTEND / "src" / "styles" / "components.scss").read_text(encoding="utf-8")
    recording_styles = (APP / "pages" / "recording" / "recording.page.scss").read_text(encoding="utf-8")
    recording_html = read_app("pages/recording/recording.page.html")

    assert 'label:has(> input[type="checkbox"])' in global_styles
    assert 'label:has(> input[type="radio"])' in global_styles
    assert "@apply mt-0.5 shrink-0 self-start;" in global_styles
    assert ".shared-processing-content .diarize-card { height: 100%; margin-top: 0; align-items: flex-start; }" in global_styles
    assert ".common-processing-fields .field-label { @apply mb-2; }" in recording_styles
    assert "container-type: inline-size" in (APP / "pages" / "library" / "library.page.scss").read_text(encoding="utf-8")
    assert 'for="recording-speakers"' in recording_html


def test_external_model_actions_open_manual_pages_and_keep_license_gates() -> None:
    settings = read_app("pages/settings/settings.page.html")

    assert "https://huggingface.co/unsloth/LFM2.5-8B-A1B-GGUF" in settings
    assert "https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models" in settings
    assert "https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models" in settings
    assert 'target="_blank" rel="noopener noreferrer"' in settings
    assert "lfmLicenseReviewed()" in settings
    assert "segmentationLicenseReviewed()" in settings
    assert "embeddingLicenseReviewed()" in settings


def test_importing_fastapi_module_does_not_attempt_to_build_angular() -> None:
    source = (ROOT / "src" / "web" / "app.py").read_text(encoding="utf-8")
    module_body, main_body = source.split("def main() -> None:", maxsplit=1)

    assert "ANGULAR_DIST_DIR = _ensure_angular_dist()" not in module_body
    assert "ANGULAR_DIST_DIR = _ensure_angular_dist()" in main_body


def test_web_run_configuration_uses_project_paths_without_forcing_rebuilds() -> None:
    run_config = (ROOT / ".run" / "Start - Web.run.xml").read_text(encoding="utf-8")

    assert 'name="WORKING_DIRECTORY" value="$PROJECT_DIR$"' in run_config
    assert 'L:\\Documents' not in run_config
    assert 'name="IS_MODULE_SDK" value="true"' in run_config
    assert 'name="GLIMIO_WEB_BUILD"' not in run_config
    assert '<method v="2" />' in run_config
