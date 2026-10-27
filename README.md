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
- **Import audio/vidéo multipiste** : chaque flux audio et, par défaut, chaque canal de chaque flux sont conservés comme pistes indépendantes. Le gain source est préservé par défaut pour éviter d’amplifier le bruit de fond.
- **Transcription locale** : moteur whisper.cpp configurable, avec traitement par blocs de 15 minutes et chevauchement pour les longs enregistrements ; langue sélectionnable ou automatique.
- **Providers audio modulaires** : amélioration de la voix, séparation des sources, transcription et embeddings de locuteurs sont des briques distinctes, remplaçables via le catalogue de providers. Les dépendances fortes sont déclarées (`requires`) et vérifiées.
- **Amélioration audio avant ASR** : débruitage spectral FFmpeg par défaut, DeepFilterNet local en option. La VAD Silero de whisper.cpp peut ignorer les silences prolongés lorsque son modèle local est installé. L’original n’est pas altéré.
- **Séparation de sources facultative** : un provider SpeechBrain SepFormer peut essayer de démêler deux voix superposées, avec un provider ECAPA séparé pour rapprocher les identités d’une fenêtre à l’autre. Le modèle public est entraîné sur des mélanges propres de deux voix anglaises et ne doit pas être supposé fiable sur toute réunion française ou bruitée.
- **Longues séances** : transcription en blocs avec chevauchement, checkpoints atomiques par bloc et reprise après interruption ; diarisation fenêtre par fenêtre et rapprochement optionnel des identités vocales.
- **Diarisation facultative** : segmentation et regroupement des tours de parole avec des modèles ONNX configurables. L’amélioration audio supprime du bruit, mais ne sépare pas deux personnes qui parlent simultanément.
- **Résumés et notes** : génération locale par llama.cpp et un modèle GGUF.
- **Bibliothèque** : recherche, filtres, pagination, audio, résumés, transcriptions, options de traitement par séance, renommage et suppression.
- **Recherche multi-séances** : retrouve des passages et prépare une réponse à partir des sources correspondantes.
- **Interface bilingue** : français et anglais, avec préférence persistée dans le navigateur et catalogues hors ligne.
- **Interface cohérente** : les icônes fonctionnelles utilisent `glimio-icon` et `@ng-icons/heroicons` ; les commandes partagées conservent un focus clavier visible et des libellés accessibles.
- **Traitements durables** : file d’attente, état des tâches et points de reprise conservés dans SQLite.

Les transcriptions et résumés issus de modèles peuvent être erronés. Vérifie les noms propres, chiffres, décisions et citations avant réutilisation.

## Prérequis

- Python **3.10+** et `pip`.
- Toolchain cible : Python **3.14.9** et Node.js **26.12.1**. Le projet déclare Python `>=3.10` ; Angular 22 accepte aussi Node.js `^22.22.3` et `^24.15.0` (voir `src/web/frontend/package.json`). Les versions exactes de développement sont épinglées dans `mise.toml` et `.nvmrc`.
- Windows recommandé pour la capture de l’audio système ; les possibilités dépendent du système et des pilotes.
- **FFmpeg et ffprobe** pour l’import fidèle de tous les flux audio, les conversions et le débruitage. C’est le provider média par défaut ; il peut être remplacé par le backend natif `native`, sans FFmpeg, pour les WAV PCM 16 bits à 16 kHz. Les chemins sont configurables dans les paramètres (`Commande FFmpeg`, `Commande ffprobe`) ou avec `--ffmpeg` et `--ffprobe`. Glimio échoue explicitement si ffprobe manque plutôt que d’ignorer silencieusement les pistes secondaires. Les traitements qui n’en ont pas besoin — capture courte, amélioration désactivée (`no-enhancement`), séparation désactivée et découpage natif des WAV — fonctionnent sans FFmpeg.
- **Facultatif — DeepFilterNet** : exécutable `deep-filter` et archive modèle DeepFilterNet téléchargés séparément pour une amélioration neuronale de la voix.
- **Facultatif — SpeechBrain** : PyTorch/Torchaudio pour SepFormer et ECAPA. Depuis les sources, installe l’extra `separation` ; dans les éditions précompilées, les dépendances sont installées à la demande dans un runtime Python isolé. Le modèle local de chaque provider reste à télécharger.
- **Whisper** : whisper.cpp et son modèle Whisper pour la transcription.
- **Résumés et recherche** : llama.cpp et un modèle GGUF.
- **Diarisation** : le provider Python `sherpa-onnx` et les deux modèles ONNX attendus. Depuis les sources, installe l’extra `diarization` ; dans les éditions précompilées, utilise `glimio providers install sherpa-onnx`. L’installation de la dépendance ne télécharge pas les poids des modèles.

