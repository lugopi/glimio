from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError
from fastapi import HTTPException

from seance.providers.media_tools import DEFAULT_MEDIA_PROVIDER, MEDIA_PROVIDER_IDS
from web.app import Settings, UIPreferences

MEDIA_TOOLS = Path(tempfile.gettempdir()) / "glimio-tools"


class WebSettingsContractTests(unittest.TestCase):
    def test_rejects_processing_limits_below_supported_minimum(self) -> None:
        invalid_settings = (
            {"context": 1024},
            {"max_tokens": 400},
            {"analysis_tokens": 80},
        )
        for values in invalid_settings:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                Settings(**values)

    def test_accepts_supported_summary_format_and_themes(self) -> None:
        self.assertEqual(Settings(format="daily").format, "daily")
        self.assertEqual(Settings(format="narrative").namespace().format, "narrative")
        self.assertEqual(Settings(format="dialogue").format, "dialogue")
        self.assertEqual(Settings(format="learning").format, "learning")
        self.assertEqual(UIPreferences(theme="dracula").theme, "dracula")
        self.assertEqual(UIPreferences(theme="monokai").theme, "monokai")

    def test_summary_language_defaults_to_transcription_language_and_is_propagated(self) -> None:
        self.assertEqual(Settings().summary_language, "auto")
        self.assertEqual(Settings(summary_language="fr").namespace().summary_language, "fr")

    def test_rejects_unsupported_summary_language(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(summary_language="xx")

    def test_reads_media_commands_from_provider_options(self) -> None:
        ffmpeg = str(MEDIA_TOOLS / "ffmpeg.exe")
        ffprobe = str(MEDIA_TOOLS / "ffprobe.exe")

        settings = Settings(provider_options={"ffmpeg": {"ffmpeg": ffmpeg, "ffprobe": ffprobe}})

        self.assertEqual(settings.ffmpeg, ffmpeg)
        self.assertEqual(settings.ffprobe, ffprobe)

    def test_namespace_exposes_resolved_media_commands(self) -> None:
        ffmpeg = str(MEDIA_TOOLS / "ffmpeg.exe")
        ffprobe = str(MEDIA_TOOLS / "ffprobe.exe")
        settings = Settings(provider_options={"ffmpeg": {"ffmpeg": ffmpeg, "ffprobe": ffprobe}})

        namespace = settings.namespace()

        self.assertEqual(namespace.ffmpeg, str(Path(ffmpeg).resolve()))
        self.assertEqual(namespace.ffprobe, str(Path(ffprobe).resolve()))

    def test_namespace_defaults_ffprobe_when_only_ffmpeg_is_configured(self) -> None:
        settings = Settings(ffmpeg=str(MEDIA_TOOLS / "ffmpeg.exe"), provider_options={})

        namespace = settings.namespace()

        self.assertEqual(settings.ffmpeg, str(MEDIA_TOOLS / "ffmpeg.exe"))
        self.assertEqual(namespace.ffmpeg, str((MEDIA_TOOLS / "ffmpeg.exe").resolve()))
        self.assertEqual(namespace.ffprobe, "ffprobe")

    def test_defaults_to_the_ffmpeg_media_provider(self) -> None:
        self.assertEqual(DEFAULT_MEDIA_PROVIDER, "ffmpeg")
        self.assertEqual(Settings().media_provider, DEFAULT_MEDIA_PROVIDER)
        self.assertEqual(Settings().namespace().media_provider, "ffmpeg")

    def test_accepts_the_native_media_provider_and_propagates_it(self) -> None:
        self.assertIn("native", MEDIA_PROVIDER_IDS)
        ffmpeg = str(MEDIA_TOOLS / "ffmpeg.exe")
        ffprobe = str(MEDIA_TOOLS / "ffprobe.exe")
        settings = Settings(
            media_provider="native",
            provider_options={"ffmpeg": {"ffmpeg": ffmpeg, "ffprobe": ffprobe}},
        )

        namespace = settings.namespace()

        self.assertEqual(namespace.media_provider, "native")
        # The historical media aliases stay aligned with the ffmpeg provider options.
        self.assertEqual(namespace.ffmpeg, str(Path(ffmpeg).resolve()))
        self.assertEqual(namespace.ffprobe, str(Path(ffprobe).resolve()))

    def test_diarization_provider_and_its_options_flow_through_namespace(self) -> None:
        segmentation = str(MEDIA_TOOLS / "segmentation.onnx")
        embedding = str(MEDIA_TOOLS / "embedding.onnx")
        settings = Settings(
            diarization_provider="sherpa-onnx",
            provider_options={"sherpa-onnx": {
                "diarization_segmentation_model": segmentation,
                "diarization_embedding_model": embedding,
            }},
        )

        namespace = settings.namespace()

        self.assertEqual(namespace.diarization_provider, "sherpa-onnx")
        self.assertEqual(namespace.diarization_segmentation_model, str(Path(segmentation).resolve()))
        self.assertEqual(namespace.diarization_embedding_model, str(Path(embedding).resolve()))
        self.assertEqual(
            namespace.provider_options["sherpa-onnx"]["diarization_segmentation_model"],
            str(Path(segmentation).resolve()),
        )

    def test_rejects_an_unknown_diarization_provider(self) -> None:
        settings = Settings(diarization_provider="made-up-diarization")

        with self.assertRaises(HTTPException) as error:
            settings.namespace()

        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(error.exception.detail, "Provider de diarisation inconnu.")

    def test_rejects_an_unknown_media_provider(self) -> None:
        settings = Settings(media_provider="made-up-media")

        with self.assertRaises(HTTPException) as error:
            settings.namespace()

        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(error.exception.detail, "Provider média inconnu.")


if __name__ == "__main__":
    unittest.main()
