# Pipeline audio local et providers

Glimio sépare les responsabilités du pipeline : l'import, le prétraitement, la séparation de sources, la transcription ASR, la diarisation et le rapprochement global des identités sont des composants indépendants. Les exécutables et poids ne sont pas embarqués dans le dépôt et aucun modèle n'est téléchargé automatiquement par un provider audio.

## Providers intégrés

| Rôle | Provider | Dépendances fortes | Usage |
|---|---|---|---|
| Prétraitement | `no-enhancement` | aucune | Préserve le signal de chaque piste, sans filtre. |
| Prétraitement | `ffmpeg-denoise` | `ffmpeg` | Filtre passe-haut/bas et réduction spectrale modérée ; réglable. Ne sépare pas les interlocuteurs. |
| Prétraitement | `deepfilternet` | `ffmpeg`, binaire `deep-filter` et modèle local | Réduction neuronale du bruit ; dépendance externe facultative. |
| Séparation | `no-separation` | aucune | Chemin par défaut recommandé si chaque piste contient déjà une seule voix ou en l'absence de preuve de chevauchement. |
| Séparation | `speechbrain-sepformer` | `ffmpeg`, `speechbrain-ecapa` et runtime SpeechBrain/PyTorch | Séparation expérimentale en deux sources par fenêtre, avec lien des identités entre fenêtres. |
| Identité vocale | `none-speaker-embedding` | aucune | Désactive le rapprochement global ; conserve des identifiants locaux à la piste/fenêtre. |
| Identité vocale | `speechbrain-ecapa` | PyTorch, Torchaudio, SpeechBrain et modèle ECAPA local | Embeddings de voix servant à rapprocher les mêmes personnes à travers les pistes/fenêtres. |
| ASR | `whisper.cpp` | binaire `whisper-cli` et poids Whisper local | Transcrit les pistes avec timestamps et VAD optionnelle. |
| Diarisation | `sherpa-onnx` | extra Python `diarization` et modèles ONNX locaux | Détecte les tours de parole sans exiger SepFormer ; liaison globale ECAPA optionnelle. |

Chaque `ProviderInfo` expose le champ `requires`. Le catalogue et l'interface indiquent ces dépendances ; le constructeur rejette un assemblage quand une dépendance indispensable du provider de séparation manque. Le pipeline fonctionne sans les extras SpeechBrain si l'on choisit `no-separation` et `none-speaker-embedding`.


## Configuration rapide des providers

Chaque `ProviderInfo` peut déclarer des `setup_links` (documentation, binaire, modèle, package ou licence), un extra Python installable (`python_install_extra`) ou une liste fixe de paquets de repli (`python_install_packages`), ainsi qu'une note de configuration. L'interface Paramètres affiche ces liens dans la carte du provider actif : on peut donc retrouver l'exécutable, les poids et les notices sans chercher dans le dépôt.

Pour les providers Python intégrés (`sherpa-onnx`, SpeechBrain/SepFormer et SpeechBrain/ECAPA), l'interface source propose **Installer / mettre à jour**. Le serveur utilise le Python qui exécute Glimio, lance `pip` en arrière-plan, expose l'état et les dernières sorties du journal, n'accepte jamais de noms de paquets depuis la requête HTTP et n'autorise le lancement de l'installation que depuis une connexion loopback locale. Une seule installation Python est autorisée à la fois. Les extras et paquets proviennent exclusivement des métadonnées des providers intégrés (jamais de la requête HTTP) ; les noms d'extra sont validés, et les poids de modèles restent exclus de cette action.

Une installation peut rendre de nouveaux modules visibles dans le processus courant, mais elle peut aussi modifier des dépendances déjà chargées. Glimio demande donc de **redémarrer l'application après une installation réussie** plutôt que de prétendre garantir le rechargement à chaud. Dans une édition empaquetée/frozen, installer un package dans son interpréteur interne n'est pas pris en charge : les liens restent affichés et l'interface explique cette limite. Pour les outils natifs tels que FFmpeg, whisper.cpp et llama.cpp, la configuration reste manuelle via les liens officiels, car les binaires dépendent de l'OS, de l'architecture et parfois de CUDA/Vulkan/OpenVINO.

Quand vous ajoutez un provider, déclarez ses liens et sa méthode d'installation dans son `ProviderInfo`. N'ajoutez jamais de champs `pip` libres provenant de préférences utilisateur ou d'une API ; la prise en charge de l'installation exige une liste blanche et un examen des licences/conditions des paquets.

## Licence et modèles facultatifs

- Glimio utilise une licence AGPL-3.0-or-later (voir `LICENSE`). Les licences des bibliothèques permissives ne remplacent pas la vérification des poids téléchargés.
- `speechbrain/sepformer-wsj02mix` est publié sous Apache-2.0, mais a été entraîné sur WSJ0-2Mix, un corpus de mélanges propres de deux voix anglaises. Cela ne garantit pas la qualité en français, avec musique/bruit, trois voix ou des microphones de réunion : https://huggingface.co/speechbrain/sepformer-wsj02mix
- `speechbrain/spkrec-ecapa-voxceleb` est publié sous Apache-2.0 : https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
- Le code `speechbrain` est un composant séparé ; installez d'abord une version PyTorch/Torchaudio correspondant à votre plateforme, puis l'extra Glimio `separation` si vous voulez l'utiliser : `python -m pip install -e ".[separation]"`.
- Les dossiers modèles doivent être pré-remplis par l'utilisateur, avec au minimum `hyperparams.yaml` et les poids. Les providers utilisent les chemins locaux et activent le mode hors ligne pour SepFormer ; le serveur de paramètres ne télécharge ni ne lance les binaires à l'ouverture.
- Le modèle VAD Silero de whisper.cpp est un poids séparé à placer sous `models/asr/ggml-silero-v6.2.0.bin` ou à sélectionner dans les paramètres. `vad_mode=auto` l'utilise uniquement s'il existe ; `on` échoue explicitement si le modèle manque, `off` ne passe pas l'argument VAD.

