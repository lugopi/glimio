# Modèles et exécutables locaux

Glimio ne versionne pas les poids IA ou les exécutables natifs. Télécharge-les toi-même depuis les projets sources, place-les aux chemins ci-dessous, puis vérifie les licences affichées par l'éditeur au moment du téléchargement.

> **Important :** la licence AGPL à la racine couvre le code et la documentation propres à Glimio, pas automatiquement les modèles, les exécutables tiers, leurs poids convertis/quantifiés ni les bibliothèques natives. Conserve les notices et licences originales. Ne redistribue pas de poids si tu n'as pas vérifié les conditions du fichier exact téléchargé.

## Chemins attendus et sources

| Fichier local attendu | Usage | Source officielle / primaire | Conditions à vérifier |
|---|---|---|---|
| `models/llm/model.gguf` | Résumés et recherche, modèle de la famille LFM2.5 | [LiquidAI/LFM2.5-8B-A1B sur Hugging Face](https://huggingface.co/LiquidAI/LFM2.5-8B-A1B) ; [quantifications compatibles llama.cpp](https://huggingface.co/models?search=LFM2.5-8B-A1B-GGUF) | Le modèle upstream indique **LFM Open License v1.0**. Elle comprend une limite conditionnelle à l'usage commercial (« Threshold ») ; ne considère pas cette licence comme MIT. Vérifie aussi les conditions du dépôt qui fournit la quantification GGUF utilisée. |
| `models/asr/model.bin` | Reconnaissance vocale Whisper large-v3 | [Dépôt whisper.cpp et modèles convertis](https://huggingface.co/ggerganov/whisper.cpp/tree/main) ; [code et licence Whisper](https://github.com/openai/whisper/blob/main/LICENSE) | Le code/modèle Whisper source est publié sous MIT, mais garde la licence et la provenance de l'artefact `ggml` exact. La conversion/le quantization peut provenir d'un tiers. |
| `models/diarization/segmentation/segmentation.onnx` | Segmentation des voix avant regroupement des locuteurs | [Modèles de segmentation de sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models) ; modèle source [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) | Le modèle source `pyannote/segmentation-3.0` affiche MIT, mais le dépôt Hugging Face demande d'accepter ses conditions avant l'accès. La version ONNX convertie est distribuée séparément : vérifie les notices/conditions associées à l'artefact sherpa-onnx exact avant toute redistribution. |
| `models/diarization/embedding/embedding.onnx` | Embeddings vocaux 3D-Speaker ERes2Net pour la diarisation | [Artefact ONNX de sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx) ; [projet 3D-Speaker et licence du code](https://github.com/modelscope/3D-Speaker/blob/main/LICENSE) | Le code du projet 3D-Speaker indique Apache-2.0, mais vérifie également les conditions exactes du poids ONNX distribué et conserve la notice fournie par la source. |
| `bin/asr/whisper-cli.exe` | Exécutable de transcription Whisper | [whisper.cpp — releases](https://github.com/ggml-org/whisper.cpp/releases) | Télécharge la version adaptée au système et examine la licence ainsi que les bibliothèques embarquées dans l'archive choisie. |
| `bin/llm/llama-completion.exe` | Exécutable d'inférence GGUF | [llama.cpp — releases](https://github.com/ggml-org/llama.cpp/releases) | Télécharge une release officielle et conserve ses notices. Les termes du modèle GGUF restent indépendants de ceux de llama.cpp. |
| `ffmpeg` (ou `ffmpeg.exe`) | Décodage audio/vidéo facultatif | [Téléchargements FFmpeg](https://ffmpeg.org/download.html) | FFmpeg est proposé sous LGPL ou GPL selon les options de compilation et les composants activés ; la licence exacte dépend de la build téléchargée. Lis sa configuration et ses notices. |

### Notes sur les noms

- `LFM2.5-8B-A1B` est le **nom de la famille/modèle upstream**, pas nécessairement le nom du fichier. Le chemin Glimio est générique (`model.gguf`) ; si tu utilises un GGUF quantifié, note dans tes réglages la source exacte et le niveau de quantification.
- Le fichier Whisper proposé par le centre est `ggml-large-v3-q5_0.bin` (~1,08 Go, licence indiquée MIT par le dépôt de modèles) ; copie-le ou renomme-le en `models/asr/model.bin`, ou règle le chemin dans **Paramètres**.
- `segmentation.onnx` et `embedding.onnx` sont les noms génériques utilisés par Glimio ; renomme les artefacts ONNX téléchargés ou ajuste leurs chemins dans **Paramètres**. L’artefact d’embedding proposé est `3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx` ; copie-le sous le nom local générique `embedding.onnx`. L’archive de segmentation amont inclut `model.onnx`, à copier sous `segmentation.onnx`. Vérifie les notices de licence exactes des poids distribués.
- N'enregistre jamais un fichier de modèle, une URL locale privée ou un jeton d'accès dans Git. Documente plutôt le nom, la version, la source et, si utile, le SHA-256 dans tes notes locales.

## Téléchargement manuel

Les téléchargements ne sont pas automatiques dans Glimio : cela évite de télécharger sans consentement des fichiers volumineux ou soumis à des conditions d'accès. Les chemins ci-dessous sont volontairement génériques ; renomme ou copie les fichiers téléchargés vers ces chemins, ou configure l’emplacement réel dans Paramètres. Crée les dossiers locaux suivants, ignorés par Git :

```text
bin/
├── whisper/whisper-cli.exe
├── llama-cpp/llama-completion.exe
└── media/ffmpeg.exe  # facultatif ; peut aussi être dans PATH
models/
├── asr/model.bin
├── llm/model.gguf
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
