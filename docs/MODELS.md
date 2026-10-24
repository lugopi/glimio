# Modèles et exécutables locaux

Glimio ne versionne pas les poids IA ou les exécutables natifs. Télécharge-les toi-même depuis les projets sources, place-les aux chemins ci-dessous, puis vérifie les licences affichées par l'éditeur au moment du téléchargement.

> **Important :** la licence AGPL à la racine couvre le code et la documentation propres à Glimio, pas automatiquement les modèles, les exécutables tiers, leurs poids convertis/quantifiés ni les bibliothèques natives. Conserve les notices et licences originales. Ne redistribue pas de poids si tu n'as pas vérifié les conditions du fichier exact téléchargé.

## Chemins attendus et sources

| Fichier local attendu | Usage | Source officielle / primaire | Conditions à vérifier |
|---|---|---|---|
| `models/llm/model.gguf` | Résumés et recherche, modèle de la famille LFM2.5 | [LiquidAI/LFM2.5-8B-A1B sur Hugging Face](https://huggingface.co/LiquidAI/LFM2.5-8B-A1B) ; [quantifications compatibles llama.cpp](https://huggingface.co/models?search=LFM2.5-8B-A1B-GGUF) | Le modèle upstream indique **LFM Open License v1.0**. Elle comprend une limite conditionnelle à l'usage commercial (« Threshold ») ; ne considère pas cette licence comme MIT. Vérifie aussi les conditions du dépôt qui fournit la quantification GGUF utilisée. |
| `models/asr/model.bin` | Reconnaissance vocale Whisper large-v3 | [Dépôt whisper.cpp et modèles convertis](https://huggingface.co/ggerganov/whisper.cpp/tree/main) ; [code et licence Whisper](https://github.com/openai/whisper/blob/main/LICENSE) | Le code/modèle Whisper source est publié sous MIT, mais garde la licence et la provenance de l'artefact `ggml` exact. La conversion/la quantification peut provenir d'un tiers. |
| `models/asr/ggml-silero-v6.2.0.bin` | VAD (détection des zones de parole) pour ignorer les silences prolongés | [Modèle Silero VAD converti pour whisper.cpp](https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin) ; [instructions officielles VAD](https://github.com/ggml-org/whisper.cpp#vad) | Le dépôt de modèles indique MIT. Conserver les notices et valider la licence de l'artefact exact distribué. |
| `models/diarization/segmentation/segmentation.onnx` | Segmentation des voix avant regroupement des locuteurs | [Modèles de segmentation de sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models) ; modèle source [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) | Le modèle source `pyannote/segmentation-3.0` affiche MIT, mais le dépôt Hugging Face demande d'accepter ses conditions avant l'accès. La version ONNX convertie est distribuée séparément : vérifie les notices/conditions associées à l'artefact sherpa-onnx exact avant toute redistribution. |
| `models/diarization/embedding/embedding.onnx` | Embeddings vocaux 3D-Speaker ERes2Net pour la diarisation | [Artefact ONNX de sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx) ; [projet 3D-Speaker et licence du code](https://github.com/modelscope/3D-Speaker/blob/main/LICENSE) | Le code du projet 3D-Speaker indique Apache-2.0, mais vérifie également les conditions exactes du poids ONNX distribué et conserve la notice fournie par la source. |
| `bin/asr/whisper-cli` (Linux) / `bin/asr/whisper-cli.exe` (Windows) | Exécutable de transcription Whisper | [whisper.cpp — releases](https://github.com/ggml-org/whisper.cpp/releases) | Télécharge la version adaptée au système et examine la licence ainsi que les bibliothèques embarquées dans l'archive choisie. |
| `bin/llm/llama-completion` (Linux) / `bin/llm/llama-completion.exe` (Windows) | Exécutable d'inférence GGUF | [llama.cpp — releases](https://github.com/ggml-org/llama.cpp/releases) | Télécharge une release officielle et conserve ses notices. Les termes du modèle GGUF restent indépendants de ceux de llama.cpp. |
| `ffmpeg` (ou `ffmpeg.exe`) | Décodage audio/vidéo, filtre anti-bruit `afftdn` | [Téléchargements FFmpeg](https://ffmpeg.org/download.html) | FFmpeg est proposé sous LGPL ou GPL selon les options de compilation et les composants activés ; la licence exacte dépend de la build téléchargée. Lis sa configuration et ses notices. |
| `bin/speech/deep-filter` (Linux) / `bin/speech/deep-filter.exe` (Windows) | Amélioration de la voix par DeepFilterNet, en option | [Releases DeepFilterNet](https://github.com/Rikorose/DeepFilterNet/releases) | Le code du projet est annoncé sous double licence MIT/Apache-2.0. Vérifie les notices de la release exacte et les conditions du binaire choisi ; ne l'inclus pas automatiquement dans un package Glimio. |
| `models/speech-enhancement/model.tar.gz` | Poids de DeepFilterNet, en option | [Projet DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) ; [guide du binaire et format du modèle](https://github.com/Rikorose/DeepFilterNet#deep-filter) | Télécharge l'archive du modèle séparément. Le mode Glimio demande une archive compatible avec le binaire `deep-filter`; garde la provenance, la licence exacte et la version du modèle. |

### Notes sur les noms

- `LFM2.5-8B-A1B` est le **nom de la famille/modèle upstream**, pas nécessairement le nom du fichier. Le chemin Glimio est générique (`model.gguf`) ; si tu utilises un GGUF quantifié, note dans tes réglages la source exacte et le niveau de quantification.
- Le fichier Whisper proposé par le centre est `ggml-large-v3-q5_0.bin` (~1,08 Go, licence indiquée MIT par le dépôt de modèles) ; copie-le ou renomme-le en `models/asr/model.bin`, ou règle le chemin dans **Paramètres**.
- `segmentation.onnx` et `embedding.onnx` sont les noms génériques utilisés par Glimio ; renomme les artefacts ONNX téléchargés ou ajuste leurs chemins dans **Paramètres**. L’artefact d’embedding proposé est `3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx` ; copie-le sous le nom local générique `embedding.onnx`. L’archive de segmentation amont inclut `model.onnx`, à copier sous `segmentation.onnx`. Vérifie les notices de licence exactes des poids distribués.
- N'enregistre jamais un fichier de modèle, une URL locale privée ou un jeton d'accès dans Git. Documente plutôt le nom, la version, la source et, si utile, le SHA-256 dans tes notes locales.

## Téléchargement manuel

Les téléchargements ne sont pas automatiques dans Glimio : cela évite de télécharger sans consentement des fichiers volumineux ou soumis à des conditions d'accès. Les chemins ci-dessous sont volontairement génériques ; renomme ou copie les fichiers téléchargés vers ces chemins, ou configure l’emplacement réel dans Paramètres. Crée les dossiers locaux suivants, ignorés par Git :

```text
bin/
├── asr/whisper-cli[.exe]
├── llm/llama-completion[.exe]
├── media/ffmpeg[.exe]  # facultatif ; peut aussi être dans PATH
└── speech/deep-filter[.exe]   # facultatif : binaire téléchargé séparément
models/
├── asr/
│   ├── model.bin
│   └── ggml-silero-v6.2.0.bin  # facultatif : VAD pour les silences
├── llm/model.gguf
├── speech-enhancement/
│   └── model.tar.gz            # facultatif : DeepFilterNet
└── diarization/
    ├── segmentation.onnx
    └── embedding.onnx
```

Après téléchargement, configure les chemins dans **Paramètres** et vérifie que les exécutables/modèles correspondent aux sources décrites ci-dessus. Les liens peuvent évoluer ; privilégie les dépôts éditeurs plutôt que les miroirs non identifiés.


## Liens de téléchargement directs vérifiés (Windows / installation manuelle)

- Whisper large-v3 Q5_0 (fichier d'environ 1,08 Go, dépôt whisper.cpp, licence affichée MIT) : https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-q5_0.bin — renommer en `models/asr/model.bin`.
- LFM2.5-8B-A1B GGUF Q4_K_M : https://huggingface.co/unsloth/LFM2.5-8B-A1B-GGUF/resolve/main/LFM2.5-8B-A1B-UD-Q4_K_M.gguf?download=true — enregistrer comme `models/llm/model.gguf`. Consulter la licence du modèle upstream avant utilisation : https://huggingface.co/LiquidAI/LFM2.5-8B-A1B/blob/main/LICENSE.
- llama.cpp Windows x64 Vulkan : https://github.com/ggml-org/llama.cpp/releases. Choisir l'archive correspondant à Windows x64 + Vulkan et vérifier le nom réel de l'exécutable inclus.
- whisper.cpp : https://github.com/ggml-org/whisper.cpp/releases. Choisir ou compiler la version appropriée ; ne pas supposer qu'une archive précompilée inclut Vulkan.
- Segmentation pyannote convertie pour sherpa-onnx : https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2. Conserver le LICENSE de l'archive et installer `model.onnx` à `models/diarization/segmentation/segmentation.onnx`.
- Embeddings sherpa-onnx : le modèle d'exemple ERes2Net est disponible à https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx. Le placer sous `models/diarization/embedding/embedding.onnx` après vérification des notices dans le dépôt source.

Les téléchargements sont lancés par clic depuis les sources officielles ; Glimio ne télécharge ni n'exécute automatiquement d'exécutable natif. Les releases Vulkan dépendent du matériel et de l'architecture, tandis que les poids peuvent avoir des conditions distinctes.
## Prétraitement de la voix, silences et licences

Le réglage **Amélioration de la voix avant transcription** du provider Whisper.cpp peut être configuré sur `Automatique`, `Désactivé`, `Débruitage FFmpeg` ou `DeepFilterNet`. En mode automatique, Glimio préfère le binaire et le modèle DeepFilterNet s'ils sont tous deux présents ; sinon il utilise `highpass`, `lowpass` et `afftdn` de FFmpeg si disponible. Le filtrage est appliqué à des blocs de transcription temporaires de 15 minutes et **ne remplace jamais les fichiers audio originaux**. Il peut améliorer l'intelligibilité avec un bruit stationnaire ou large bande, mais un filtrage trop fort peut supprimer des consonnes faibles.

Pour ignorer les longs silences, régler **Détection de parole (VAD)** sur automatique ou activée et installer le modèle Silero indiqué ci-dessus. Le mode automatique ne passe les options VAD à `whisper-cli` que lorsque le fichier modèle existe. Les réglages de seuil plus élevés rejettent davantage de bruit, avec le risque de manquer une voix faible.

**Important :** DeepFilterNet est un modèle d'amélioration de la parole (voix contre bruit), pas un modèle de séparation de plusieurs locuteurs en train de parler en même temps. La séparation des voix simultanées nécessite un modèle spécialisé différent et une validation indépendante. La diarisation actuelle détecte les tours de parole ; elle n'est pas une garantie de séparation parfaite des voix superposées.


## Séparation de sources et identité vocale (facultatif)

| Fichier local attendu | Usage | Source officielle / primaire | Conditions à vérifier |
|---|---|---|---|
| `models/source-separation/sepformer-wsj02mix/` | Séparation expérimentale d'un mélange vocal en deux sources via le provider `speechbrain-sepformer` | [Modèle SepFormer WSJ0-2Mix](https://huggingface.co/speechbrain/sepformer-wsj02mix) ; [code SpeechBrain](https://github.com/speechbrain/speechbrain) | Le dépôt du modèle affiche Apache-2.0. Le modèle a été entraîné sur WSJ0-2Mix, des mélanges propres de deux voix anglaises : ses résultats ne sont pas garantis pour des réunions françaises, bruyantes ou avec plus de deux personnes simultanées. Vérifie la licence de l'artefact précis que tu télécharges et conserve les notices.
| `models/speaker-embedding/spkrec-ecapa-voxceleb/` | Rapprochement global des voix entre les petites fenêtres et les pistes avec `speechbrain-ecapa` | [Modèle ECAPA-TDNN VoxCeleb](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) ; [code SpeechBrain](https://github.com/speechbrain/speechbrain) | Le dépôt du modèle affiche Apache-2.0. L'usage requiert SpeechBrain, PyTorch et Torchaudio installés séparément et compatibles avec le matériel. Conserve la licence du modèle exact et les licences des dépendances.

Ces deux fournisseurs sont des plugins facultatifs et aucun poids n'est livré avec Glimio. Pour préparer les modèles hors ligne, télécharge les dépôts via leurs instructions officielles puis configure les dossiers dans **Paramètres**. Le provider `speechbrain-sepformer` déclare une dépendance forte envers `speechbrain-ecapa`, car le tri des deux sorties peut s'inverser d'une fenêtre à l'autre ; il ne peut donc pas être sélectionné avec `none-speaker-embedding`. Le chemin `no-separation` reste disponible sans SpeechBrain ni PyTorch.

Exemple d'installation de la couche logicielle facultative (le choix du build PyTorch CPU/CUDA adapté reste volontaire) :

```bash
# Installer d'abord un build torch/torchaudio compatible avec l'OS et l'accélérateur.
python -m pip install -e ".[separation]"
```

L'installation des paquets Python ne télécharge pas les poids de modèles au nom de Glimio. Vérifie également les conditions d'usage des données d'entraînement et les éventuelles restrictions d'emploi des artefacts avant de redistribuer un modèle.
