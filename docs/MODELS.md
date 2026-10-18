# Modèles et exécutables locaux

Glimio ne versionne pas les poids IA ou les exécutables natifs. Télécharge-les toi-même depuis les projets sources, place-les aux chemins ci-dessous, puis vérifie les licences affichées par l'éditeur au moment du téléchargement.

> **Important :** la licence AGPL à la racine couvre le code et la documentation propres à Glimio, pas automatiquement les modèles, les exécutables tiers, leurs poids convertis/quantifiés ni les bibliothèques natives. Conserve les notices et licences originales. Ne redistribue pas de poids si tu n'as pas vérifié les conditions du fichier exact téléchargé.

## Chemins attendus et sources

| Fichier local attendu | Usage | Source officielle / primaire | Conditions à vérifier |
|---|---|---|---|
| `models/llm/model.gguf` | Résumés et recherche, modèle de la famille LFM2.5 | [LiquidAI/LFM2.5-8B-A1B sur Hugging Face](https://huggingface.co/LiquidAI/LFM2.5-8B-A1B) ; [quantifications compatibles llama.cpp](https://huggingface.co/models?search=LFM2.5-8B-A1B-GGUF) | Le modèle upstream indique **LFM Open License v1.0**. Elle comprend une limite conditionnelle à l'usage commercial (« Threshold ») ; ne considère pas cette licence comme MIT. Vérifie aussi les conditions du dépôt qui fournit la quantification GGUF utilisée. |
| `models/asr/model.bin` | Reconnaissance vocale Whisper large-v3 | [Dépôt whisper.cpp et modèles convertis](https://huggingface.co/ggerganov/whisper.cpp/tree/main) ; [code et licence Whisper](https://github.com/openai/whisper/blob/main/LICENSE) | Le code/modèle Whisper source est publié sous MIT, mais garde la licence et la provenance de l'artefact `ggml` exact. La conversion/le quantization peut provenir d'un tiers. |
| `models/diarization/segmentation.onnx` | Segmentation des voix avant regroupement des locuteurs | [Modèles de segmentation de sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models) ; modèle source [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) | Le modèle source `pyannote/segmentation-3.0` affiche MIT, mais le dépôt Hugging Face demande d'accepter ses conditions avant l'accès. La version ONNX convertie est distribuée séparément : vérifie les notices/conditions associées à l'artefact sherpa-onnx exact avant toute redistribution. |
| `models/diarization/embedding.onnx` | Embeddings vocaux Titanet pour la diarisation | [Artefacts ONNX de sherpa-onnx — speaker-recognition-models](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models) ; [modèle Titanet Small d'origine côté NVIDIA NeMo](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/nemo/models/titanet_small) | Le dépôt sherpa-onnx est une source de téléchargement/conversion, pas une preuve que les poids d'origine sont soumis à la licence du code sherpa-onnx. Vérifie les termes du modèle NVIDIA et les éventuels termes de l'artefact ONNX. |
| `bin/asr/whisper-cli.exe` | Exécutable de transcription Whisper | [whisper.cpp — releases](https://github.com/ggml-org/whisper.cpp/releases) | Télécharge la version adaptée au système et examine la licence ainsi que les bibliothèques embarquées dans l'archive choisie. |
| `bin/llm/llama-completion.exe` | Exécutable d'inférence GGUF | [llama.cpp — releases](https://github.com/ggml-org/llama.cpp/releases) | Télécharge une release officielle et conserve ses notices. Les termes du modèle GGUF restent indépendants de ceux de llama.cpp. |
| `ffmpeg` (ou `ffmpeg.exe`) | Décodage audio/vidéo facultatif | [Téléchargements FFmpeg](https://ffmpeg.org/download.html) | FFmpeg est proposé sous LGPL ou GPL selon les options de compilation et les composants activés ; la licence exacte dépend de la build téléchargée. Lis sa configuration et ses notices. |

### Notes sur les noms

- `LFM2.5-8B-A1B` est le **nom de la famille/modèle upstream**, pas nécessairement le nom du fichier. Le chemin Glimio est générique (`model.gguf`) ; si tu utilises un GGUF quantifié, note dans tes réglages la source exacte et le niveau de quantification.
- Le fichier Whisper téléchargé peut porter un nom upstream comme `ggml-large-v3.bin` ; copie-le ou renomme-le en `models/asr/model.bin`, ou règle le chemin dans **Paramètres**.
- `segmentation.onnx` et `embedding.onnx` sont les noms génériques utilisés par Glimio ; renomme les artefacts ONNX téléchargés ou ajuste leurs chemins dans **Paramètres**. L’artefact d’embedding provenant de sherpa-onnx peut porter un nom tel que `nemo_en_titanet_small.onnx` ; l’archive de segmentation amont peut inclure un `model.onnx` à copier sous le nom local générique.
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
