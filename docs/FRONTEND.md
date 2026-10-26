# Guide du frontend

## Architecture

L’interface servie à `/` est l’application Angular 22. FastAPI fournit les routes `/api/*` et sert le build SPA depuis `dist/glimio-web-ui` à la racine du dépôt. Un import de `web.app` depuis les tests Python ne doit pas installer les dépendances ni lancer npm.

Les sources Angular se trouvent dans `src/web/frontend/src/app`. Les pages sont regroupées par fonctionnalité et les éléments partagés dans `src/web/frontend/src/app/shared`. Les composants gardent leur logique, leur template et leurs styles dans des fichiers séparés (`.ts`, `.html`, `.scss`).

## Providers et réglages

Les champs des providers sont construits à partir des métadonnées renvoyées par l’API (options, descriptions, disponibilité et dépendances). Remplacer un provider par un autre du même rôle ne doit donc pas nécessiter de nouvelle branche dans Angular. Les dépendances déclarées via `requires` sont regroupées dans « Outils et composants requis » ; leurs identifiants restent des liens vers le réglage correspondant, avec un repli vers le provider demandeur si le plugin requis n’est pas présent dans le catalogue. Les liens profonds ouvrent la section « Plus de paramètres » lorsqu’elle contient la cible. Sur la page Paramètres, les options d’un provider prêt sont repliées par défaut. Son aide à l’installation, ses dépendances Python et ses ressources sont regroupées dans un seul volet « Installation et documentation », fermé par défaut quand le provider est prêt et ouvert lorsqu’il ne l’est pas ; un état d’installation en cours ou récent reste visible. Les composants non prêts conservent leurs champs de configuration et leurs aides visibles pour faciliter le diagnostic. Le repli ne supprime aucune action : options, contrôle de disponibilité, installation et liens documentaires restent accessibles au clavier. L’avertissement et les liens de dépendance utilisent ces mêmes métadonnées pour éviter de coder les identifiants de plugins dans l’affichage générique.

## Résumés et langues

La génération du résumé expose `summary_language` dans les paramètres partagés et ceux d’une séance. `auto` demande au modèle de conserver la langue dominante de la transcription ; les codes `fr`, `en`, `de`, `it`, `es`, `pt` et `nl` imposent une langue de sortie. Les consignes de langue sont appliquées aux notes d’analyse, à la rédaction, à la vue d’ensemble, au titre des rapports assemblés et à la relecture. Quand `auto` est choisi, une détection lexicale sans dépendance supplémentaire fixe explicitement la langue de génération si la transcription est suffisamment claire ; sinon, les prompts gardent l’instruction de suivre la source. Le choix appliqué est consultable dans `analysis/summary_language_selection.txt`.

Les formats de résumé disponibles pour Enregistrement et les options d’une séance partagent le catalogue UI `src/app/shared/summary-formats.ts` ; leurs identifiants autorisés sont centralisés côté Python dans `seance.processing.report_formats`. Le sélecteur affiche une courte description contextuelle : synthèse générale, récit narratif (livre audio/fiction/roleplay), dialogue/conversation, cours/explication et formats dédiés aux réunions (point d’avancement, analyse technique, réunion formelle, idéation). Le mode `auto` compare l’intention du contenu à ces formats et revient à `summary` lorsque sa décision n’est pas suffisamment étayée. Les marqueurs tels que `Speaker 1:` sont décrits au modèle comme des métadonnées de locuteur, et le nom d’une piste audio n’est pas considéré comme l’identité d’un intervenant ; un nom ou personnage n’est utilisé que si la source l’établit clairement.

Depuis les détails d’une séance, le menu d’actions du résumé regroupe l’édition de la version originale, l’export Markdown, l’impression/PDF et la création d’une variante traduite. Les traductions sont des fichiers séparés sous `summary/translations/<code>.md` ; elles ne remplacent pas `summary/resume_audio.md` et sont accessibles via le sélecteur « Version affichée ». Le job `translate-summary` passe par la même file de traitement et le provider de génération sélectionné, sans relancer transcription ni analyse. Une demande de traduction ponctuelle ne modifie pas les préférences de langue de résumé.

