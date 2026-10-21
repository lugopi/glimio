# Architecture et frontières applicatives

## Couches

- `seance` est le cœur Python : cas d’usage, orchestration des traitements, formats de séance, CLI et contrats des providers. Il ne dépend pas de FastAPI, Angular ou des services Web.
- `web` est l’adaptateur HTTP : FastAPI, endpoints, persistance de l’application et traduction des événements du cœur vers l’API consommée par Angular.
- `src/web/frontend` est le client Angular. Il consomme les contrats JSON de l’API et ne connaît pas les détails internes des providers.
- `seance.providers` contient les contrats neutres (`TextGenerationProvider`, `TranscriptionProvider`, `ProviderInfo`, `ProviderStatus`, `ProviderEvent`). Les formats éditeur ne doivent pas sortir des adaptateurs.

Les providers ne doivent jamais importer `web`, FastAPI ou le frontend. Le code Web peut dépendre de `seance` pour assembler l’application et exposer ses informations. Le CLI et l’interface Web appellent les mêmes cas d’usage Python.

## Organisation du code Python

- `seance/media` regroupe la capture audio et l’import des médias.
- `seance/processing` regroupe l’orchestration, la transcription, la diarisation et la génération des comptes rendus.
- `seance/providers` regroupe les contrats, fabriques, diagnostics et adaptateurs de moteurs.
- Les modules restants à la racine de `seance` portent les services partagés (`layout`, `sessions`, `runtime`, `llm`, chemins et CLI).
- Les imports utilisent directement ces sous-paquets ; aucun module de compatibilité ne duplique les anciens chemins.

## Contrat d’un provider

Chaque adaptateur déclare un identifiant stable, les tâches prises en charge, les capacités et son mode d’exécution. Il expose un diagnostic de disponibilité sans charger de modèle. À l’exécution, il retourne des types de domaine Glimio et peut émettre des `ProviderEvent` structurés : provider, tâche, étape, message, progression facultative et détails destinés à l’affichage.

Les use cases possèdent le découpage, les reprises, la persistance, l’annulation et les règles métier. L’adaptateur gère la communication avec son moteur, traduit ses options et convertit les résultats vers les types Glimio. Les fabriques de `seance.providers.factory` résolvent les identifiants sélectionnés dans les paramètres. Ajouter un moteur demande un adaptateur et une inscription dans la fabrique et le catalogue, sans modifier les use cases ni les formats de séance.

FFmpeg est un provider système pour l’import et la conversion média : les formats pris en charge dépendent du binaire distribué/configuré. Les autres providers peuvent être embarqués ou intégrés au paquet Python selon les bibliothèques et licences disponibles. « Local » et « sans installation externe » sont des propriétés de distribution à déclarer dans `ProviderInfo.execution`, pas des hypothèses du pipeline.

## État exposé à l’utilisateur

`GET /api/providers` fournit les métadonnées et vérifications de disponibilité sans lancer de processus ni télécharger de fichiers. Les événements d’exécution restent neutres dans le cœur Python ; l’adaptateur Web les expose dans l’état des tâches, et le CLI les affiche en texte. Les interfaces de génération et transcription ont leur adaptateur actif. FFmpeg et sherpa-onnx sont inventoriés, mais leurs intégrations existantes restent à extraire derrière des adaptateurs avant de pouvoir être remplacées via la fabrique.
