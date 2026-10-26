# Architecture et frontières applicatives

## Couches

- `seance` est le cœur Python : cas d’usage, orchestration des traitements, formats de séance, CLI, services `seance.core` et contrats des providers. Il ne dépend pas de FastAPI, Angular ou des services Web.
- `seance.core` contient les opérations métier partagées : bibliothèque, mutations des séances/pistes, artefacts, recherche et synthèse, persistance SQLite, préférences, historique des jobs et détection des périphériques. Ce sont des fonctions Python indépendantes du terminal et de HTTP.
- `seance.cli` et `seance.cli_commands` adaptent les commandes du terminal à ces opérations. Le CLI peut fonctionner seul sans installer les dépendances Web.
- `web` est l’adaptateur HTTP : FastAPI, validation des requêtes, file de jobs en direct, endpoints, et traduction des événements du cœur vers l’API consommée par Angular.
- `src/web/frontend` est le client Angular. Il consomme les contrats JSON de l’API et ne connaît pas les détails internes des providers.
- `seance.providers` contient les contrats neutres (`TextGenerationProvider`, `TranscriptionProvider`, `ProviderInfo`, `ProviderStatus`, `ProviderEvent`), le catalogue, les diagnostics, le gestionnaire d’installation et le CLI des providers. Les formats éditeur ne doivent pas sortir des adaptateurs.

Les providers ne doivent jamais importer `web`, FastAPI ou le frontend. Le code Web peut dépendre de `seance` pour assembler l’application et exposer ses informations. Le CLI et l’interface Web appellent les mêmes cas d’usage Python.

## Exécution indépendante

- `glimio` / `seance.cli` fonctionne sans l’extra `web` ; aucun import de FastAPI ne doit être requis par le graphe d’import CLI.
- `glimio-web` / `web.app` démarre directement le serveur ASGI et ne doit pas importer le point d’entrée `seance.cli`.
- Les deux adaptateurs assemblent les mêmes cas d’usage et services, mais aucune entrée ne démarre l’autre. Les tests de frontières gardent ce contrat vérifiable.
- Angular ne fournit que l’interface HTTP/SSE. Ses sélecteurs, champs et options de provider sont rendus depuis les métadonnées ; l’ajout d’un moteur ne nécessite pas de modifier les composants de réglages.

## Sélection automatique du format de résumé

Les identifiants et leurs consignes vivent dans `seance.processing.report_formats`, partagé par la CLI et la Web API : `auto`, `summary`, `narrative`, `dialogue`, `learning`, `daily`, `technical`, `formal`, `brainstorm`. `narrative` couvre les récits, fictions, livres audio et sessions de roleplay ; `dialogue` privilégie les questions/réponses et points de vue ; `learning` met l’accent sur les connaissances et exemples. Les formats de suivi de réunion (`daily`, `formal`, `brainstorm`) et l’analyse technique restent disponibles. Les sélecteurs Enregistrement et Bibliothèque décrivent chaque choix.

Le format `auto` classe la transcription originale (échantillons du début, du milieu et de la fin), pas les notes déjà reformulées. Le classificateur doit retourner une décision structurée avec une confiance élevée et deux citations de la source pour tout format spécialisé. Le cœur vérifie que les deux extraits existent après normalisation lexicale ; si le JSON est invalide, si la confiance n’est pas élevée ou si les preuves ne correspondent pas à la transcription, le format général `summary` est retenu. Ce repli est volontairement conservateur : une synthèse générale est préférable à une structure de sortie inadaptée. Le motif et les extraits validés sont consignés dans `analysis/format_selection.txt`. Un format explicitement choisi par l’utilisateur n’est pas reclassifié.

Les marqueurs de transcription sont expliqués aux étapes de classification, d’analyse, de rédaction et de relecture : un préfixe `Speaker N` est un identifiant de voix anonyme, l’horodatage est une métadonnée et `Micro`/`Audio Windows` correspond à une piste source, pas à une identité. Un vrai nom n’est associé à une voix que lorsque la transcription établit ce lien de façon explicite et non ambigu. Dans un livre audio ou un roleplay, une voix ne doit pas être confondue avec le personnage qu’elle interprète.

## Langue des résumés et variantes traduites