## Recherche intelligente

La page de recherche utilise le contrat REST `/api/search/start` pour récupérer les extraits et le flux SSE partagé pour afficher la progression. La propriété `session_ids` limite réellement la récupération documentaire aux séances sélectionnées ; une liste vide signifie une recherche globale. Dans l’interface, les suggestions déclenchées par `@` et le sélecteur « Ajouter des séances » alimentent cette même liste d’identifiants.

Les changements d’inclusion des extraits sont locaux tant que l’utilisateur ne les confirme pas. `/api/search/{id}/synthesize` reçoit les identifiants stables des extraits conservés et régénère uniquement la synthèse à partir de ceux-ci, sans refaire la recherche documentaire. L’API expose `included` et `citation_number` pour conserver les extraits exclus visibles, permettre de revenir sur son choix et renuméroter les références de la synthèse. Tout changement de sélection doit donc rester sans appel réseau jusqu’à confirmation explicite.
Les listes de la bibliothèque, des séances du sélecteur de recherche et des extraits pertinents réutilisent `glimio-standard-list` : la surface et les séparateurs sont communs, la rangée mise en évidence porte le marqueur vertical à gauche, et le contenu de chaque ligne reste fourni par un template propre à la fonctionnalité. Les extraits inclus utilisent ce marqueur ; les extraits exclus restent visibles mais atténués. Les éléments réutilisables gardent leurs feuilles SCSS avec `@reference` et privilégient `@apply`, y compris dans les media queries. Les extraits et le sélecteur de séances sont isolés dans des composants autonomes avec leurs propres feuilles de style pour maintenir le budget de style des pages. La synthèse générale peut être exportée en Markdown ou ouverte dans la vue d’impression partagée afin d’être enregistrée en PDF. Ces actions sont accessibles depuis le menu overflow de son en-tête et réutilisent `DocumentExportService`, comme les exports de la bibliothèque. Le sélecteur de séances reprend les cartes, la date, la durée et les badges de la bibliothèque tout en gardant une sélection multi-séances par cases à cocher.

## Outils et commandes

Les versions Angular, TypeScript et Tailwind sont définies dans `src/web/frontend/package.json` et son lockfile. La version Node de référence est inscrite dans `src/web/frontend/.nvmrc` ; le contrat `engines` du package indique les versions compatibles.

Depuis `src/web/frontend`, après activation d’une version Node compatible :

```powershell
npm ci
npm run typecheck
npm test
npm run build
```

Depuis la racine du dépôt, lancer les tests backend avec :

```powershell
python -m pytest -q src/tests
```

## Conventions Angular et Tailwind CSS 4

