# Architecture et frontières applicatives

## Couches

- `seance` est le cœur Python : cas d’usage, orchestration des traitements, formats de séance, CLI, services `seance.core` et contrats des providers. Il ne dépend pas de FastAPI, Angular ou des services Web.
- `seance.core` contient les opérations métier partagées : bibliothèque, mutations des séances/pistes, artefacts, recherche et synthèse, persistance SQLite, préférences, historique des jobs et détection des périphériques. Ce sont des fonctions Python indépendantes du terminal et de HTTP.
- `seance.cli` et `seance.cli_commands` adaptent les commandes du terminal à ces opérations. Le CLI peut fonctionner seul sans installer les dépendances Web.
- `web` est l’adaptateur HTTP : FastAPI, validation des requêtes, file de jobs en direct, endpoints, et traduction des événements du cœur vers l’API consommée par Angular.
- `src/web/frontend` est le client Angular. Il consomme les contrats JSON de l’API et ne connaît pas les détails internes des providers.
- `seance.providers` contient les contrats neutres (`TextGenerationProvider`, `TranscriptionProvider`, `ProviderInfo`, `ProviderStatus`, `ProviderEvent`), le catalogue, les diagnostics, le gestionnaire d’installation et le CLI des providers. Les formats éditeur ne doivent pas sortir des adaptateurs.

Les providers ne doivent jamais importer `web`, FastAPI ou le frontend. Le code Web peut dépendre de `seance` pour assembler l’application et exposer ses informations. Le CLI et l’interface Web appellent les mêmes cas d’usage Python.

## Organisation du code Python

- `seance/media` regroupe la capture audio et l’import des médias.
- `seance/processing` regroupe l’orchestration, la transcription, la diarisation et la génération des comptes rendus. La diarisation native `sherpa-onnx` s’exécute dans un processus enfant (`diarization_process`) pour ne pas bloquer le GIL du serveur Web ; les callbacks de suivi et l’annulation restent pilotés par le processus parent.
- `seance/providers` regroupe les contrats, fabriques, diagnostics et adaptateurs de moteurs.
- `seance/core` regroupe les cas d’usage et la persistance que les deux interfaces utilisent. `seance/media` et `seance/processing` restent des services métier exécutés par la CLI comme par la Web app.
- Les modules racine de `seance` portent les contrats transverses (`layout`, résolution des chemins de séance (`session_paths`), runtime, LLM, chemins du projet et point d’entrée CLI).
- Les imports utilisent directement ces sous-paquets ; aucun module de compatibilité ne duplique les anciens chemins.

## Contrat d’un provider

Chaque adaptateur déclare un identifiant stable, les tâches prises en charge, les capacités et son mode d’exécution. Il expose un diagnostic de disponibilité sans charger de modèle. À l’exécution, il retourne des types de domaine Glimio et peut émettre des `ProviderEvent` structurés : provider, tâche, étape, message, progression facultative et détails destinés à l’affichage.

Les options configurables sont déclarées comme `ProviderOption` dans `ProviderInfo`, avec type de champ, valeur par défaut, choix, contraintes et indication « avancée ». L’API REST transmet ces métadonnées avec l’état du provider. Angular ne contient ni identifiant de moteur ni liste de paramètres propres à un moteur : il rend le schéma reçu et enregistre les valeurs par identifiant de provider. Retirer un provider de son registre retire donc également son choix et ses options de l’API et de l’interface. La couche Web valide et persiste les paramètres, puis transmet le dictionnaire d’options à l’adaptateur sélectionné ; le cœur Python n’importe jamais le frontend et le frontend n’importe jamais Python.

L’accélération matérielle est déclarée et interprétée par chaque provider, au moyen de ses `ProviderOption` et de son adaptateur. Il n’existe pas de réglage global CPU/GPU/NPU : les moteurs n’acceptent pas tous les mêmes backends, périphériques ou prérequis, et l’interface ne propose que les choix annoncés par le provider sélectionné. Les variables d’environnement et arguments propres à un moteur restent confinés à son adaptateur ; l’orchestration et le contrat REST restent génériques. OpenVINO est donc une option facultative propre aux providers compatibles, désactivée par défaut.

Les use cases possèdent le découpage, les reprises, la persistance, l’annulation et les règles métier. L’adaptateur gère la communication avec son moteur, traduit ses options et convertit les résultats vers les types Glimio. Les fabriques de `seance.providers.factory` résolvent les identifiants sélectionnés dans les paramètres. Ajouter un moteur demande un adaptateur et une inscription dans la fabrique et le catalogue, sans modifier les use cases ni les formats de séance.

FFmpeg est un provider système pour l’import et la conversion média : les formats pris en charge dépendent du binaire distribué/configuré. Les éditions précompilées gardent les dépendances lourdes des providers optionnelles. `seance.providers.installer` télécharge à la demande un runtime CPython autonome vérifié par SHA-256 et installe uniquement les paquets déclarés dans le catalogue ; le runtime et les roues restent sous les données utilisateur, hors du dossier PyInstaller. Le CLI expose `providers list`, `info`, `install` et `doctor` sans importer la couche Web. Les modèles et exécutables natifs restent séparés. « Local » et « sans installation externe » sont des propriétés de distribution à déclarer dans `ProviderInfo.execution`, pas des hypothèses du pipeline.

## État exposé à l’utilisateur

`GET /api/providers` fournit les métadonnées et vérifications de disponibilité sans lancer de processus ni télécharger de fichiers. Les événements d’exécution restent neutres dans le cœur Python ; l’adaptateur Web les expose dans l’état des tâches par un flux Server-Sent Events, et le CLI les affiche en texte. Le frontend partage une connexion SSE pour les compteurs, la file, l’enregistrement, la bibliothèque et la recherche ; les endpoints REST restent utilisés pour charger et modifier les ressources. Les interfaces de génération et transcription ont leur adaptateur actif. FFmpeg et sherpa-onnx sont inventoriés, mais leurs intégrations existantes restent à extraire derrière des adaptateurs avant de pouvoir être remplacées via la fabrique.

## Frontières de dépendances CLI/Web

`.[cli]` correspond au socle installable sans framework Web. Les dépendances de FastAPI, Uvicorn et des uploads sont déclarées dans l’extra `.[web]`, et les providers lourds dans `.[diarization]` / `.[separation]` ou le runtime géré des éditions précompilées. Importer `seance.cli` ne doit pas charger `fastapi` ni `uvicorn`.

Les commandes `sessions`, `artifacts`, `preferences`, `jobs`, `devices` et `search` sont des adaptateurs de `seance.core`, pas des appels HTTP au serveur local. La seule opération nécessitant le serveur Web est l’annulation d’un job Web en cours : le worker et ses signaux d’annulation sont encore hébergés dans le processus Web. Les traitements démarrés en CLI restent synchrones dans le processus CLI.
