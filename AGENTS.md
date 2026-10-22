# Conventions de code pour les assistants

Ces règles s’appliquent aux assistants de programmation qui modifient Glimio. Avant un changement, lire les documents pertinents : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) pour les frontières, [`docs/FRONTEND.md`](docs/FRONTEND.md) pour Angular et Tailwind, [`CONTRIBUTING.md`](CONTRIBUTING.md) pour les validations et [`docs/RELEASING.md`](docs/RELEASING.md) pour les versions.

## Frontières et structure

- Garder l’application Python (`src/seance` et `src/web`) indépendante du client web (`src/web/frontend`). Le cœur et les providers Python ne doivent importer ni Angular ni FastAPI; le frontend ne dépend que de l’API HTTP/SSE.
- Respecter les sous-paquets existants (`seance/media`, `seance/processing`, `seance/providers`). Placer chaque nouvelle responsabilité dans la couche qui la possède; éviter les modules de compatibilité et les réexports ajoutés uniquement pour préserver un ancien chemin d’import.
- Intégrer les moteurs IA et outils remplaçables derrière les contrats et fabriques de providers. Garder leurs options, formats, arguments, détection de disponibilité et détails d’exécution dans l’adaptateur correspondant. Exposer au frontend les capacités, options et états par les contrats API génériques; ne pas coder les noms de moteurs ou leurs options en dur dans Angular.
- Les traitements et événements métier restent dans le cœur Python. La couche Web les adapte à l’API et au flux SSE; le frontend réutilise le service d’événements partagé au lieu d’ajouter du polling pour suivre les traitements.
- Ne pas ajouter de dépendance à un outil externe sans en documenter la raison, l’installation, la version et la licence. FFmpeg est requis pour les conversions média qui le nécessitent; les autres moteurs doivent rester échangeables via leurs providers.

## Python

- Suivre le style et les motifs des modules voisins. Garder les types métier et contrats indépendants des frameworks; typer les nouvelles frontières publiques et convertir les erreurs propres aux moteurs en erreurs de domaine compréhensibles.
- Garder l’orchestration, la persistance et les règles métier dans les use cases. Un provider s’occupe de communiquer avec son moteur et de traduire ses entrées, options, événements et résultats vers les types Glimio.
- Éviter les appels bloquants dans les handlers asynchrones de l’API. Pour les longues tâches, utiliser le système de jobs existant et publier des événements compatibles avec le suivi SSE.

## Angular 22, Tailwind CSS 4.3.3 et styles

- Conserver la séparation des composants en fichiers `.ts`, `.html` et `.scss`, ainsi que l’organisation par fonctionnalités sous `src/web/frontend/src/app/pages` et les éléments communs sous `src/web/frontend/src/app/shared`.
- Réutiliser les composants, services, contrôles, jetons et styles partagés existants avant d’en créer de nouveaux. Utiliser `glimio-icon` avec les Heroicons enregistrées; ne pas intégrer de SVG d’icône à la main.
- Toute chaîne visible doit utiliser le système de traduction existant (`interface-language.service.ts`) et être fournie dans toutes les langues prises en charge.
- Dans un SCSS de composant, importer les utilitaires Tailwind avec `@reference` vers `src/web/frontend/src/styles/tailwind-ref.scss`, puis privilégier `@apply` et les jetons du projet. Garder les règles CSS spécifiques aux cas structurels ou dynamiques qui ne se traduisent pas proprement en utilitaires.
- Réserver `src/web/frontend/src/styles/components.scss` aux styles réellement communs. Ne pas dupliquer des styles globaux dans les pages ni recopier un composant standard pour un usage local. Vérifier le budget de style Angular avant d’ajouter beaucoup de règles à une page.
- Respecter l’accessibilité et les motifs Angular déjà utilisés : contrôles natifs, libellés associés, focus clavier visible, état accessible, responsive, signaux/RxJS et gestion du cycle de vie sans abonnement ou écouteur laissé actif.

## Modifications et vérification

- Faire des changements ciblés et préserver les modifications préexistantes. Ne supprimer un document, contrat ou chemin que si ses références et son rôle ont été vérifiés.
- Mettre à jour les traductions et la documentation quand le comportement visible, les options d’un provider, la configuration ou l’installation change. Ajouter les notes de version dans `CHANGELOG.md` quand le travail fait partie de la préparation d’une release; suivre `docs/RELEASING.md`.
- Exécuter les vérifications pertinentes décrites dans `CONTRIBUTING.md` et `docs/FRONTEND.md`; ne pas affirmer qu’une compilation ou des tests ont réussi s’ils n’ont pas été lancés.
