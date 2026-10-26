"""sherpa-onnx speaker diarization adapter."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contracts import ProviderInfo, ProviderOption, ProviderResourceLink, SpeakerTurn

SHERPA_ONNX_TRANSLATIONS_EN = {'en': {'Diarisation locale avec modèles ONNX.': 'Local speaker diarization with ONNX models.',
        'Installe le runtime Python sherpa-onnx. Les deux modèles ONNX restent à télécharger séparément.': 'Installs '
                                                                                                           'the '
                                                                                                           'sherpa-onnx '
                                                                                                           'Python '
                                                                                                           'runtime. '
                                                                                                           'Both '
                                                                                                           'ONNX '
                                                                                                           'models '
                                                                                                           'must '
                                                                                                           'be '
                                                                                                           'downloaded '
                                                                                                           'separately.',
        'Modèle de segmentation': 'Segmentation model',
        'Modèle ONNX qui détecte les tours de parole.': 'ONNX model that detects speaker turns.',
        'Modèle de reconnaissance des voix': 'Speaker recognition model',
        'Modèle ONNX qui regroupe les segments par voix.': 'ONNX model that groups transcript segments by '
                                                           'speaker.',
        'Modèles de segmentation des locuteurs': 'Speaker segmentation models',
        'Téléchargez et extrayez le modèle, puis configurez son fichier .onnx.': 'Download and extract the '
                                                                                 'model, then configure its '
                                                                                 '.onnx file.',
        'Modèles d’embeddings vocaux': 'Speaker embedding models',
        'Téléchargez un modèle compatible et configurez son chemin .onnx.': 'Download a compatible model and '
                                                                            'configure its .onnx path.',
        'Documentation diarisation': 'Diarization documentation',
        'Licence sherpa-onnx': 'sherpa-onnx license'}}

SHERPA_ONNX_INFO = ProviderInfo(
    id="sherpa-onnx", name="sherpa-onnx", task="diarization",
    description="Diarisation locale avec modèles ONNX.",
    execution="embedded",
    capabilities=("local", "speaker-segmentation", "speaker-embedding"),
    python_install_extra="diarization",
    python_install_packages=("sherpa-onnx>=1.10.28",),
    python_install_note="Installe le runtime Python sherpa-onnx. Les deux modèles ONNX restent à télécharger séparément.",
    setup_links=(
        ProviderResourceLink("Modèles de segmentation des locuteurs", "https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models", "model", "Téléchargez et extrayez le modèle, puis configurez son fichier .onnx."),
        ProviderResourceLink("Modèles d’embeddings vocaux", "https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models", "model", "Téléchargez un modèle compatible et configurez son chemin .onnx."),
        ProviderResourceLink("Documentation diarisation", "https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/index.html", "documentation"),
        ProviderResourceLink("Licence sherpa-onnx", "https://github.com/k2-fsa/sherpa-onnx", "license"),
    ),
    options=(
        ProviderOption(
            key="diarization_segmentation_model", label="Modèle de segmentation", type="path",
            default="models/diarization/segmentation/segmentation.onnx",
            description="Modèle ONNX qui détecte les tours de parole.", required=True, advanced=True,
        ),
        ProviderOption(
            key="diarization_embedding_model", label="Modèle de reconnaissance des voix", type="path",
            default="models/diarization/embedding/embedding.onnx",
            description="Modèle ONNX qui regroupe les segments par voix.", required=True, advanced=True,
        ),
    ),
    translations=SHERPA_ONNX_TRANSLATIONS_EN,
)


class SherpaOnnxDiarizationProvider:
    """Translate Glimio's provider-neutral audio-window contract to sherpa-onnx."""

    info = SHERPA_ONNX_INFO

    def __init__(self, options: Mapping[str, Any] | None = None) -> None:
        values = dict(options or {})
        self.segmentation_model = Path(str(values.get(
            "diarization_segmentation_model", "models/diarization/segmentation/segmentation.onnx"
        ))).expanduser()
        self.embedding_model = Path(str(values.get(
            "diarization_embedding_model", "models/diarization/embedding/embedding.onnx"
        ))).expanduser()
        for label, path in (("segmentation", self.segmentation_model), ("embedding", self.embedding_model)):
            if not path.is_file():
                raise RuntimeError(f"Modèle de diarisation {label} introuvable : {path}")

        try:
            import sherpa_onnx
        except ImportError as exc:
            raise RuntimeError(
                'La diarisation nécessite sherpa-onnx. Installez la dépendance avec : '
                'python -m pip install -e ".[diarization]"'
            ) from exc

        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=str(self.segmentation_model),
                ),
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(self.embedding_model)),
            clustering=sherpa_onnx.FastClusteringConfig(
                num_clusters=int(values.get("diarization_num_speakers", -1)),
                threshold=float(values.get("diarization_threshold", 0.5)),
            ),
            min_duration_on=0.3,
            min_duration_off=0.5,
        )
        if not config.validate():
            raise RuntimeError("Configuration sherpa-onnx invalide. Vérifiez les deux modèles ONNX de diarisation.")
        self._diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)
        self.sample_rate = int(self._diarizer.sample_rate)

    def process(self, audio: Any) -> list[SpeakerTurn]:
        result = self._diarizer.process(audio).sort_by_start_time()
        return [
            SpeakerTurn(float(turn.start), float(turn.end), int(turn.speaker))
            for turn in result
            if float(turn.end) > float(turn.start)
        ]
