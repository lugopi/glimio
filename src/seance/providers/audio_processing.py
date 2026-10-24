"""Pluggable local audio-processing providers.

No heavy ML package is imported at module import time. Model/runtime dependencies
are resolved only when the corresponding provider is selected.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np

from .contracts import (
    AudioEnhancementRequest, AudioEnhancementResult, AudioSeparationRequest,
    AudioSeparationResult, ProviderInfo, ProviderOption, ProviderOptionChoice,
    ProviderResourceLink, SpeakerEmbeddingProvider,
)
from ..media.speech_enhancement import enhance_for_transcription


NO_ENHANCEMENT_TRANSLATIONS_EN = {'en': {'Aucun prétraitement': 'No preprocessing',
        'Utilise l’audio source tel quel, sans filtre ni modèle supplémentaire.': 'Uses the source audio '
                                                                                  'as-is, without a filter '
                                                                                  'or additional model.'}}


FFMPEG_DENOISE_TRANSLATIONS_EN = {'en': {'FFmpeg · débruitage prudent': 'FFmpeg · cautious noise reduction',
        'Filtre passe-haut/passe-bas et débruitage spectral modéré. N’isole pas les voix qui se chevauchent.': 'High-pass/low-pass '
                                                                                                               'filtering '
                                                                                                               'and '
                                                                                                               'moderate '
                                                                                                               'spectral '
                                                                                                               'noise '
                                                                                                               'reduction. '
                                                                                                               'Does '
                                                                                                               'not '
                                                                                                               'isolate '
                                                                                                               'overlapping '
                                                                                                               'voices.',
        'Intensité du débruitage': 'Noise reduction strength',
        'Un débruitage trop fort peut effacer des consonnes faibles.': 'Excessive noise reduction can remove '
                                                                       'weak consonants.',
        'Légère': 'Light',
        'Modérée': 'Moderate',
        'Forte': 'Strong'}}


DEEPFILTERNET_TRANSLATIONS_EN = {'en': {'DeepFilterNet · amélioration neuronale': 'DeepFilterNet · neural enhancement',
        'Réduction de bruit par modèle local facultatif. N’est pas un séparateur de plusieurs interlocuteurs.': 'Optional '
                                                                                                                'local-model '
                                                                                                                'noise '
                                                                                                                'reduction. '
                                                                                                                'It '
                                                                                                                'does '
                                                                                                                'not '
                                                                                                                'separate '
                                                                                                                'multiple '
                                                                                                                'speakers.',
        'Binaire DeepFilterNet': 'DeepFilterNet binary',
        'Exécutable installé séparément.': 'Executable installed separately.',
        'Modèle DeepFilterNet': 'DeepFilterNet model',
        'Archive du modèle téléchargée séparément.': 'Model archive downloaded separately.',
        'Binaires DeepFilterNet': 'DeepFilterNet binaries',
        'Téléchargez le binaire officiel adapté à votre système ; Glimio ne l’installe pas automatiquement.': 'Download '
                                                                                                              'the '
                                                                                                              'official '
                                                                                                              'binary '
                                                                                                              'for '
                                                                                                              'your '
                                                                                                              'system; '
                                                                                                              'Glimio '
                                                                                                              'does '
                                                                                                              'not '
                                                                                                              'install '
                                                                                                              'it '
                                                                                                              'automatically.',
        'Documentation et modèles DeepFilterNet': 'DeepFilterNet documentation and models',
        'Consultez les instructions officielles pour les modèles et leur format tar.gz.': 'See the official '
                                                                                          'instructions for '
                                                                                          'models and their '
                                                                                          'tar.gz format.',
        'Licence DeepFilterNet': 'DeepFilterNet license',
        'Vérifiez la licence du code et les conditions applicables aux modèles téléchargés.': 'Check the '
                                                                                              'code license '
                                                                                              'and the terms '
                                                                                              'applicable to '
                                                                                              'downloaded '
                                                                                              'models.',
        'Modèle local incomplet : {path} (hyperparams.yaml requis)': 'Local model incomplete: {path} '
                                                                     '(hyperparams.yaml required)',
        'Poids du modèle introuvables dans : {path}': 'Model weights not found in: {path}'}}


NO_SEPARATION_TRANSLATIONS_EN = {'en': {'Aucune séparation de sources': 'No source separation',
        'Ne tente pas de démêler les voix superposées. Recommandé lorsque les voix ne se chevauchent pas.': 'Does '
                                                                                                            'not '
                                                                                                            'try '
                                                                                                            'to '
                                                                                                            'disentangle '
                                                                                                            'overlapping '
                                                                                                            'voices. '
                                                                                                            'Recommended '
                                                                                                            'when '
                                                                                                            'speakers '
                                                                                                            'do '
                                                                                                            'not '
                                                                                                            'talk '
                                                                                                            'over '
                                                                                                            'one '
                                                                                                            'another.'}}


SPEECHBRAIN_SEPFORMER_TRANSLATIONS_EN = {'en': {'Sépare un mélange en deux pistes vocales. Modèle générique entraîné sur WSJ0-2Mix (anglais propre) ; résultats variables sur les réunions, le français, le bruit et les voix non superposées. À activer explicitement.': 'Separates '
                                                                                                                                                                                                                                  'a '
                                                                                                                                                                                                                                  'mixture '
                                                                                                                                                                                                                                  'into '
                                                                                                                                                                                                                                  'two '
                                                                                                                                                                                                                                  'vocal '
                                                                                                                                                                                                                                  'tracks. '
                                                                                                                                                                                                                                  'General '
                                                                                                                                                                                                                                  'model '
                                                                                                                                                                                                                                  'trained '
                                                                                                                                                                                                                                  'on '
                                                                                                                                                                                                                                  'WSJ0-2Mix '
                                                                                                                                                                                                                                  '(clean '
                                                                                                                                                                                                                                  'English); '
                                                                                                                                                                                                                                  'results '
                                                                                                                                                                                                                                  'vary '
                                                                                                                                                                                                                                  'for '
                                                                                                                                                                                                                                  'meetings, '
                                                                                                                                                                                                                                  'French, '
                                                                                                                                                                                                                                  'noise, '
                                                                                                                                                                                                                                  'and '
                                                                                                                                                                                                                                  'non-overlapping '
                                                                                                                                                                                                                                  'speech. '
                                                                                                                                                                                                                                  'Enable '
                                                                                                                                                                                                                                  'it '
                                                                                                                                                                                                                                  'explicitly.',
        'Installe SpeechBrain et ses dépendances. Le choix d’une build PyTorch CPU/CUDA dépend de la machine ; si l’installation automatique choisit une build inadaptée, consultez la documentation PyTorch puis relancez Glimio.': 'Installs '
                                                                                                                                                                                                                                     'SpeechBrain '
                                                                                                                                                                                                                                     'and '
                                                                                                                                                                                                                                     'its '
                                                                                                                                                                                                                                     'dependencies. '
                                                                                                                                                                                                                                     'The '
                                                                                                                                                                                                                                     'correct '
                                                                                                                                                                                                                                     'PyTorch '
                                                                                                                                                                                                                                     'CPU/CUDA '
                                                                                                                                                                                                                                     'build '
                                                                                                                                                                                                                                     'depends '
                                                                                                                                                                                                                                     'on '
                                                                                                                                                                                                                                     'your '
                                                                                                                                                                                                                                     'hardware; '
                                                                                                                                                                                                                                     'if '
                                                                                                                                                                                                                                     'automatic '
                                                                                                                                                                                                                                     'installation '
                                                                                                                                                                                                                                     'selects '
                                                                                                                                                                                                                                     'an '
                                                                                                                                                                                                                                     'unsuitable '
                                                                                                                                                                                                                                     'build, '
                                                                                                                                                                                                                                     'consult '
                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                     'PyTorch '
                                                                                                                                                                                                                                     'documentation '
                                                                                                                                                                                                                                     'and '
                                                                                                                                                                                                                                     'restart '
                                                                                                                                                                                                                                     'Glimio.',
        'Dossier local du modèle SepFormer': 'Local SepFormer model directory',
        'Dossier pré-téléchargé contenant notamment hyperparams.yaml et les poids du modèle. Aucun téléchargement automatique n’est effectué.': 'Pre-downloaded '
                                                                                                                                                'directory '
                                                                                                                                                'containing '
                                                                                                                                                'hyperparams.yaml '
                                                                                                                                                'and '
                                                                                                                                                'the '
                                                                                                                                                'model '
                                                                                                                                                'weights. '
                                                                                                                                                'Nothing '
                                                                                                                                                'is '
                                                                                                                                                'downloaded '
                                                                                                                                                'automatically.',
        'Périphérique': 'Device',
        'CUDA nécessite une installation PyTorch compatible.': 'CUDA requires a compatible PyTorch '
                                                               'installation.',
        'Automatique': 'Automatic',
        'Longueur des blocs de séparation (secondes)': 'Source separation chunk length (seconds)',
        'Petits blocs pour limiter la mémoire ; les identités sont réconciliées avec les embeddings de voix.': 'Short '
                                                                                                               'chunks '
                                                                                                               'limit '
                                                                                                               'memory '
                                                                                                               'use; '
                                                                                                               'identities '
                                                                                                               'are '
                                                                                                               'reconciled '
                                                                                                               'using '
                                                                                                               'speaker '
                                                                                                               'embeddings.',
        'Modèle SepFormer WSJ0-2Mix': 'SepFormer WSJ0-2Mix model',
        'Deux voix anglaises issues de mélanges relativement propres : résultats variables sur des réunions françaises.': 'Two '
                                                                                                                          'English '
                                                                                                                          'voices '
                                                                                                                          'from '
                                                                                                                          'relatively '
                                                                                                                          'clean '
                                                                                                                          'mixtures; '
                                                                                                                          'results '
                                                                                                                          'vary '
                                                                                                                          'on '
                                                                                                                          'French '
                                                                                                                          'meetings.',
        'Documentation SpeechBrain': 'SpeechBrain documentation',
        'Installer PyTorch (CPU/CUDA)': 'Install PyTorch (CPU/CUDA)',
        'Choisissez le backend correspondant au matériel si le premier installateur ne convient pas.': 'Choose '
                                                                                                       'the '
                                                                                                       'backend '
                                                                                                       'matching '
                                                                                                       'your '
                                                                                                       'hardware '
                                                                                                       'if '
                                                                                                       'the '
                                                                                                       'default '
                                                                                                       'installer '
                                                                                                       'is '
                                                                                                       'unsuitable.',
        'Licence du modèle SepFormer': 'SepFormer model license',
        'Vérifiez la licence et la model card avant redistribuer ou utiliser les poids.': 'Check the license '
                                                                                          'and model card '
                                                                                          'before '
                                                                                          'redistributing or '
                                                                                          'using the '
                                                                                          'weights.',
        'paquet Python speechbrain (extra separation)': 'Python package speechbrain (separation extra)',
        'paquet Python torch (extra separation)': 'Python package torch (separation extra)',
        'paquet Python torchaudio (extra separation)': 'Python package torchaudio (separation extra)',
        'Modèle local incomplet : {path} (hyperparams.yaml requis)': 'Local model incomplete: {path} '
                                                                     '(hyperparams.yaml required)',
        'Poids du modèle introuvables dans : {path}': 'Model weights not found in: {path}'}}


NONE_SPEAKER_EMBEDDING_TRANSLATIONS_EN = {'en': {'Aucun rapprochement global des voix': 'No global speaker matching',
        'Désactive les embeddings globaux. Les identités restent locales à chaque piste/bloc ; SepFormer exige un provider d’embeddings compatible.': 'Disables '
                                                                                                                                                      'global '
                                                                                                                                                      'embeddings. '
                                                                                                                                                      'Identities '
                                                                                                                                                      'remain '
                                                                                                                                                      'local '
                                                                                                                                                      'to '
                                                                                                                                                      'each '
                                                                                                                                                      'track/chunk; '
                                                                                                                                                      'SepFormer '
                                                                                                                                                      'requires '
                                                                                                                                                      'a '
                                                                                                                                                      'compatible '
                                                                                                                                                      'embedding '
                                                                                                                                                      'provider.'}}


SPEECHBRAIN_ECAPA_TRANSLATIONS_EN = {'en': {'SpeechBrain ECAPA · identité vocale': 'SpeechBrain ECAPA · speaker identity',
        'Produit des embeddings de voix locaux pour conserver des identifiants cohérents entre blocs de séparation.': 'Produces '
                                                                                                                      'local '
                                                                                                                      'speaker '
                                                                                                                      'embeddings '
                                                                                                                      'to '
                                                                                                                      'preserve '
                                                                                                                      'consistent '
                                                                                                                      'identities '
                                                                                                                      'across '
                                                                                                                      'separation '
                                                                                                                      'chunks.',
        'Installe SpeechBrain et ses dépendances. Si PyTorch/CUDA ne correspond pas à votre machine, choisissez le build adapté via pytorch.org.': 'Installs '
                                                                                                                                                   'SpeechBrain '
                                                                                                                                                   'and '
                                                                                                                                                   'its '
                                                                                                                                                   'dependencies. '
                                                                                                                                                   'If '
                                                                                                                                                   'the '
                                                                                                                                                   'PyTorch/CUDA '
                                                                                                                                                   'build '
                                                                                                                                                   'does '
                                                                                                                                                   'not '
                                                                                                                                                   'match '
                                                                                                                                                   'your '
                                                                                                                                                   'hardware, '
                                                                                                                                                   'choose '
                                                                                                                                                   'a '
                                                                                                                                                   'suitable '
                                                                                                                                                   'build '
                                                                                                                                                   'at '
                                                                                                                                                   'pytorch.org.',
        'Dossier local du modèle ECAPA': 'Local ECAPA model directory',
        'Dossier de modèle SpeechBrain pré-téléchargé contenant hyperparams.yaml et les poids.': 'Pre-downloaded '
                                                                                                 'SpeechBrain '
                                                                                                 'model '
                                                                                                 'directory '
                                                                                                 'containing '
                                                                                                 'hyperparams.yaml '
                                                                                                 'and the '
                                                                                                 'weights.',
        'Modèle ECAPA-TDNN VoxCeleb': 'ECAPA-TDNN VoxCeleb model',
        'Modèle de représentation vocale pour rapprocher des segments appartenant à la même personne.': 'Speaker '
                                                                                                        'representation '
                                                                                                        'model '
                                                                                                        'for '
                                                                                                        'matching '
                                                                                                        'segments '
                                                                                                        'that '
                                                                                                        'belong '
                                                                                                        'to '
                                                                                                        'the '
                                                                                                        'same '
                                                                                                        'person.',
        'Documentation SpeechBrain': 'SpeechBrain documentation',
        'Installer PyTorch (CPU/CUDA)': 'Install PyTorch (CPU/CUDA)',
        'Licence du modèle ECAPA': 'ECAPA model license',
        'paquet Python speechbrain (extra separation)': 'Python package speechbrain (separation extra)',
        'paquet Python torch (extra separation)': 'Python package torch (separation extra)',
        'paquet Python torchaudio (extra separation)': 'Python package torchaudio (separation extra)',
        'Modèle local incomplet : {path} (hyperparams.yaml requis)': 'Local model incomplete: {path} '
                                                                     '(hyperparams.yaml required)',
        'Poids du modèle introuvables dans : {path}': 'Model weights not found in: {path}'}}


NO_ENHANCEMENT_INFO = ProviderInfo(
    id="no-enhancement", name="Aucun prétraitement", task="enhancement",
    description="Utilise l’audio source tel quel, sans filtre ni modèle supplémentaire.",
    execution="embedded", capabilities=("offline", "lossless-source"),

    translations=NO_ENHANCEMENT_TRANSLATIONS_EN,
)

FFMPEG_ENHANCEMENT_INFO = ProviderInfo(
    id="ffmpeg-denoise", name="FFmpeg · débruitage prudent", task="enhancement",
    description="Filtre passe-haut/passe-bas et débruitage spectral modéré. N’isole pas les voix qui se chevauchent.",
    execution="system_executable", capabilities=("offline", "denoising", "no-extra-model"),
    options=(ProviderOption(
        key="noise_reduction", label="Intensité du débruitage", type="select", default="moderate",
        choices=(ProviderOptionChoice("light", "Légère"), ProviderOptionChoice("moderate", "Modérée"), ProviderOptionChoice("strong", "Forte")),
        description="Un débruitage trop fort peut effacer des consonnes faibles.", advanced=True, per_job=True,
    ),), requires=("ffmpeg",),

    translations=FFMPEG_DENOISE_TRANSLATIONS_EN,
)

DEEPFILTER_ENHANCEMENT_INFO = ProviderInfo(
    id="deepfilternet", name="DeepFilterNet · amélioration neuronale", task="enhancement",
    description="Réduction de bruit par modèle local facultatif. N’est pas un séparateur de plusieurs interlocuteurs.",
    execution="system_executable", capabilities=("offline", "neural-denoising"),
    setup_links=(
        ProviderResourceLink("Binaires DeepFilterNet", "https://github.com/Rikorose/DeepFilterNet/releases", "binary", "Téléchargez le binaire officiel adapté à votre système ; Glimio ne l’installe pas automatiquement."),
        ProviderResourceLink("Documentation et modèles DeepFilterNet", "https://github.com/Rikorose/DeepFilterNet", "documentation", "Consultez les instructions officielles pour les modèles et leur format tar.gz."),
        ProviderResourceLink("Licence DeepFilterNet", "https://github.com/Rikorose/DeepFilterNet", "license", "Vérifiez la licence du code et les conditions applicables aux modèles téléchargés."),
    ),
    options=(
        ProviderOption(key="deep_filter_executable", label="Binaire DeepFilterNet", type="path", default="bin/speech/deep-filter.exe", description="Exécutable installé séparément.", advanced=True),
        ProviderOption(key="deep_filter_model", label="Modèle DeepFilterNet", type="path", default="models/speech-enhancement/model.tar.gz", description="Archive du modèle téléchargée séparément.", advanced=True),
    ), requires=("ffmpeg",),

    translations=DEEPFILTERNET_TRANSLATIONS_EN,
)

NO_SEPARATION_INFO = ProviderInfo(
    id="no-separation", name="Aucune séparation de sources", task="separation",
    description="Ne tente pas de démêler les voix superposées. Recommandé lorsque les voix ne se chevauchent pas.",
    execution="embedded", capabilities=("offline", "no-extra-model"),

    translations=NO_SEPARATION_TRANSLATIONS_EN,
)

SPEECHBRAIN_SEPARATION_INFO = ProviderInfo(
    id="speechbrain-sepformer", name="SpeechBrain SepFormer · 2 sources", task="separation",
    description=("Sépare un mélange en deux pistes vocales. Modèle générique entraîné sur WSJ0-2Mix (anglais propre) ; "
                 "résultats variables sur les réunions, le français, le bruit et les voix non superposées. À activer explicitement."),
    execution="embedded", capabilities=("offline", "two-source-separation", "chunked", "speaker-order-linking"),
    python_install_extra="separation",
    python_install_packages=("speechbrain>=1.0.0",),
    python_install_note=("Installe SpeechBrain et ses dépendances. Le choix d’une build PyTorch CPU/CUDA dépend de la machine ; "
                         "si l’installation automatique choisit une build inadaptée, consultez la documentation PyTorch puis relancez Glimio."),
    setup_links=(
        ProviderResourceLink("Modèle SepFormer WSJ0-2Mix", "https://huggingface.co/speechbrain/sepformer-wsj02mix", "model", "Deux voix anglaises issues de mélanges relativement propres : résultats variables sur des réunions françaises."),
        ProviderResourceLink("Documentation SpeechBrain", "https://speechbrain.github.io/", "documentation"),
        ProviderResourceLink("Installer PyTorch (CPU/CUDA)", "https://pytorch.org/get-started/locally/", "package", "Choisissez le backend correspondant au matériel si le premier installateur ne convient pas."),
        ProviderResourceLink("Licence du modèle SepFormer", "https://huggingface.co/speechbrain/sepformer-wsj02mix", "license", "Vérifiez la licence et la model card avant redistribuer ou utiliser les poids."),
    ),
    options=(
        ProviderOption(key="model_dir", label="Dossier local du modèle SepFormer", type="path", default="models/source-separation/sepformer-wsj02mix", description="Dossier pré-téléchargé contenant notamment hyperparams.yaml et les poids du modèle. Aucun téléchargement automatique n’est effectué.", required=True, advanced=True),
        ProviderOption(key="device", label="Périphérique", type="select", default="auto", choices=(ProviderOptionChoice("auto", "Automatique"), ProviderOptionChoice("cpu", "CPU"), ProviderOptionChoice("cuda", "CUDA")), description="CUDA nécessite une installation PyTorch compatible.", advanced=True),
        ProviderOption(key="chunk_seconds", label="Longueur des blocs de séparation (secondes)", type="number", default=30, minimum=10, maximum=60, step=5, description="Petits blocs pour limiter la mémoire ; les identités sont réconciliées avec les embeddings de voix.", advanced=True, per_job=True),
    ), requires=("ffmpeg", "speechbrain-ecapa"),

    translations=SPEECHBRAIN_SEPFORMER_TRANSLATIONS_EN,
)

NO_EMBEDDING_INFO = ProviderInfo(
    id="none-speaker-embedding", name="Aucun rapprochement global des voix", task="speaker_embedding",
    description="Désactive les embeddings globaux. Les identités restent locales à chaque piste/bloc ; SepFormer exige un provider d’embeddings compatible.",
    execution="embedded", capabilities=("offline", "no-extra-model"),

    translations=NONE_SPEAKER_EMBEDDING_TRANSLATIONS_EN,
)

SPEECHBRAIN_EMBEDDING_INFO = ProviderInfo(
    id="speechbrain-ecapa", name="SpeechBrain ECAPA · identité vocale", task="speaker_embedding",
    description="Produit des embeddings de voix locaux pour conserver des identifiants cohérents entre blocs de séparation.",
    execution="embedded", capabilities=("offline", "speaker-embeddings", "cross-chunk-linking"),
    python_install_extra="separation",
    python_install_packages=("speechbrain>=1.0.0",),
    python_install_note="Installe SpeechBrain et ses dépendances. Si PyTorch/CUDA ne correspond pas à votre machine, choisissez le build adapté via pytorch.org.",
    setup_links=(
        ProviderResourceLink("Modèle ECAPA-TDNN VoxCeleb", "https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb", "model", "Modèle de représentation vocale pour rapprocher des segments appartenant à la même personne."),
        ProviderResourceLink("Documentation SpeechBrain", "https://speechbrain.github.io/", "documentation"),
        ProviderResourceLink("Installer PyTorch (CPU/CUDA)", "https://pytorch.org/get-started/locally/", "package"),
        ProviderResourceLink("Licence du modèle ECAPA", "https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb", "license"),
    ),
    options=(ProviderOption(
        key="model_dir", label="Dossier local du modèle ECAPA", type="path", default="models/speaker-embedding/spkrec-ecapa-voxceleb",
        description="Dossier de modèle SpeechBrain pré-téléchargé contenant hyperparams.yaml et les poids.", required=True, advanced=True,
    ),),

    translations=SPEECHBRAIN_ECAPA_TRANSLATIONS_EN,
)


class NoAudioEnhancementProvider:
    info = NO_ENHANCEMENT_INFO

    def enhance(self, request: AudioEnhancementRequest) -> AudioEnhancementResult:
        return AudioEnhancementResult(str(Path(request.audio_path).resolve()), self.info.id, False)


class FFmpegDenoiseProvider:
    info = FFMPEG_ENHANCEMENT_INFO

    def enhance(self, request: AudioEnhancementRequest) -> AudioEnhancementResult:
        strength = str(request.options.get("noise_reduction", "moderate"))
        filters = {
            "light": "highpass=f=55,lowpass=f=7800,afftdn=nr=4:nf=-48:tn=1",
            "moderate": "highpass=f=65,lowpass=f=7600,afftdn=nr=8:nf=-45:tn=1",
            "strong": "highpass=f=80,lowpass=f=7200,afftdn=nr=12:nf=-42:tn=1",
        }
        if strength not in filters:
            raise ValueError("Intensité de débruitage inconnue.")
        source = Path(request.audio_path).expanduser().resolve()
        target = Path(request.output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [str(request.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                   "-vn", "-af", filters[strength], "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)]
        _run_checked(command, request.cancel_event, "Débruitage FFmpeg")
        _ensure_wav(target, "Débruitage FFmpeg")
        return AudioEnhancementResult(str(target), self.info.id, True, {"strength": strength})


class DeepFilterNetEnhancementProvider:
    info = DEEPFILTER_ENHANCEMENT_INFO

    def enhance(self, request: AudioEnhancementRequest) -> AudioEnhancementResult:
        options = request.options
        output, selected = enhance_for_transcription(
            request.audio_path, request.output_path, mode="deepfilter", ffmpeg=request.ffmpeg,
            deep_filter_executable=str(options.get("deep_filter_executable", "bin/speech/deep-filter.exe")),
            deep_filter_model=str(options.get("deep_filter_model", "models/speech-enhancement/model.tar.gz")),
            cancel_event=request.cancel_event,
        )
        return AudioEnhancementResult(str(output), self.info.id, selected != "off", {"backend": selected})


class NoSourceSeparationProvider:
    info = NO_SEPARATION_INFO

    def separate(self, request: AudioSeparationRequest) -> AudioSeparationResult:
        return AudioSeparationResult((str(Path(request.audio_path).resolve()),), self.info.id)


class SpeechBrainEcapaEmbeddingProvider:
    """Lazy-loaded, local speaker embedding backend. It never resolves a Hub ID."""

    info = SPEECHBRAIN_EMBEDDING_INFO

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options = dict(options or {})
        self._classifier = None

    def _load(self):
        if self._classifier is not None:
            return self._classifier
        model_dir = Path(str(self.options.get("model_dir", self.info.options[0].default))).expanduser().resolve()
        if not model_dir.is_dir() or not (model_dir / "hyperparams.yaml").is_file():
            raise RuntimeError(f"Modèle ECAPA local introuvable ou incomplet : {model_dir} (hyperparams.yaml requis).")
        try:
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as exc:
            raise RuntimeError('Le provider speechbrain-ecapa nécessite le extra facultatif « separation » (SpeechBrain/PyTorch/Torchaudio).') from exc
        device = _selected_device(str(self.options.get("device", "auto")))
        self._classifier = EncoderClassifier.from_hparams(
            source=str(model_dir), savedir=str(model_dir / ".glimio-runtime"), run_opts={"device": device},
        )
        return self._classifier

    def embed(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        if not audio.size:
            raise ValueError("Impossible de calculer un embedding sur un signal vide.")
        try:
            import torch
            import torchaudio.functional as AF
        except ImportError as exc:
            raise RuntimeError("Le provider ECAPA nécessite PyTorch et Torchaudio.") from exc
        waveform = torch.as_tensor(np.asarray(audio, dtype=np.float32)).reshape(1, -1)
        if sample_rate != 16000:
            waveform = AF.resample(waveform, orig_freq=int(sample_rate), new_freq=16000)
        waveform = waveform.to(_selected_device(str(self.options.get("device", "auto"))))
        classifier = self._load()
        with torch.no_grad():
            embedding = classifier.encode_batch(waveform).detach().cpu().numpy().reshape(-1)
        norm = float(np.linalg.norm(embedding))
        if norm > 0:
            embedding = embedding / norm
        return embedding.astype(np.float32, copy=False)


class SpeechBrainSepFormerProvider:
    """Local chunked SepFormer separation with ECAPA-based source-order matching."""

    info = SPEECHBRAIN_SEPARATION_INFO

    def __init__(self, options: dict[str, Any] | None = None, *, embedding_provider: SpeakerEmbeddingProvider | None = None) -> None:
        self.options = dict(options or {})
        self.embedding_provider = embedding_provider
        self._separator = None
        self._centroids: list[np.ndarray] = []
        self._centroid_ids: list[int] = []
        self._centroid_counts: list[int] = []
        self._next_speaker_id = 0
        self.match_threshold = float(self.options.get("identity_threshold", 0.62))
        if not 0.0 <= self.match_threshold <= 1.0:
            raise ValueError("Le seuil de rapprochement des voix doit être compris entre 0 et 1.")

    def _load(self):
        if self._separator is not None:
            return self._separator
        model_dir = Path(str(self.options.get("model_dir", self.info.options[0].default))).expanduser().resolve()
        if not model_dir.is_dir() or not (model_dir / "hyperparams.yaml").is_file():
            raise RuntimeError(f"Modèle SepFormer local introuvable ou incomplet : {model_dir} (hyperparams.yaml requis).")
        if self.embedding_provider is None:
            raise RuntimeError("SepFormer requiert le provider de dépendance speechbrain-ecapa pour garder l’identité des sources entre blocs.")
        try:
            from speechbrain.inference.separation import SepformerSeparation
        except ImportError as exc:
            raise RuntimeError('Le provider speechbrain-sepformer nécessite le extra facultatif « separation » (SpeechBrain/PyTorch/Torchaudio).') from exc
        device = _selected_device(str(self.options.get("device", "auto")))
        # Force offline mode: configured local paths must contain every model artifact.
        old_hf = os.environ.get("HF_HUB_OFFLINE")
        old_transformers = os.environ.get("TRANSFORMERS_OFFLINE")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            self._separator = SepformerSeparation.from_hparams(
                source=str(model_dir), savedir=str(model_dir / ".glimio-runtime"), run_opts={"device": device},
            )
        finally:
            if old_hf is None:
                os.environ.pop("HF_HUB_OFFLINE", None)
            else:
                os.environ["HF_HUB_OFFLINE"] = old_hf
            if old_transformers is None:
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
            else:
                os.environ["TRANSFORMERS_OFFLINE"] = old_transformers
        return self._separator

    def state_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable multi-speaker identity state for checkpoints."""
        return {
            "schema_version": 2,
            "centroids": [centroid.astype(np.float32).tolist() for centroid in self._centroids],
            "centroid_ids": list(self._centroid_ids),
            "centroid_counts": list(self._centroid_counts),
            "next_speaker_id": self._next_speaker_id,
        }

    def load_state_dict(self, payload: Any) -> None:
        if not isinstance(payload, dict) or payload.get("schema_version") != 2:
            return
        centroids = payload.get("centroids")
        ids = payload.get("centroid_ids")
        counts = payload.get("centroid_counts")
        try:
            if not isinstance(centroids, list) or not isinstance(ids, list) or not isinstance(counts, list):
                return
            parsed_centroids = [np.asarray(item, dtype=np.float32) for item in centroids]
            parsed_ids = [int(item) for item in ids]
            parsed_counts = [max(1, int(item)) for item in counts]
            if not (len(parsed_centroids) == len(parsed_ids) == len(parsed_counts)):
                return
            if any(item.ndim != 1 or not item.size or not np.all(np.isfinite(item)) for item in parsed_centroids):
                return
            self._centroids = parsed_centroids
            self._centroid_ids = parsed_ids
            self._centroid_counts = parsed_counts
            self._next_speaker_id = max(int(payload.get("next_speaker_id", 0)), max(parsed_ids, default=-1) + 1)
        except (TypeError, ValueError):
            self._centroids, self._centroid_ids, self._centroid_counts = [], [], []
            self._next_speaker_id = 0

    def _voice_embedding(self, samples: np.ndarray) -> np.ndarray | None:
        """Embed a short, energetic window rather than 30 seconds of mostly silence/noise."""
        if self.embedding_provider is None or samples.size < 8000:
            return None
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        # SepFormer input/output is 8 kHz. 250 ms frames are enough to find a
        # compact active region without requiring another heavy VAD provider.
        frame_size = 2000
        frame_count = len(samples) // frame_size
        if frame_count < 3:
            return None
        frames = samples[:frame_count * frame_size].reshape(frame_count, frame_size)
        rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
        peak_rms = float(np.max(rms)) if rms.size else 0.0
        if peak_rms < 0.0012:
            return None
        active = rms >= max(0.0012, peak_rms * 0.20)
        target_frames = min(frame_count, 12)  # at most a 3-second embedding window
        active_prefix = np.concatenate(([0], np.cumsum(active.astype(np.int32))))
        energy_prefix = np.concatenate(([0.0], np.cumsum(np.minimum(rms, peak_rms))))
        best_start = 0
        best_score = -1.0
        for frame_start in range(frame_count - target_frames + 1):
            frame_end = frame_start + target_frames
            active_count = int(active_prefix[frame_end] - active_prefix[frame_start])
            mean_energy = float((energy_prefix[frame_end] - energy_prefix[frame_start]) / target_frames)
            score = active_count / target_frames + min(1.0, mean_energy / max(peak_rms, 1e-6)) * 0.15
            if score > best_score:
                best_score, best_start = score, frame_start
        voice_start = best_start * frame_size
        voice_end = min(len(samples), (best_start + target_frames) * frame_size)
        if voice_end - voice_start < int(0.75 * 8000):
            return None
        selected = samples[voice_start:voice_end]
        if float(np.sqrt(np.mean(selected * selected) + 1e-12)) < 0.0012:
            return None
        try:
            vector = np.asarray(self.embedding_provider.embed(selected, 8000), dtype=np.float32).reshape(-1)
        except Exception:
            raise
        norm = float(np.linalg.norm(vector))
        if not vector.size or not np.all(np.isfinite(vector)) or norm < 1e-6:
            return None
        return vector / norm

    def _assign_order(self, chunks: list[np.ndarray]) -> tuple[list[tuple[int, int | None, np.ndarray]], tuple[str | None, ...]]:
        """Assign each current source to one of N global identities, not just two.

        The separator emits two signals per window, but a four-hour meeting may contain
        more than two different people over time. ECAPA embeddings therefore map each
        output to any existing identity above the threshold or create a new one. A stem
        with no credible voice is left unlabeled instead of being forced onto a person.
        """
        vectors = [self._voice_embedding(samples) for samples in chunks]
        source_ids: list[int | None] = [None] * len(chunks)
        matched_existing: dict[int, int] = {}
        new_vectors: dict[int, np.ndarray] = {}
        used_ids: set[int] = set()

        # Resolve the most confident matches first, then keep output sources distinct
        # within the same chunk. This prevents two simultaneous stems being assigned
        # to the same global identity just because both are similar to one speaker.
        valid_indexes = [index for index, vector in enumerate(vectors) if vector is not None]
        best_scores: dict[int, float] = {}
        score_rows: dict[int, list[tuple[float, int, int]]] = {}
        # Centroids stay unchanged until all current stems have been scored. Cache
        # their norms once instead of recalculating each norm for every stem.
        centroid_norms = [float(np.linalg.norm(centroid)) for centroid in self._centroids]
        for index in valid_indexes:
            vector = vectors[index]
            assert vector is not None
            vector_norm = float(np.linalg.norm(vector))
            scores = [
                float(np.dot(vector, centroid) / max(1e-8, vector_norm * centroid_norm))
                for centroid, centroid_norm in zip(self._centroids, centroid_norms)
            ]
            score_rows[index] = sorted(
                ((score, centroid_index, self._centroid_ids[centroid_index])
                 for centroid_index, score in enumerate(scores)), reverse=True,
            )
            best_scores[index] = score_rows[index][0][0] if score_rows[index] else -1.0
        valid_indexes.sort(key=lambda index: (best_scores[index], -index), reverse=True)

        for index in valid_indexes:
            candidate = next(
                ((score, centroid_index, speaker_id) for score, centroid_index, speaker_id in score_rows[index]
                 if score >= self.match_threshold and speaker_id not in used_ids),
                None,
            )
            if candidate is not None:
                _, centroid_index, speaker_id = candidate
                source_ids[index] = speaker_id
                used_ids.add(speaker_id)
                matched_existing[index] = centroid_index
            else:
                speaker_id = self._next_speaker_id
                self._next_speaker_id += 1
                source_ids[index] = speaker_id
                used_ids.add(speaker_id)
                vector = vectors[index]
                assert vector is not None
                new_vectors[index] = vector

        # Do not merge uncertain stems into old identities; label them as a new
        # per-window speaker when they carry audio energy, but leave silence unlabeled.
        for index, samples in enumerate(chunks):
            if source_ids[index] is not None:
                continue
            rms = float(np.sqrt(np.mean(np.asarray(samples, dtype=np.float32) ** 2) + 1e-12)) if len(samples) else 0.0
            peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
            if rms >= 0.00035 and peak >= 0.001:
                source_ids[index] = self._next_speaker_id
                self._next_speaker_id += 1
                used_ids.add(int(source_ids[index]))

        for index, centroid_index in matched_existing.items():
            vector = vectors[index]
            assert vector is not None
            old_count = self._centroid_counts[centroid_index]
            new_count = old_count + 1
            merged = self._centroids[centroid_index] * (old_count / new_count) + vector / new_count
            norm = float(np.linalg.norm(merged))
            self._centroids[centroid_index] = merged / norm if norm > 0 else merged
            self._centroid_counts[centroid_index] = new_count
        for index, vector in new_vectors.items():
            speaker_id = source_ids[index]
            assert speaker_id is not None
            self._centroids.append(vector.copy())
            self._centroid_ids.append(speaker_id)
            self._centroid_counts.append(1)

        ordered = [(index, source_ids[index], np.asarray(chunks[index], dtype=np.float32)) for index in range(len(chunks))]
        labels = tuple(f"speaker_{speaker_id:02d}" if speaker_id is not None else None for speaker_id in source_ids)
        return ordered, labels

    def separate(self, request: AudioSeparationRequest) -> AudioSeparationResult:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError('Le provider speechbrain-sepformer nécessite PyTorch. Installez un build CPU/CUDA compatible, puis le extra « separation ».') from exc
        source = Path(request.audio_path).expanduser().resolve()
        output_dir = Path(request.output_directory).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        prefix = request.output_prefix
        chunk_seconds = int(self.options.get("chunk_seconds", 30))
        if not 10 <= chunk_seconds <= 60:
            raise ValueError("La taille des blocs SepFormer doit être comprise entre 10 et 60 secondes.")
        separator = self._load()
        paths = [output_dir / f"{prefix}_source_{index + 1:02d}.wav" for index in range(2)]
        source_ids: tuple[str | None, ...] = (None, None)
        ffmpeg = str(request.ffmpeg or "ffmpeg")
        with tempfile.TemporaryDirectory(prefix="glimio-separate-", dir=str(output_dir)) as temporary:
            temp = Path(temporary)
            mono_8k = temp / "source_8k.wav"
            _run_checked([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", str(mono_8k)], request.cancel_event, "Préparation de la séparation SepFormer")
            _ensure_wav(mono_8k, "Préparation de la séparation SepFormer")
            raw_stems = [temp / f"stem_{index}.wav" for index in range(2)]
            with wave.open(str(mono_8k), "rb") as audio_input, wave.open(str(raw_stems[0]), "wb") as stem0, wave.open(str(raw_stems[1]), "wb") as stem1:
                if audio_input.getnchannels() != 1 or audio_input.getsampwidth() != 2 or audio_input.getframerate() != 8000:
                    raise RuntimeError("La préparation audio SepFormer doit produire un WAV mono PCM16 à 8 kHz.")
                outputs = [stem0, stem1]
                for output in outputs:
                    output.setnchannels(1); output.setsampwidth(2); output.setframerate(8000)
                block_frames = chunk_seconds * 8000
                if audio_input.getnframes() > block_frames + 80:
                    raise RuntimeError(
                        f"Le provider SepFormer traite une seule fenêtre de {chunk_seconds} s par appel; "
                        "la fenêtre doit être découpée par l’orchestrateur pour garder un identifiant de voix stable."
                    )
                while True:
                    if request.cancel_event is not None and request.cancel_event.is_set():
                        raise RuntimeError("Séparation audio annulée.")
                    raw = audio_input.readframes(block_frames)
                    if not raw:
                        break
                    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
                    mixture = torch.from_numpy(samples.copy()).reshape(1, -1)
                    with torch.no_grad():
                        estimates = separator.separate_batch(mixture)
                    if hasattr(estimates, "detach"):
                        estimates = estimates.detach().cpu().numpy()
                    estimates = np.asarray(estimates)
                    estimates = estimates[0] if estimates.ndim == 3 else estimates
                    if estimates.ndim != 2:
                        raise RuntimeError(f"Sortie SepFormer inattendue : shape={estimates.shape}.")
                    # SpeechBrain's documented shape is [frames, sources]. Accept [sources, frames] too.
                    if estimates.shape[0] == 2 and estimates.shape[1] != 2:
                        estimates = estimates.T
                    if estimates.shape[1] < 2:
                        raise RuntimeError("SepFormer n’a pas produit deux sources audio.")
                    stem_chunks = [np.asarray(estimates[:, index], dtype=np.float32) for index in range(2)]
                    ordered, source_ids = self._assign_order(stem_chunks)
                    expected = len(samples)
                    for output_index, _speaker_id, chunk in ordered:
                        if len(chunk) < expected:
                            chunk = np.pad(chunk, (0, expected - len(chunk)))
                        chunk = chunk[:expected]
                        pcm = np.clip(chunk, -1.0, 1.0)
                        pcm = np.round(pcm * 32767.0).astype("<i2")
                        outputs[output_index].writeframes(pcm.tobytes())
            for raw_path, final_path in zip(raw_stems, paths):
                _run_checked([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_path), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(final_path)], request.cancel_event, "Conversion des sources séparées")
                _ensure_wav(final_path, "Conversion des sources séparées")
        return AudioSeparationResult(
            tuple(str(path) for path in paths), self.info.id,
            {"source_ids": list(source_ids), "chunk_seconds": chunk_seconds,
             "identity_count": self._next_speaker_id, "identity_threshold": self.match_threshold,
             "model_license": "Apache-2.0 (upstream model card)",
             "model_limitations": "Model trained on clean English two-speaker mixtures; validate French/noisy meeting audio."},
            source_ids=source_ids,
        )


def _run_checked(command: list[str], cancel_event: Any, label: str) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError(f"{label} annulé.")
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"Impossible de lancer {command[0]} : {exc}") from exc
    while True:
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill(); process.communicate()
            raise RuntimeError(f"{label} annulé.")
        try:
            stdout, stderr = process.communicate(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            continue
    if process.returncode != 0:
        detail = (stderr or stdout or "aucun détail").strip()
        raise RuntimeError(f"{label} a échoué : {detail[-4000:]}")


def _ensure_wav(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 44:
        raise RuntimeError(f"{label} n’a créé aucun WAV exploitable : {path}")


def _selected_device(value: str) -> str:
    value = value.strip().lower()
    if value == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
    if value == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA a été sélectionné, mais PyTorch ne détecte pas de GPU CUDA.")
        except ImportError as exc:
            raise RuntimeError("CUDA nécessite PyTorch. Installez l’extra séparation correspondant à votre plateforme.") from exc
    return value


ENHANCEMENT_PROVIDER_FACTORIES = {
    "no-enhancement": lambda options: NoAudioEnhancementProvider(),
    "ffmpeg-denoise": lambda options: FFmpegDenoiseProvider(),
    "deepfilternet": lambda options: DeepFilterNetEnhancementProvider(),
}
SEPARATION_PROVIDER_FACTORIES = {
    "no-separation": lambda options, embedding: NoSourceSeparationProvider(),
    "speechbrain-sepformer": lambda options, embedding: SpeechBrainSepFormerProvider(options, embedding_provider=embedding),
}
EMBEDDING_PROVIDER_FACTORIES = {
    "none-speaker-embedding": lambda options: None,
    "speechbrain-ecapa": lambda options: SpeechBrainEcapaEmbeddingProvider(options),
}


def audio_processing_provider_infos() -> tuple[ProviderInfo, ...]:
    return (NO_ENHANCEMENT_INFO, FFMPEG_ENHANCEMENT_INFO, DEEPFILTER_ENHANCEMENT_INFO,
            NO_SEPARATION_INFO, SPEECHBRAIN_SEPARATION_INFO, NO_EMBEDDING_INFO, SPEECHBRAIN_EMBEDDING_INFO)


def create_audio_enhancement_provider(provider_id: str, options: dict[str, Any] | None = None):
    try:
        return ENHANCEMENT_PROVIDER_FACTORIES[provider_id](dict(options or {}))
    except KeyError as exc:
        raise ValueError(f"Provider d’amélioration audio inconnu : {provider_id}") from exc


def create_speaker_embedding_provider(provider_id: str, options: dict[str, Any] | None = None):
    if provider_id in (None, "", "none", "none-speaker-embedding"):
        return None
    try:
        return EMBEDDING_PROVIDER_FACTORIES[provider_id](dict(options or {}))
    except KeyError as exc:
        raise ValueError(f"Provider d’embeddings vocaux inconnu : {provider_id}") from exc


def create_source_separation_provider(provider_id: str, options: dict[str, Any] | None = None, *, embedding_provider_id: str | None = None, embedding_options: dict[str, Any] | None = None):
    try:
        factory = SEPARATION_PROVIDER_FACTORIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Provider de séparation audio inconnu : {provider_id}") from exc
    embedding = create_speaker_embedding_provider(embedding_provider_id, embedding_options)
    provider = factory(dict(options or {}), embedding)
    verify_provider_dependencies(provider.info, available_provider_ids={"ffmpeg", *([embedding_provider_id] if embedding_provider_id else [])})
    return provider


def verify_provider_dependencies(info: ProviderInfo, *, available_provider_ids: set[str]) -> None:
    missing = [dependency for dependency in info.requires if dependency not in available_provider_ids]
    if missing:
        raise RuntimeError(f"Le provider {info.id} requiert les providers suivants : {', '.join(missing)}.")


def provider_readiness(info: ProviderInfo, options: dict[str, Any] | None = None) -> tuple[bool, tuple[str, ...]]:
    """Report missing local resources/runtime packages without downloads or heavy imports."""
    values = dict(options or {})
    missing: list[str] = []

    if info.id in {"no-enhancement", "no-separation", "none-speaker-embedding"}:
        return True, ()

    if info.id == "deepfilternet":
        executable = str(values.get("deep_filter_executable", "bin/speech/deep-filter.exe"))
        model = Path(str(values.get("deep_filter_model", "models/speech-enhancement/model.tar.gz"))).expanduser()
        resolved_exe = shutil.which(executable) if "/" not in executable and "\\" not in executable else executable
        if not resolved_exe or (("/" in executable or "\\" in executable) and not Path(executable).expanduser().is_file()):
            missing.append(executable)
        if not model.is_file():
            missing.append(str(model))

    if info.id in {"speechbrain-sepformer", "speechbrain-ecapa"}:
        model = Path(str(values.get("model_dir", info.options[0].default))).expanduser()
        if not model.is_dir() or not (model / "hyperparams.yaml").is_file():
            missing.append(f"Modèle local incomplet : {model} (hyperparams.yaml requis)")
        else:
            try:
                weight_files = [
                    child for child in model.iterdir()
                    if child.is_file() and child.suffix.casefold() in {".ckpt", ".pt", ".pth"}
                ]
            except OSError:
                weight_files = []
            if not weight_files:
                missing.append(f"Poids du modèle introuvables dans : {model}")
        for package in ("speechbrain", "torch", "torchaudio"):
            try:
                import importlib.util
                available = importlib.util.find_spec(package) is not None
            except (ImportError, ValueError):
                available = False
            if not available:
                missing.append(f"paquet Python {package} (extra separation)")

    return not missing, tuple(dict.fromkeys(missing))