## Multipiste et synchro

L'import FFmpeg/ffprobe conserve chaque flux audio et divise les canaux d'un flux multicanal en fichiers mono quand `split_channels=True`. Chaque fichier WAV a 16 kHz PCM16, est associé à ses métadonnées d'origine, et est transcrit séparément. Le gain du signal est conservé par défaut ; la normalisation de crête est disponible en passant `normalize=True`, mais elle peut amplifier le bruit d'un canal peu actif.

Les pistes extraites de la même vidéo démarrent à zéro et sont alignées sur la même horloge média. Cette hypothèse convient aux fichiers multipistes synchronisés. Pour des fichiers enregistrés séparément avec des débuts/dérives d'horloge différents, il faut aligner la synchro avant de les traiter comme une séance commune.

La diarisation classique traite chaque piste séparément par fenêtres de 15 minutes, avec deux secondes de contexte de chaque côté. Elle ne somme donc pas les pistes microphones : une piste propre n'est pas contaminée par le bruit d'une autre. Sans embeddings globaux, les identifiants ne sont pas fusionnés entre pistes par simple proximité temporelle. Avec ECAPA, le système compare des embeddings, avec un risque résiduel de fusion erronée : vérifiez les labels sur les réunions exigeantes.

## Longues séances, silences et checkpoints

- La transcription sans séparation utilise des blocs de 15 minutes avec chevauchement de 10 secondes. Les segments sont affectés par le milieu de leur intervalle à un seul bloc logique pour limiter les doublons.
- Quand SepFormer est activé, l'orchestrateur découpe en fenêtres courtes (10–60 secondes, 30 secondes par défaut), avec contexte de 2 secondes ; cela préserve l'état de lien des identités mais fait augmenter la durée de calcul.
- La diarisation lit des fenêtres WAV à la demande au lieu de charger toutes les quatre heures en mémoire. L'état par fenêtre (tours, centroïdes, compteurs) est sauvegardé atomiquement sous `transcript/checkpoints/diarization/state.json`.
- Chaque piste de transcription a des checkpoints JSON par bloc. Si un bloc ancien manque, les checkpoints plus tardifs ne sont pas réutilisés, car les identités de locuteurs sont un état séquentiel.
- La VAD de whisper.cpp réduit le temps envoyé à l'ASR lors des longues plages silencieuses quand le modèle VAD existe. Si le modèle n'est pas installé et que le mode est `auto`, aucun VAD n'est activé ; utilisez `on` pour exiger ce modèle. Le VAD peut couper des paroles faibles selon les conditions, donc vérifiez les conversations à voix basse.

## Recommandations qualité

1. Conservez `no-separation` par défaut pour les réunions multipistes où chaque canal correspond déjà à un micro ; le séparateur générique peut dégrader une voix isolée.
2. Activez `ffmpeg-denoise` pour un bruit stationnaire modéré. Essayez `deepfilternet` seulement après comparaison A/B sur un passage réel ; un débruitage fort peut enlever les consonnes et voix faibles.
3. Activez SepFormer uniquement pour évaluer les voix superposées, avec ECAPA installé. Il est expérimental sur le français et les enregistrements bruyants, et il n'est pas un séparateur universel pour N personnes.
4. Pour les pistes avec des voix faibles, utilisez un échantillon A/B (original, débruité, éventuellement séparé) et comparez taux d'erreurs, pas seulement le volume perçu.
5. Pour les sessions longues, gardez assez d'espace disque pour les temporaires/checkpoints et ne déplacez pas les fichiers WAV pendant le traitement.

## Ajouter ou remplacer un provider

1. Implémentez un des protocoles dans `src/seance/providers/contracts.py` (`AudioEnhancementProvider`, `AudioSeparationProvider` ou `SpeakerEmbeddingProvider`).
2. Déclarez un `ProviderInfo` stable (`id`, `task`, options, capacités et `requires`), et enregistrez son factory dans `src/seance/providers/audio_processing.py`.
3. Déclarez chaque dépendance qui change la possibilité d'utiliser le provider ; n'importez pas de gros packages au chargement du catalogue. Les imports de SpeechBrain/PyTorch sont différés jusqu'à l'usage.
4. Ajoutez un test du contrat, un test d'absence de dépendances et un test du traitement/reprise. Ajoutez les attributions/licences du code et des poids dans cette documentation.
5. L'orchestrateur de `src/seance/processing/transcription.py` ne doit appeler que le contrat provider ; il ne doit pas contenir de branche spécifique au moteur supplémentaire sauf orchestration temporelle nécessaire.
