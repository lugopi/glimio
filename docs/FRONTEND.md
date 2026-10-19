# Guide du frontend

## Architecture

L’interface servie à `/` est l’application Angular 22. FastAPI fournit les routes `/api/*` et sert le build SPA depuis `dist/glimio-web-ui` à la racine du dépôt. Un import de `web.app` depuis les tests Python ne doit pas installer les dépendances ni lancer npm.

Les sources Angular se trouvent dans `src/web/frontend/src/app`. Les pages sont regroupées par fonctionnalité et les éléments partagés dans `src/web/frontend/src/app/shared`. Les composants gardent leur logique, leur template et leurs styles dans des fichiers séparés (`.ts`, `.html`, `.scss`).

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
- Le budget `anyComponentStyle` est de 12 kB en avertissement et 20 kB en erreur. Avant de le relever, vérifier les règles répétées et les styles partagés qui peuvent être mutualisés.

## Vérification de l’interface

Après compilation, vérifier les parcours modifiés au clavier et dans les thèmes concernés. Pour une revue responsive, couvrir 320, 375, 768, 1024 et 1440 px ainsi que le zoom à 200 % et 400 %. Ces vérifications manuelles complètent les tests automatisés ; elles ne constituent pas une certification WCAG.