Les poids IA et exécutables natifs sont volontairement exclus du dépôt Git. Les noms de fichiers, chemins, liens des éditeurs et restrictions connues sont documentés dans [`docs/MODELS.md`](docs/MODELS.md). Le fonctionnement des providers audio et leurs limites sont décrits dans [`docs/AUDIO_PIPELINE.md`](docs/AUDIO_PIPELINE.md). Consulte [`docs/PROVIDERS.md`](docs/PROVIDERS.md) pour les commandes et options du CLI. Dans les éditions précompilées, les dépendances Python des providers compatibles peuvent être installées à la demande depuis Paramètres ou le CLI : elles sont placées dans un runtime Python isolé sous les données utilisateur, sans modifier le binaire Glimio. Les modèles et exécutables natifs restent des téléchargements séparés.

## Installation

### Télécharger une édition précompilée

Dans la page **Releases** du dépôt GitHub, choisis l’une des deux éditions : **CLI** pour travailler depuis la ligne de commande, ou **Web** pour l’interface dans le navigateur (qui inclut aussi le CLI).

- **Windows x64** : installateur `Setup.exe` ou archive `portable.zip` pour chaque édition.
- **Linux x86_64** : archive `.tar.gz` pour chaque édition ; build basé sur Ubuntu 22.04 (glibc 2.35 ou plus récent). Extrait-la puis lance les exécutables indiqués dans `LISEZ-MOI.txt`.

Les dépendances Python optionnelles ne sont pas incluses dans le téléchargement de base. Installe-les à la demande avec `glimio providers install ID`. La première installation télécharge un runtime CPython autonome, vérifié par SHA-256, puis les paquets nécessaires au provider. Les téléchargements peuvent être importants pour SpeechBrain/PyTorch.

Les exécutables Whisper/llama.cpp, FFmpeg et les poids des modèles ne sont pas inclus. Configure leurs emplacements dans **Paramètres** après l’installation ; les modèles et leurs conditions restent documentés dans [`docs/MODELS.md`](docs/MODELS.md). Les données de l’application et le runtime des providers optionnels sont conservés hors du dossier d’installation :

- Windows : `%LOCALAPPDATA%\Glimio\Data`
- Linux : `$XDG_DATA_HOME/Glimio/Data` si `XDG_DATA_HOME` est défini, sinon `~/.local/share/Glimio/Data`

### Installer depuis les sources

Depuis la racine du dépôt complet, avec Python 3.10 ou plus récent, choisis les extras nécessaires :

```bash
# CLI autonome, sans dépendances Web
python -m pip install -e ".[cli]"

# Web + CLI
python -m pip install -e ".[web]"

# Web + diarisation depuis les sources
python -m pip install -e ".[web,diarization]"

# CLI + diarisation depuis les sources
python -m pip install -e ".[cli,diarization]"
```

La diarisation reste un extra **optionnel depuis les sources**. Dans les paquets précompilés, `sherpa-onnx` s’installe à la demande avec `glimio providers install sherpa-onnx`, et les deux fichiers modèle ONNX doivent toujours être téléchargés séparément. Pour SpeechBrain, utilise `glimio providers install speechbrain-ecapa` ou `glimio providers install speechbrain-sepformer`.

Télécharge manuellement les outils et modèles à partir des sources indiquées dans [`docs/MODELS.md`](docs/MODELS.md). Place-les aux chemins par défaut ou configure-les dans **Paramètres**.

Démarre l’application :

```bash
python -m web
```

L’interface locale est normalement ouverte à `http://127.0.0.1:8765`. Le serveur écoute sur la boucle locale par défaut. Ne l’expose pas sur un réseau non fiable : Glimio n’implémente actuellement pas d’authentification.