La langue de sortie est une option de traitement commune (`summary_language`) : `auto` demande au modèle de suivre la langue dominante de la transcription, et les codes de langue supportés forcent une rédaction explicite. Une détection lexicale sans dépendance supplémentaire fixe la langue des prompts et des titres lorsque la source est claire ; en cas d’incertitude, le prompt demande au modèle de suivre directement la transcription. La décision est tracée dans `analysis/summary_language_selection.txt`. Les variantes de traduction après génération restent distinctes de l’artefact original dans `summary/translations/` ; l’API expose uniquement les codes de langue validés, et leur génération réutilise la file de jobs Web ainsi que le provider de génération configuré. Une traduction a posteriori ne relance pas l’analyse et ne remplace pas les paramètres par défaut de la séance.

## Organisation du code Python

- `seance/media` regroupe la capture audio et l’import des médias.
- `seance/processing` regroupe l’orchestration, la transcription, la diarisation et la génération des comptes rendus. Le provider de diarisation sélectionné s’exécute dans un processus enfant (`diarization_process`) afin d’isoler les bibliothèques natives susceptibles de bloquer le GIL du serveur Web ; le suivi et l’annulation restent pilotés par le processus parent.
- `seance/providers` regroupe les contrats, fabriques, diagnostics et adaptateurs de moteurs.
- `seance/core` regroupe les cas d’usage et la persistance que les deux interfaces utilisent. `seance/media` et `seance/processing` restent des services métier exécutés par la CLI comme par la Web app.
- Les modules racine de `seance` portent les contrats transverses (`layout`, résolution des chemins de séance (`session_paths`), résolution des exécutables média (`executables`), runtime, LLM, chemins du projet et point d’entrée CLI).
- Les imports utilisent directement ces sous-paquets ; aucun module de compatibilité ne duplique les anciens chemins.

## Contrat d’un provider

Chaque adaptateur déclare un identifiant stable, les tâches prises en charge, les capacités et son mode d’exécution. Il expose un diagnostic de disponibilité sans charger de modèle. À l’exécution, il retourne des types de domaine Glimio et peut émettre des `ProviderEvent` structurés : provider, tâche, étape, message, progression facultative et détails destinés à l’affichage.

Les intégrations tierces peuvent s’enregistrer par les `entry points` Python du groupe `glimio.providers`. Le catalogue les découvre au démarrage, expose leurs métadonnées à la CLI/API et résout leur fabrique au moment de l’utilisation. Une intégration défectueuse est ignorée avec un avertissement plutôt que de bloquer toutes les commandes. Les tâches extensibles couvrent génération, transcription, diarisation, média, amélioration audio, séparation et embeddings vocaux. Les contrats propres à chaque tâche sont décrits dans `docs/PROVIDERS.md`.

La sélection de la diarisation suit le même principe que la génération et la transcription : `diarization_provider` choisit un adaptateur, ses options sont stockées dans `provider_options[provider_id]`, et les tours de parole retournés utilisent `SpeakerTurn`. Le cœur ne dépend donc plus directement de `sherpa-onnx`. Les options historiques restent prises en charge comme alias pour la migration des réglages existants.

Les options configurables sont déclarées comme `ProviderOption` dans `ProviderInfo`, avec type de champ, valeur par défaut, choix, contraintes et indication « avancée ». L’API REST transmet ces métadonnées avec l’état du provider. Angular ne contient ni identifiant de moteur ni liste de paramètres propres à un moteur : il rend le schéma reçu et enregistre les valeurs par identifiant de provider. Retirer un provider de son registre retire donc également son choix et ses options de l’API et de l’interface. La couche Web valide et persiste les paramètres, puis transmet le dictionnaire d’options à l’adaptateur sélectionné ; le cœur Python n’importe jamais le frontend et le frontend n’importe jamais Python.

L’accélération matérielle est déclarée et interprétée par chaque provider, au moyen de ses `ProviderOption` et de son adaptateur. Il n’existe pas de réglage global CPU/GPU/NPU : les moteurs n’acceptent pas tous les mêmes backends, périphériques ou prérequis, et l’interface ne propose que les choix annoncés par le provider sélectionné. Les variables d’environnement et arguments propres à un moteur restent confinés à son adaptateur ; l’orchestration et le contrat REST restent génériques. OpenVINO est donc une option facultative propre aux providers compatibles, désactivée par défaut.

