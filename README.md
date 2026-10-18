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
- **Import audio/vidéo** : les formats décodables par FFmpeg peuvent être importés.
- **Transcription locale** : moteur whisper.cpp configuré localement, avec langue de transcription sélectionnable, suivi de la langue FR/EN de l’interface ou détection de la langue parlée.
- **Diarisation facultative** : segmentation et regroupement de voix avec des modèles ONNX configurables.
- **Résumés et notes** : génération locale par llama.cpp et un modèle GGUF.
- **Bibliothèque** : recherche, filtres, pagination, audio, résumés, transcriptions, options de traitement par séance, renommage et suppression.
- **Interface cohérente** : les icônes fonctionnelles utilisent le sprite local Heroicons v2 Outline (`@ng-icons/heroicons (icônes arborescentes intégrées au bundle Angular)`) ; le menu mobile possède une grande cible tactile et se ferme avec Échap ou après navigation.
- **Recherche multi-séances** : retrouve des passages et prépare une réponse à partir des sources correspondantes.
- **Interface bilingue** : français et anglais, avec préférence persistée dans le navigateur et catalogues hors ligne.
- **Traitements durables** : file d’attente, état des tâches et points de reprise conservés en SQLite.

Les transcriptions et résumés issus de modèles peuvent être erronés. Vérifie les noms propres, chiffres, décisions et citations avant réutilisation.

## Prérequis

- Python **3.10+** et `pip`.
- Windows recommandé pour la capture de l’audio système ; les possibilités dépendent du système et des pilotes.
- FFmpeg sur le `PATH` pour les imports nécessitant une conversion.
- whisper.cpp et son modèle Whisper pour la transcription.
- llama.cpp et un modèle GGUF pour les résumés/recherches.
- Pour la diarisation, l’extra Python `diarization` (`sherpa-onnx`) et les deux modèles ONNX attendus. Le module d’intégration est fourni dans `src/seance/diarization.py` ; la dépendance seule ne télécharge pas les poids des modèles.

Les poids IA et exécutables natifs sont volontairement exclus du dépôt Git. Les noms de fichiers, chemins et liens éditeurs sont documentés dans [`docs/MODELS.md`](docs/MODELS.md).

## Installation

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

## Modèles et exécutables

| Élément | Chemin attendu par défaut |
|---|---|
| Whisper CLI | `bin/asr/whisper-cli.exe` |
| Modèle Whisper large-v3 | `models/asr/model.bin` |
| llama.cpp | `bin/llm/llama-completion.exe` |
| Modèle LFM2.5 GGUF | `models/llm/model.gguf` |
| Modèle de segmentation | `models/diarization/segmentation.onnx` |
| Modèle d’embedding Titanet | `models/diarization/embedding.onnx` |

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


### Structure des composants Angular

Les composants Angular sont séparés en trois fichiers : `*.component.ts` ou `*.page.ts` pour la logique, le fichier `.html` associé pour le template et le fichier `.scss` associé pour les styles propres au composant. Les styles partagés de l’interface restent dans les feuilles globales tant que leur migration composant par composant n’a pas été vérifiée visuellement. Les composants doivent utiliser le composant partagé `glimio-icon` pour les icônes Heroicons ; le logo de marque est l’asset vectoriel `src/web/frontend/public/brand/glimio.svg`.

## Développement et tests

Installer les extras web et diarisation comme indiqué ci-dessus, puis lancer la suite depuis la racine :

```powershell
.\.venv\Scripts\python.exe -m pytest -q src/tests
```

Contrôle de contraste des principaux jetons de thème :

```powershell
.\.venv\Scripts\python.exe scripts/check_theme_contrast.py
```

Vérification JavaScript (Node.js requis) :

```powershell
```

### Interface web — migration Angular 22 en cours

L’interface actuellement servie à `/` reste la version stable en JavaScript pendant que l’application Angular 22 est portée et vérifiée. Le backend demeure en FastAPI/Python. Voir [`docs/ANGULAR_22_MIGRATION.md`](docs/ANGULAR_22_MIGRATION.md) pour l’architecture cible, les contraintes de versions et les critères de bascule.

Angular 22 requiert Node.js `22.22.3+` dans la branche 22 (ou une version compatible de la branche 24/26). Depuis `src/web/frontend` :

```powershell
npm install
npm run typecheck
npm test
npm run build
```

Le build Angular est disponible en aperçu à `/angular/` après redémarrage du serveur FastAPI. Il ne remplace pas encore l’interface stable : la bascule n’aura lieu qu’après validation de la parité fonctionnelle et des tests de non-régression. Pour régénérer le CSS de la version stable pendant cette transition, utilise `npm run build:legacy-css`.

Garde le CSS livré (`src/web/frontend/src/styles/`) synchronisé avec ses sources Tailwind. Pour les nouvelles chaînes UI de la version stable, modifie les catalogues `src/web/frontend/src/i18n (à réintroduire côté Angular)` et ajoute un test. La suite automatisée ne remplace pas des essais manuels sur le matériel audio, les navigateurs et les lecteurs d’écran. La conformité WCAG AAA n’est pas certifiée. Le rapport [`ACCESSIBILITY_AUDIT.md`](ACCESSIBILITY_AUDIT.md) détaille les vérifications et les limites ; Glimio ne revendique pas une conformité WCAG globale certifiée.

## Git et contribution

Le `.gitignore` exclut l’état local, les séances, les poids de modèles, les exécutables et les binaires compilés. Avant le premier push, vérifie `git status --ignored` et assure-toi qu’aucun poids IA, exécutable, fichier audio de test privé, base SQLite ou secret n’est inclus. Si de tels fichiers ont déjà été indexés par Git, `.gitignore` ne les retire pas de l’index : suis les étapes de [`docs/GIT_PREPARATION.md`](docs/GIT_PREPARATION.md).

Les contributions doivent inclure des tests et documenter les nouveaux modèles/dépendances. Voir [`CONTRIBUTING.md`](CONTRIBUTING.md) et [`SECURITY.md`](SECURITY.md). Les changements notables se trouvent dans [`CHANGELOG.md`](CHANGELOG.md).

## Licence

Le code propre à Glimio est publié sous **GNU AGPL v3 ou toute version ultérieure**. Cette licence préserve le copyleft, y compris pour les modifications proposées comme service réseau. Elle n’interdit pas la vente commerciale et n’impose pas une contribution au projet amont : aucune licence reconnue comme open source ne peut interdire l’usage commercial. La marque Glimio et ses éléments visuels ne sont pas accordés comme marques par la licence du code. Cette licence ne remplace pas les conditions distinctes des modèles IA, exécutables ou autres composants tiers. Consulte [`docs/MODELS.md`](docs/MODELS.md) avant de télécharger ou redistribuer leurs poids.