Le CLI peut enregistrer avec `glimio record` (Ctrl+C pour arrêter), importer un fichier avec `glimio import`, traiter un dossier avec `glimio process`, gérer la bibliothèque (`glimio sessions`), lire ou modifier les documents (`glimio artifacts`), consulter les jobs (`glimio jobs`) et effectuer la recherche intelligente (`glimio search`). Il peut aussi gérer les providers et les préférences sans lancer Web. Consulte [`docs/CLI.md`](docs/CLI.md) pour les commandes et exemples complets, ou utilise `glimio --help` pour afficher l’aide.

Pour un débruitage conservateur, passe `--speech-enhancement ffmpeg`. Pour DeepFilterNet configuré localement, utilise `--speech-enhancement deepfilter --deep-filter-executable chemin/vers/deep-filter --deep-filter-model models/speech-enhancement/model.tar.gz`. La détection de silence utilise `--vad-mode auto|on|off` et le modèle Silero indiqué dans la section [Modèles et exécutables](#modèles-et-exécutables). Les options de séparation et d’identité vocale se configurent avec `--source-separation-provider`, `--speaker-embedding-provider` et les options propres à chaque provider ; SepFormer requiert explicitement ECAPA et les deux modèles locaux.

## Modèles et exécutables

| Élément | Chemin attendu par défaut |
|---|---|
| Whisper CLI | `bin/asr/whisper-cli` (Linux) / `bin/asr/whisper-cli.exe` (Windows) |
| Modèle Whisper large-v3 | `models/asr/model.bin` |
| Modèle VAD Silero (optionnel) | `models/asr/ggml-silero-v6.2.0.bin` |
| Binaire DeepFilterNet (optionnel) | `bin/speech/deep-filter` (Linux) / `bin/speech/deep-filter.exe` (Windows) |
| Modèle DeepFilterNet (optionnel) | `models/speech-enhancement/model.tar.gz` |
| llama.cpp | `bin/llm/llama-completion` (Linux) / `bin/llm/llama-completion.exe` (Windows) |
| Modèle LFM2.5 GGUF | `models/llm/model.gguf` |
| Modèle de segmentation | `models/diarization/segmentation/segmentation.onnx` |
| Modèle d’embedding Titanet | `models/diarization/embedding/embedding.onnx` |

Ces noms et chemins sont des valeurs par défaut configurables ; ils ne signifient pas que Glimio redistribue ces ressources. Consulte [`docs/MODELS.md`](docs/MODELS.md) pour les sources et les restrictions connues, en particulier concernant la licence LFM Open et les modèles de diarisation.

## Utilisation

1. Dans **Enregistrement**, choisis les sources audio et le workflow : enregistrer seul, transcrire, ou transcrire et résumer.
2. Sous **Options communes**, choisis la langue de transcription, le format de résumé par défaut et, si nécessaire, active la diarisation et indique le nombre d’interlocuteurs. Ces options s’appliquent aux nouveaux enregistrements et aux imports.
3. Lance l’enregistrement ou importe un fichier.
4. Dans **Bibliothèque**, chaque séance possède ses propres options de traitement. Enregistre les options de langue, de format et de diarisation avant de relancer une transcription ou un résumé ; elles sont sauvegardées dans les métadonnées de la séance et réutilisées lors des traitements suivants. Les anciennes séances sans options enregistrées reprennent les valeurs communes comme point de départ.
5. Suis l’avancement dans **Activité** et consulte les artefacts dans **Bibliothèque**. Utilise **Recherche intelligente** pour interroger plusieurs séances.

Le réglage de langue indique la langue parlée que Whisper doit reconnaître ; il ne traduit pas automatiquement une transcription vers une langue cible arbitraire.

## Données et confidentialité

Les séances, l’audio et les artefacts sont stockés localement. La base d’état et de préférences est normalement `.glimio/glimio.sqlite3`, et les dossiers de séances sont généralement conservés dans `seances/`. La racine peut être ajustée via `GLIMIO_PROJECT_ROOT`, `GLIMIO_DIRECTORY` et `GLIMIO_DATA_DIR`.

La capture et l’analyse audio peuvent traiter des informations personnelles. Obtiens le consentement requis et respecte les règles applicables avant d’enregistrer. Fais des sauvegardes avant de supprimer des séances : les suppressions sont irréversibles dans l’application.

## Développement et tests

Installe les extras Web et diarisation comme indiqué dans la section [Installation](#installation), puis lance la suite Python depuis la racine :

```powershell
.\.venv\Scripts\python.exe -m pytest -q src/tests
```

Contrôle le contraste des principaux jetons de thème avec :

```powershell
.\.venv\Scripts\python.exe scripts/check_theme_contrast.py
```

### Interface web — Angular 22 et Tailwind CSS 4

Les composants sont séparés en fichiers `*.ts`, `*.html` et `*.scss`. Les styles partagés se trouvent dans `src/web/frontend/src/styles/components.scss`. Tailwind CSS 4 est chargé depuis `src/web/frontend/src/styles/tailwind.css` ; dans les composants, `@reference` rend ses utilitaires disponibles à `@apply`. Les icônes Heroicons passent par le composant partagé `glimio-icon`, et le logo Angular est servi depuis `src/web/frontend/public/brand/`.

L’interface servie à `/` est l’application Angular 22 ; FastAPI fournit l’API `/api/*` et sert le build Angular depuis `dist/glimio-web-ui`. Lorsqu’on démarre le serveur via le point d’entrée du projet, le build de l’interface est vérifié et reconstruit si nécessaire. Un simple import de `web.app` n’installe toutefois pas les dépendances et ne lance pas npm : les tests API peuvent s’exécuter indépendamment du build frontend.

Utilise la version cible Node.js `26.12.1` indiquée dans `src/web/frontend/.nvmrc`. Angular 22 accepte également les versions indiquées dans `src/web/frontend/package.json` ; les versions hors de ces plages peuvent produire des avertissements `EBADENGINE` et ne constituent pas un environnement pris en charge. Depuis `src/web/frontend`, installe les dépendances verrouillées et exécute les contrôles dans cet ordre :

```powershell
npm ci
npm run typecheck
npm test
npm run build
```

Les sources sous `src/web/static/` sont des fichiers historiques et ne constituent pas le point d’entrée de l’application Angular. La suite automatisée ne remplace pas les essais manuels sur le matériel audio, les navigateurs et les lecteurs d’écran. La conformité WCAG AAA n’est pas certifiée. Le rapport [`ACCESSIBILITY_AUDIT.md`](ACCESSIBILITY_AUDIT.md) détaille les vérifications et les limites ; Glimio ne revendique pas une conformité WCAG globale certifiée.

## Git et contribution

Le `.gitignore` exclut l’état local, les séances, les poids de modèles, les exécutables et les binaires compilés. Avant le premier push, vérifie `git status --ignored` et assure-toi qu’aucun poids IA, exécutable, fichier audio de test privé, base SQLite ou secret n’est inclus. Si de tels fichiers ont déjà été indexés par Git, `.gitignore` ne les retire pas de l’index : suis les étapes de [`docs/GIT_PREPARATION.md`](docs/GIT_PREPARATION.md).

Les contributions doivent inclure des tests et documenter les nouveaux modèles ou dépendances. Consulte [`CONTRIBUTING.md`](CONTRIBUTING.md) et [`SECURITY.md`](SECURITY.md). Les assistants de code suivent les conventions du dépôt décrites dans [`AGENTS.md`](AGENTS.md). Pour créer les paquets et publier une version, suis [`docs/RELEASING.md`](docs/RELEASING.md) ; les changements notables sont consignés dans [`CHANGELOG.md`](CHANGELOG.md).

Les frontières entre cœur Python, API Web et frontend, ainsi que le contrat des providers, sont décrits dans [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Licence

Le code propre à Glimio est publié sous **GNU AGPL v3 ou toute version ultérieure**. Cette licence préserve le copyleft, y compris pour les modifications proposées comme service réseau. Elle n’interdit pas la vente commerciale et n’impose pas une contribution au projet amont : aucune licence reconnue comme open source ne peut interdire l’usage commercial. La marque Glimio et ses éléments visuels ne sont pas accordés comme marques par la licence du code. Cette licence ne remplace pas les conditions distinctes des modèles IA, exécutables ou autres composants tiers. Consulte [`docs/MODELS.md`](docs/MODELS.md) avant de télécharger ou redistribuer leurs poids.
