from __future__ import annotations

import json
import unittest
from pathlib import Path
from pydantic import ValidationError

from seance.audio import sample_rate_for_bitrate
from web.app import Settings

ROOT = Path(__file__).resolve().parents[2]


class AudioBitrateProfileTests(unittest.TestCase):
    def test_pcm_bitrate_options_map_to_actual_mono_16_bit_sample_rates(self) -> None:
        self.assertEqual(sample_rate_for_bitrate(128), 8000)
        self.assertEqual(sample_rate_for_bitrate(256), 16000)
        self.assertEqual(sample_rate_for_bitrate(384), 24000)
        self.assertEqual(sample_rate_for_bitrate(512), 32000)
        self.assertEqual(sample_rate_for_bitrate(768), 48000)

    def test_invalid_pcm_bitrate_is_rejected_by_helper_and_settings_model(self) -> None:
        with self.assertRaises(ValueError):
            sample_rate_for_bitrate(300)
        with self.assertRaises(ValidationError):
            Settings(audio_bitrate_kbps=300)

    def test_settings_exposes_generic_paths_for_all_models_and_local_binaries(self) -> None:
        settings = Settings()
        self.assertEqual(settings.model, 'models/asr/model.bin')
        self.assertEqual(settings.whisper_cli, 'bin/asr/whisper-cli.exe')
        self.assertEqual(settings.gguf, 'models/llm/model.gguf')
        self.assertEqual(settings.llama_completion, 'bin/llm/llama-completion.exe')
        self.assertEqual(settings.diarization_segmentation_model, 'models/diarization/segmentation.onnx')
        self.assertEqual(settings.diarization_embedding_model, 'models/diarization/embedding.onnx')
        self.assertEqual(settings.audio_bitrate_kbps, 256)

    def test_settings_view_centralizes_every_model_and_binary_path(self) -> None:
        html = (ROOT / 'src/web/static/index.html').read_text(encoding='utf-8')
        control_view = html.split('id="view-control"', 1)[1].split('id="view-settings"', 1)[0]
        settings_view = html.split('id="view-settings"', 1)[1].split('id="view-library"', 1)[0]
        for element_id in ('whisper-model', 'whisper-cli', 'llm-model', 'llama-cli', 'diarization-segmentation-model', 'diarization-embedding-model', 'ffmpeg-path'):
            self.assertIn(f'id="{element_id}"', settings_view)
            self.assertNotIn(f'id="{element_id}"', control_view)
        self.assertIn('id="audio-bitrate" data-setting="audio_bitrate_kbps"', settings_view)
        self.assertIn('data-setting="no_review"', settings_view)
        self.assertIn('data-setting="whisper_cli" value="bin/asr/whisper-cli.exe"', settings_view)
        self.assertIn('data-setting="llama_completion" value="bin/llm/llama-completion.exe"', settings_view)
        self.assertNotIn('bin/asr/transcriber.exe', html)
        self.assertNotIn('bin/llm/inference.exe', html)

    def test_processing_options_are_shared_between_recording_and_import_and_not_collapsible(self) -> None:
        html = (ROOT / 'src/web/static/index.html').read_text(encoding='utf-8')
        recording_js = (ROOT / 'src/web/static/js/pages/recording.js').read_text(encoding='utf-8')
        control_view = html.split('id="view-control"', 1)[1].split('id="view-settings"', 1)[0]
        settings_view = html.split('id="view-settings"', 1)[1].split('id="view-library"', 1)[0]
        self.assertIn('class="card shared-processing-panel"', control_view)
        self.assertIn('id="processing-options-title"', control_view)
        self.assertIn('id="diarize" data-setting="diarize"', control_view)
        self.assertIn('id="language" data-setting="language"', control_view)
        self.assertIn('id="default-summary-format" data-setting="format"', control_view)
        self.assertNotIn('id="default-summary-format"', settings_view)
        self.assertIn('id="import-title"', control_view)
        en = json.loads((ROOT / 'src/web/static/locales/en.json').read_text(encoding='utf-8'))
        option_text = 'Identifie les différentes voix et associe à chacune les segments correspondants de la transcription. S’applique aux enregistrements et aux fichiers importés dès qu’une transcription est lancée ; sans effet en mode « Enregistrer seulement ».'
        self.assertIn('recordings and imported files', en[option_text])
        self.assertNotIn('processing-options-heading', recording_js)
        self.assertNotIn('diarizeOption.hidden = workflow', recording_js)
        self.assertNotIn('aria-expanded', control_view)
        self.assertNotIn('Les options inutiles sont masquées selon le flux choisi', html)
        for catalog in ('fr', 'en'):
            messages = json.loads((ROOT / f'src/web/static/locales/{catalog}.json').read_text(encoding='utf-8'))
            self.assertNotIn('Les options inutiles sont masquées selon le flux choisi', messages)

    def test_locale_catalogues_keep_the_same_keys_for_the_new_settings_view(self) -> None:
        fr = json.loads((ROOT / 'src/web/static/locales/fr.json').read_text(encoding='utf-8'))
        en = json.loads((ROOT / 'src/web/static/locales/en.json').read_text(encoding='utf-8'))
        self.assertEqual(set(fr), set(en))
        self.assertIn('Modèles et exécutables', fr)
        self.assertEqual(en['Modèles et exécutables'], 'Models and executables')

    def test_recording_layout_places_shared_options_after_source_cards_and_splits_threshold_to_settings(self) -> None:
        html = (ROOT / 'src/web/static/index.html').read_text(encoding='utf-8')
        recording_js = (ROOT / 'src/web/static/js/pages/recording.js').read_text(encoding='utf-8')
        control_view = html.split('id="view-control"', 1)[1].split('id="view-settings"', 1)[0]
        settings_view = html.split('id="view-settings"', 1)[1].split('id="view-library"', 1)[0]
        self.assertLess(control_view.index('class="control-grid"'), control_view.index('class="card shared-processing-panel"'))
        shared_start = control_view.index('<section class="card shared-processing-panel"')
        jobs_start = control_view.index('<section class="card jobs-panel"')
        shared_options_markup = control_view[shared_start:jobs_start]
        self.assertIn('id="diarization-settings"', shared_options_markup)
        self.assertIn('class="card-title diarization-settings-title" id="diarization-settings-title"', shared_options_markup)
        self.assertIn('<legend class="sr-only">Paramètres de diarisation</legend>', shared_options_markup)
        self.assertLess(shared_options_markup.index('id="diarization-settings-title"'), shared_options_markup.index('id="diarization-settings"'))
        self.assertIn('id="diarization-num-speakers-auto" checked', shared_options_markup)
        self.assertIn('id="diarization-num-speakers-field" hidden', control_view)
        self.assertIn('id="diarization-num-speakers-auto" checked', control_view)
        self.assertLess(control_view.index('id="diarization-num-speakers-auto"'), control_view.index('id="diarization-num-speakers"'))
        self.assertNotIn('id="diarization-num-speakers"', settings_view)
        self.assertIn('id="diarization-threshold"', settings_view)
        self.assertIn('speakerCountField.hidden = automaticCount', recording_js)

    def test_common_options_and_license_have_consistent_spacing(self) -> None:
        for css_path in ('src/web/static/app.css', 'src/web/frontend/src/components.css'):
            css = (ROOT / css_path).read_text(encoding='utf-8')
            self.assertIn('.shared-processing-panel { min-width: 0; margin: 15px 0;', css)
            self.assertIn('.diarization-settings-section { display: grid; gap: 9px; min-width: 0; margin-top: 19px; }', css)
            self.assertIn('.diarization-settings { display: grid; grid-column: 1 / -1; gap: 14px; min-width: 0; margin: 0; padding: 18px 20px 20px; }', css)
            self.assertIn('.participant-count-field:not([hidden]) { display: grid; gap: 8px; }', css)
            self.assertIn('.participant-count-field { max-width: 420px; padding: 13px 14px;', css)
            self.assertIn('.settings-footer + .license-notice { margin-top: 12px; padding-top: 23px;', css)
            self.assertIn('.settings-footer + .license-notice { margin-top: 8px; padding-top: 18px; }', css)

    def test_mobile_navigation_uses_an_accessible_collapsible_menu(self) -> None:
        html = (ROOT / 'src/web/static/index.html').read_text(encoding='utf-8')
        app_js = (ROOT / 'src/web/static/js/app.js').read_text(encoding='utf-8')
        for attr in ('id="mobile-nav-toggle"', 'aria-controls="main-navigation"', 'aria-expanded="false"'):
            self.assertIn(attr, html)
        self.assertIn('id="main-navigation"', html)
        self.assertIn("window.matchMedia('(max-width: 850px)')", app_js)
        self.assertIn("event.key === 'Escape'", app_js)
        for css_path in ('src/web/static/app.css', 'src/web/frontend/src/components.css'):
            css = (ROOT / css_path).read_text(encoding='utf-8')
            self.assertIn('.sidebar.is-nav-open #main-navigation { display: grid; }', css)
            self.assertIn('.mobile-nav-toggle { display: inline-flex;', css)
            self.assertIn('.brand { width: 100%; min-height: 40px; align-items: center; padding: 0 10px;', css)
            self.assertIn('@media (max-width: 380px)', css)


if __name__ == '__main__':
    unittest.main()