### Chaîne média

`MediaToolchainProvider` décrit les trois opérations dont les use cases média ont besoin : `probe_audio_streams`, `extract_track` et `extract_chunk`. `seance.providers.media_tools` fournit l’adaptateur FFmpeg/ffprobe (`ffmpeg`, exécutable système avec les options `ffmpeg`/`ffprobe`) et l’adaptateur natif (`native`, module `wave` et `numpy`, sans exécutable, limité au WAV PCM 16 bits à 16 kHz). La fabrique `create_media_provider` résout l’identifiant `media_provider` ; la couche Web valide cet identifiant et l’expose aux préférences.

Les cas d’usage (`seance.media.audio_import`, `seance.processing.transcription`, `seance.processing.minutes`) choisissent le provider, appliquent la normalisation, le repli WAV natif du découpage, l’annulation et le nettoyage des artefacts ; ils ne construisent aucune ligne de commande. Les contrats `AudioStreamInfo`, `AudioTrackRequest` et `AudioChunkRequest` fixent l’invariant de sortie (mono PCM16 16 kHz, plage d’au moins 0,1 s quand la source le permet) et les erreurs de moteur sont traduites en `MediaToolchainError`, `MediaToolchainUnavailable` ou `MediaCancelled`. Les options propres à un moteur, la détection de disponibilité et le diagnostic restent dans l’adaptateur.

Les use cases possèdent le découpage, les reprises, la persistance, l’annulation et les règles métier. L’adaptateur gère la communication avec son moteur, traduit ses options et convertit les résultats vers les types Glimio. Les fabriques de `seance.providers.factory` résolvent les identifiants sélectionnés dans les paramètres. Un provider intégré demande un adaptateur et une inscription au catalogue ; un provider tiers peut s'enregistrer avec l'entry point Python `glimio.providers`, sans modifier les use cases ni les formats de séance.

FFmpeg est un provider système pour l’import et la conversion média : les formats pris en charge dépendent du binaire distribué/configuré. Les éditions précompilées gardent les dépendances lourdes des providers optionnelles. `seance.providers.installer` télécharge à la demande un runtime CPython autonome vérifié par SHA-256 et installe uniquement les paquets déclarés dans le catalogue ; le runtime et les roues restent sous les données utilisateur, hors du dossier PyInstaller. Le CLI expose `providers list`, `info`, `install` et `doctor` sans importer la couche Web. Les modèles et exécutables natifs restent séparés. « Local » et « sans installation externe » sont des propriétés de distribution à déclarer dans `ProviderInfo.execution`, pas des hypothèses du pipeline.

## État exposé à l’utilisateur

`GET /api/providers` fournit les métadonnées et vérifications de disponibilité sans lancer de processus ni télécharger de fichiers. Les événements d’exécution restent neutres dans le cœur Python ; l’adaptateur Web les expose dans l’état des tâches par un flux Server-Sent Events, et le CLI les affiche en texte. Le frontend partage une connexion SSE pour les compteurs, la file, l’enregistrement, la bibliothèque et la recherche ; les endpoints REST restent utilisés pour charger et modifier les ressources. Les interfaces de génération, transcription et diarisation utilisent leur adaptateur actif, et les chaînes média/audio consomment des contrats remplaçables. Certaines étapes historiques du pipeline gardent encore des choix spécifiques à Glimio et restent candidates à une extraction supplémentaire.

## Frontières de dépendances CLI/Web

`.[cli]` correspond au socle installable sans framework Web. Les dépendances de FastAPI, Uvicorn et des uploads sont déclarées dans l’extra `.[web]`, et les providers lourds dans `.[diarization]` / `.[separation]` ou le runtime géré des éditions précompilées. Importer `seance.cli` ne doit pas charger `fastapi` ni `uvicorn`.

Les commandes `sessions`, `artifacts`, `preferences`, `jobs`, `devices` et `search` sont des adaptateurs de `seance.core`, pas des appels HTTP au serveur local. La seule opération nécessitant le serveur Web est l’annulation d’un job Web en cours : le worker et ses signaux d’annulation sont encore hébergés dans le processus Web. Les traitements démarrés en CLI restent synchrones dans le processus CLI.