- L’entrée Tailwind est `src/web/frontend/src/styles/tailwind.css`, un fichier CSS simple qui importe `tailwindcss`. Ne pas y substituer un import Sass.
- Les feuilles Sass partagées sont composées dans `src/web/frontend/src/styles/main.scss` avec `@use`.
- Dans un fichier SCSS de composant, charger les utilitaires avec `@reference` vers `src/web/frontend/src/styles/tailwind-ref.scss`, puis privilégier les utilitaires Tailwind via `@apply`.
- Les tailles sémantiques partagées `text-compact`, `text-caption` et `text-micro` sont définies par `--text-*` dans `styles/tokens.scss` et `styles/tailwind.css`. Tout nouveau nom utilisé par `@apply` doit être déclaré dans le thème Tailwind 4 puis vérifié par `npm run build` ; les contrôles statiques seuls ne valident pas la résolution des utilitaires.
- Les propriétés CSS standard qui disposent d'un utilitaire Tailwind doivent passer par `@apply`, notamment display, dimensions, marges, padding, alignements, couleurs, positionnement, bordures et typographie. Par exemple, employer `@apply border-l-3 border-l-danger` plutôt que `border-left: 3px solid var(--c-danger)`. Pour les valeurs sémantiques calculées avec `color-mix()` ou les ombres réutilisables, créer un jeton dans `tokens.scss` et `tailwind.css`, puis utiliser l'utilitaire généré (`bg-danger-banner`, `bg-success-soft`, `border-danger-border`, `shadow-danger-halo`, etc.) plutôt que de répéter la valeur calculée dans les composants. Ne conserver du CSS direct que si aucun utilitaire/jeton ne reproduit fidèlement le besoin ou si la cascade impose une exception documentée. Éviter les variantes personnalisées et les doublons pour un style ponctuel.
- Minimiser les utilitaires à valeur arbitraire (`h-[84px]`, `text-[13px]`, `grid-cols-[...]`). Utiliser l’échelle Tailwind et les jetons existants d’abord ; pour une largeur ou grille de structure qui doit rester précise, préférer une propriété CSS claire et un jeton partagé aux valeurs entre crochets répétées. Ne pas remplacer une valeur arbitraire par une valeur numérique inhabituelle uniquement pour la cacher : chaque exception doit être justifiée par une contrainte réelle et rester limitée à son composant ou à son jeton.
- `modern-normalize.scss` conserve le comportement natif des éléments `summary` avec `display: list-item` dans une règle hors couche. `.session-actions-toggle` a donc besoin d’un override `display: grid` hors `@layer`, sinon le reset non classé peut l’emporter sur l’utilitaire Tailwind et décaler son icône.
- Pour les déclarations partagées, déplacer les dimensions, alignements, espacements, typographie, bordures et états standards dans `@apply` avec les jetons existants. Garder en CSS direct les valeurs réellement spécifiques (par exemple `color-mix()`, ombres/animations/transitions sur mesure, grilles structurelles ou règles conditionnelles comme `[hidden]`). Ne pas compacter plusieurs règles en une ligne pour gagner quelques caractères : privilégier un SCSS lisible et facile à auditer. Les règles `.session-actions-*`, `.menu-toggle-icon`, champs, badges et boutons partagés restent centralisées ici, sans surcharge locale équivalente.
- Garder `src/web/frontend/src/styles/components.scss` pour les styles réellement partagés entre plusieurs pages ou composants. Les styles propres à une page restent dans son SCSS.
- Réutiliser les composants partagés (icônes, pagination, champs communs) au lieu de créer une variante locale équivalente.
- Les commandes d’action en menu utilisent `.session-actions-menu` / `.session-actions-toggle` définis dans les styles partagés : 40 px sur grand écran, 44 px de cible tactile sur petit écran. Toutes les icônes de déclencheur burger portent `.menu-toggle-icon` : boîte et SVG de 20 px, centrés, partagés avec le menu principal mobile ; ne pas ajouter de dimension locale par page. Ne pas redéfinir leur taille dans une page ou un composant de piste audio. Les boutons ordinaires, champs, badges et états de job/providers reprennent les hauteurs partagées ; conserver les hauteurs plus grandes uniquement pour les actions principales explicites (par exemple démarrer/arrêter un enregistrement).
- Garder un rythme vertical compact : 12 px entre les champs ou panneaux empilés, 6 px entre un libellé et son aide/champ lorsque cela reste lisible. Sur mobile, réduire le padding des panneaux à 16 px et garder une cible d’au moins 44 px pour les menus d’action.
- Conserver les associations label/champ, le focus clavier visible et les noms accessibles. Masquer un champ conditionnel quand son option parente est inactive ; le désactiver seulement quand il reste pertinent mais temporairement indisponible.
- Le budget `anyComponentStyle` conserve un avertissement à 12 kB et une erreur à 20 kB. Si une page approche du seuil, extraire les blocs fonctionnels cohérents dans des composants autonomes réutilisables avec leurs propres styles, plutôt que de relever le budget ou de déplacer des styles propres à une page dans la feuille globale.

## Vérification de l’interface

Après compilation, vérifier les parcours modifiés au clavier et dans les thèmes concernés. Pour une revue responsive, couvrir 320, 375, 768, 1024 et 1440 px ainsi que le zoom à 200 % et 400 %. Ces vérifications manuelles complètent les tests automatisés ; elles ne constituent pas une certification WCAG.
