# Glimio

**Enregistrer, transcrire, résumer et retrouver ses conversations — localement.**

Glimio est une application de bureau locale avec une interface web qui aide à enregistrer ou importer de l’audio, transcrire la parole, identifier les changements de locuteur, générer des notes structurées et rechercher dans plusieurs séances. Le projet est encore en développement (`0.x`) et ne doit pas être considéré comme une version stable.

- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Modèles et exécutables](#modèles-et-exécutables)
- [Utilisation](#utilisation)
- [Données et confidentialité](#données-et-confidentialité)
- [Développement et tests](#développement-et-tests)
- [Git et contribution](#git-et-contribution)
- [Licence](#licence)

## Fonctionnalités

- **Capture audio** : microphone et audio système Windows, avec normalisation optionnelle.
- **Import audio/vidéo multipiste** : chaque flux audio et, par défaut, chaque canal de chaque flux sont conservés comme pistes indépendantes ; le gain source est préservé par défaut pour éviter d’amplifier le bruit de fond.
- **Transcription locale** : moteur whisper.cpp configurable, avec traitement par blocs de 15 minutes et chevauchement pour les longs enregistrements, langue sélectionnable ou automatique.
- **Providers audio modulaires** : amélioration de la voix, séparation des sources, transcription et embeddings de locuteurs sont des briques distinctes, remplaçables via le catalogue de providers. Les dépendances fortes sont déclarées (`requires`) et vérifiées.
- **Amélioration audio avant ASR** : débruitage spectral FFmpeg par défaut, DeepFilterNet local en option ; la VAD Silero de whisper.cpp peut ignorer les silences prolongés lorsque son modèle local est installé. L’original n’est pas altéré.
- **Séparation de sources facultative** : un provider SpeechBrain SepFormer peut essayer de démêler deux voix superposées, avec un provider ECAPA séparé pour rapprocher les identités d’une fenêtre à l’autre. Le modèle public est entraîné sur des mélanges propres de deux voix anglaises et ne doit pas être supposé fiable sur toute réunion française ou bruitée.
- **Longues séances** : transcription en blocs avec chevauchement, checkpoints atomiques par bloc et reprise après interruption ; diarisation fenêtre par fenêtre et rapprochement d’identités vocales optionnel.
- **Diarisation facultative** : segmentation et regroupement des tours de parole avec des modèles ONNX configurables. L’amélioration audio supprime du bruit, mais ne sépare pas deux personnes qui parlent simultanément.
- **Résumés et notes** : génération locale par llama.cpp et un modèle GGUF.
- **Bibliothèque** : recherche, filtres, pagination, audio, résumés, transcriptions, options de traitement par séance, renommage et suppression.
- **Interface cohérente** : les icônes fonctionnelles utilisent `glimio-icon` et `@ng-icons/heroicons` ; les commandes partagées conservent un focus clavier visible et des libellés accessibles.
- **Recherche multi-séances** : retrouve des passages et prépare une réponse à partir des sources correspondantes.
- **Interface bilingue** : français et anglais, avec préférence persistée dans le navigateur et catalogues hors ligne.
- **Traitements durables** : file d’attente, état des tâches et points de reprise conservés en SQLite.

Les transcriptions et résumés issus de modèles peuvent être erronés. Vérifie les noms propres, chiffres, décisions et citations avant réutilisation.

## Prérequis

- Python **3.10+** et `pip`.
- Node.js **22.22.3+** (branche 22) ou une version compatible plus récente pour compiler l’interface Angular ; la version cible est définie dans `src/web/frontend/.nvmrc`.
- Windows recommandé pour la capture de l’audio système ; les possibilités dépendent du système et des pilotes.
- FFmpeg et ffprobe sur le `PATH` (ou côte à côte) pour l’import fidèle de tous les flux audio, les conversions et le débruitage. Glimio échoue explicitement si ffprobe manque plutôt que de silencieusement ignorer les pistes secondaires.
- Facultatif : exécutable `deep-filter` et archive modèle DeepFilterNet téléchargés séparément pour une amélioration neuronale de la voix.
- Facultatif : l’extra `separation` (SpeechBrain, PyTorch/Torchaudio) pour SepFormer et ECAPA ; installe d’abord le build PyTorch adapté à la plateforme, puis le modèle local de chaque provider.
- whisper.cpp et son modèle Whisper pour la transcription.
- llama.cpp et un modèle GGUF pour les résumés/recherches.
- Pour la diarisation, l’extra Python `diarization` (`sherpa-onnx`) et les deux modèles ONNX attendus. Le module d’intégration est fourni dans `src/seance/processing/diarization.py` ; la dépendance seule ne télécharge pas les poids des modèles.

Les poids IA et exécutables natifs sont volontairement exclus du dépôt Git. Les noms de fichiers, chemins et liens éditeurs sont documentés dans [`docs/MODELS.md`](docs/MODELS.md). Le fonctionnement des providers audio et leurs limites sont décrits dans [`docs/AUDIO_PIPELINE.md`](docs/AUDIO_PIPELINE.md). Les paramètres affichent aussi les liens de téléchargement fournis par chaque provider ; les extras Python compatibles peuvent être installés en un clic dans une exécution depuis les sources. Redémarre Glimio après une installation de dépendances. Les éditions empaquetées affichent les liens mais ne modifient pas leur runtime Python interne.

## Installation

### Télécharger une édition Windows

Dans la page **Releases** du dépôt GitHub, télécharge l’installateur `Setup.exe` pour une installation classique, ou l’archive `portable.zip` si tu préfères extraire et lancer l’application sans installateur. Les deux formats existent pour chacune des éditions : **CLI**, **Web** et **Web avec diarisation**. L’édition Web inclut aussi le CLI et son interface Angular précompilée ; Node.js n’est pas nécessaire pour l’utiliser.

Les exécutables Whisper/llama.cpp, FFmpeg et les poids de modèles ne sont pas inclus. Configure leurs emplacements dans **Paramètres** après l’installation ; les modèles et leurs conditions restent documentés dans [`docs/MODELS.md`](docs/MODELS.md). Les données de l’application empaquetée sont conservées dans `%LOCALAPPDATA%\Glimio\Data` et séparées du dossier d’installation.

### Installer depuis les sources

Depuis la racine du dépôt complet, avec Python 3.10 ou plus récent :

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[web,diarization]"
```

Sans diarisation :

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[web]"
```

Télécharge manuellement les outils et modèles depuis les sources de [`docs/MODELS.md`](docs/MODELS.md). Place-les aux chemins par défaut ou configure-les dans **Paramètres**.

Démarre l’application :

```powershell
.\.venv\Scripts\python.exe -m web
```

L’interface locale est normalement ouverte à `http://127.0.0.1:8765`. Le serveur écoute sur la boucle locale par défaut. Ne l’expose pas sur un réseau non fiable : Glimio n’implémente actuellement pas d’authentification.

Le CLI peut enregistrer avec `glimio record` (Ctrl+C pour arrêter) et accepte aussi un fichier audio/vidéo ou un dossier de séance : `glimio process chemin\vers\fichier.wav`, `glimio transcribe chemin\vers\seance` ou `glimio summarize chemin\vers\seance`. Utilise `glimio --help` pour les options et chemins de modèles. Pour un débruitage conservateur, passe `--speech-enhancement ffmpeg`; pour DeepFilterNet configuré localement, `--speech-enhancement deepfilter --deep-filter-executable chemin/vers/deep-filter --deep-filter-model models/speech-enhancement/model.tar.gz`. La détection de silence utilise `--vad-mode auto|on|off` et le modèle Silero indiqué ci-dessus. Les options de séparation et d’identité vocale se configurent avec `--source-separation-provider`, `--speaker-embedding-provider` et les options du provider correspondantes ; SepFormer requiert explicitement ECAPA et les deux modèles locaux.

## Modèles et exécutables

| Élément | Chemin attendu par défaut |
|---|---|
| Whisper CLI | `bin/asr/whisper-cli.exe` |
| Modèle Whisper large-v3 | `models/asr/model.bin` |
| Modèle VAD Silero (optionnel) | `models/asr/ggml-silero-v6.2.0.bin` |
| Binaire DeepFilterNet (optionnel) | `bin/speech/deep-filter.exe` (adapter sur Linux/macOS) |
| Modèle DeepFilterNet (optionnel) | `models/speech-enhancement/model.tar.gz` |
| llama.cpp | `bin/llm/llama-completion.exe` |
| Modèle LFM2.5 GGUF | `models/llm/model.gguf` |
| Modèle de segmentation | `models/diarization/segmentation/segmentation.onnx` |
| Modèle d’embedding Titanet | `models/diarization/embedding/embedding.onnx` |

Ces noms et chemins sont des valeurs par défaut configurables ; ils ne signifient pas que Glimio redistribue ces ressources. Voir les sources et les restrictions connues dans [`docs/MODELS.md`](docs/MODELS.md), en particulier pour la licence LFM Open et les modèles de diarisation.

## Utilisation

1. Dans **Enregistrement**, choisis les sources audio et le workflow (enregistrer seul, transcrire, ou transcrire et résumer).
2. Sous **Options communes**, choisis la langue de transcription, le format de résumé par défaut et, si nécessaire, active la diarisation et indique le nombre d’interlocuteurs. Ces options s’appliquent aux nouveaux enregistrements et aux imports.
3. Lance l’enregistrement ou importe un fichier.
4. Dans **Bibliothèque**, chaque séance possède ses propres options de traitement. Enregistre les options de langue, de format et de diarisation avant de relancer une transcription ou un résumé ; elles sont sauvegardées dans les métadonnées de la séance et réutilisées aux prochains traitements. Les anciennes séances sans options enregistrées reprennent les valeurs communes comme point de départ.
5. Suis l’avancement dans **Activité** et consulte les artefacts dans **Bibliothèque**. Utilise **Recherche intelligente** pour interroger plusieurs séances.

Le réglage de langue indique la langue parlée que Whisper doit reconnaître ; il ne traduit pas automatiquement une transcription vers une langue cible arbitraire.

## Données et confidentialité

Les séances, l’audio et les artefacts sont stockés localement. La base d’état et de préférences est normalement `.glimio/glimio.sqlite3`, et les dossiers de séances sont généralement conservés dans `seances/`. La racine peut être ajustée via `GLIMIO_PROJECT_ROOT`, `GLIMIO_DIRECTORY` et `GLIMIO_DATA_DIR`.

La capture et l’analyse audio peuvent traiter des informations personnelles. Obtiens le consentement requis et respecte les règles applicables avant d’enregistrer. Fais des sauvegardes avant de supprimer des séances ; les suppressions sont irréversibles dans l’application.


## Développement et tests

Installer les extras web et diarisation comme indiqué ci-dessus, puis lancer la suite depuis la racine :

```powershell
.\.venv\Scripts\python.exe -m pytest -q src/tests
```

Contrôle de contraste des principaux jetons de thème :

```powershell
.\.venv\Scripts\python.exe scripts/check_theme_contrast.py
```

### Interface web — Angular 22, Tailwind CSS 4

Les composants sont séparés en fichiers `*.ts`, `*.html` et `*.scss`. Les styles partagés sont dans `src/web/frontend/src/styles/components.scss`. Tailwind CSS 4 est chargé depuis `src/web/frontend/src/styles/tailwind.css` ; dans les composants, `@reference` rend ses utilitaires disponibles à `@apply`. Les icônes Heroicons passent par le composant partagé `glimio-icon` et le logo Angular est servi depuis `src/web/frontend/public/brand/`.

L’interface servie à `/` est l’application Angular 22 ; FastAPI fournit l’API `/api/*` et sert le build Angular depuis `dist/glimio-web-ui`. Lorsqu’on démarre le serveur via le point d’entrée du projet, le build de l’interface est vérifié et reconstruit si nécessaire. Un simple import de `web.app` n’installe toutefois pas les dépendances et ne lance pas npm : les tests API peuvent s’exécuter indépendamment du build frontend.

Utilise Node.js `22.22.3+` dans la branche 22 (ou une version compatible de la branche 24/26 ; la version cible 22.22.3 est dans `.nvmrc`). Les versions plus anciennes peuvent produire des avertissements `EBADENGINE` et ne constituent pas un environnement pris en charge. Depuis `src/web/frontend`, installe les dépendances verrouillées et exécute les contrôles dans cet ordre :

```powershell
npm ci
npm run typecheck
npm test
npm run build
```

La suite Python se lance séparément à la racine avec `python -m pytest -q src/tests`. Les sources sous `src/web/static/` sont des fichiers historiques et ne constituent pas le point d’entrée de l’application Angular. La suite automatisée ne remplace pas les essais manuels sur le matériel audio, les navigateurs et les lecteurs d’écran. La conformité WCAG AAA n’est pas certifiée. Le rapport [`ACCESSIBILITY_AUDIT.md`](ACCESSIBILITY_AUDIT.md) détaille les vérifications et les limites ; Glimio ne revendique pas une conformité WCAG globale certifiée.

## Git et contribution

Le `.gitignore` exclut l’état local, les séances, les poids de modèles, les exécutables et les binaires compilés. Avant le premier push, vérifie `git status --ignored` et assure-toi qu’aucun poids IA, exécutable, fichier audio de test privé, base SQLite ou secret n’est inclus. Si de tels fichiers ont déjà été indexés par Git, `.gitignore` ne les retire pas de l’index : suis les étapes de [`docs/GIT_PREPARATION.md`](docs/GIT_PREPARATION.md).

Les contributions doivent inclure des tests et documenter les nouveaux modèles/dépendances. Voir [`CONTRIBUTING.md`](CONTRIBUTING.md) et [`SECURITY.md`](SECURITY.md). Les assistants de code suivent les conventions du dépôt décrites dans [`AGENTS.md`](AGENTS.md). Pour créer les paquets et publier une version, suivre [`docs/RELEASING.md`](docs/RELEASING.md) ; les changements notables sont consignés dans [`CHANGELOG.md`](CHANGELOG.md).

Les frontières entre cœur Python, API Web et frontend ainsi que le contrat des providers sont décrits dans [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Licence

Le code propre à Glimio est publié sous **GNU AGPL v3 ou toute version ultérieure**. Cette licence préserve le copyleft, y compris pour les modifications proposées comme service réseau. Elle n’interdit pas la vente commerciale et n’impose pas une contribution au projet amont : aucune licence reconnue comme open source ne peut interdire l’usage commercial. La marque Glimio et ses éléments visuels ne sont pas accordés comme marques par la licence du code. Cette licence ne remplace pas les conditions distinctes des modèles IA, exécutables ou autres composants tiers. Consulte [`docs/MODELS.md`](docs/MODELS.md) avant de télécharger ou redistribuer leurs poids.
