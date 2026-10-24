# Guide du frontend

## Architecture

L’interface servie à `/` est l’application Angular 22. FastAPI fournit les routes `/api/*` et sert le build SPA depuis `dist/glimio-web-ui` à la racine du dépôt. Un import de `web.app` depuis les tests Python ne doit pas installer les dépendances ni lancer npm.

Les sources Angular se trouvent dans `src/web/frontend/src/app`. Les pages sont regroupées par fonctionnalité et les éléments partagés dans `src/web/frontend/src/app/shared`. Les composants gardent leur logique, leur template et leurs styles dans des fichiers séparés (`.ts`, `.html`, `.scss`).

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
- Préférer les utilitaires Tailwind standards. Ajouter une règle CSS spécifique seulement quand aucune utilité standard ne couvre le besoin (par exemple une valeur liée à un jeton dynamique, un état complexe ou un sélecteur structurel). Éviter les variantes personnalisées et les doublons pour un style ponctuel.
- Garder `src/web/frontend/src/styles/components.scss` pour les styles réellement partagés entre plusieurs pages ou composants. Les styles propres à une page restent dans son SCSS.
- Réutiliser les composants partagés (icônes, pagination, champs communs) au lieu de créer une variante locale équivalente.
- Conserver les associations label/champ, le focus clavier visible et les noms accessibles. Masquer un champ conditionnel quand son option parente est inactive ; le désactiver seulement quand il reste pertinent mais temporairement indisponible.
- Le budget `anyComponentStyle` conserve un avertissement à 12 kB et une erreur à 20 kB. Si une page approche du seuil, extraire les blocs fonctionnels cohérents dans des composants autonomes réutilisables avec leurs propres styles, plutôt que de relever le budget ou de déplacer des styles propres à une page dans la feuille globale.

## Vérification de l’interface

Après compilation, vérifier les parcours modifiés au clavier et dans les thèmes concernés. Pour une revue responsive, couvrir 320, 375, 768, 1024 et 1440 px ainsi que le zoom à 200 % et 400 %. Ces vérifications manuelles complètent les tests automatisés ; elles ne constituent pas une certification WCAG.
