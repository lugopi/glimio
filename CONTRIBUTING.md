# Contribuer à Glimio

Merci de contribuer. Glimio est encore en développement ; les interfaces et les formats de configuration peuvent évoluer entre versions `0.x`.

## Avant une pull request

1. Décris le problème et le changement visible/utilisateur.
2. Ajoute des tests pour tout comportement modifié.
3. Lance `python -m pytest -q src/tests` depuis la racine.
4. Pour tout changement Angular, depuis `src/web/frontend`, exécute `npm ci`, `npm run typecheck`, `npm test` et `npm run build`.
5. Ajoute des tests qui protègent le comportement observable : règles métier, réponses API, import/normalisation audio, persistance, pagination, navigation et licences. Évite les snapshots qui figent des détails de CSS ou des métadonnées SVG sans impact utilisateur.
   Range-les dans `src/tests/unit`, `src/tests/integration` ou `src/tests/regression` selon ce qu’ils vérifient. Les tests de composants Angular restent dans le frontend et se lancent avec `npm test`.
6. Les composants Angular séparent logique, template et styles. Utilise Tailwind CSS 4 via `@reference`/`@apply` et privilégie ses utilitaires standards. Suis les conventions et commandes de [`docs/FRONTEND.md`](docs/FRONTEND.md).
7. N'ajoute pas de poids IA, d'exécutables, de captures audio utilisateur, de données de séance ou de secrets dans un commit.
8. Pour une release, suis [`docs/RELEASING.md`](docs/RELEASING.md) et garde la même version dans `pyproject.toml`, `src/seance/__init__.py`, `src/web/app.py`, `src/web/frontend/package.json` et la racine de `src/web/frontend/package-lock.json`.

## Modèles et dépendances

Documente la source, la version et la licence de toute dépendance ou tout modèle ajouté. Ne considère pas que la licence de sherpa-onnx, whisper.cpp, llama.cpp ou de Glimio couvre automatiquement les poids d'un modèle tiers. Voir [docs/MODELS.md](docs/MODELS.md).

## Données et sécurité

Glimio est conçu pour un usage local et ne fournit pas d'authentification web. Ne partage pas de séances ou de transcriptions réelles dans des tickets publics sans retirer les données sensibles. Signale les vulnérabilités potentielles en privé au mainteneur avant publication d'un correctif.
