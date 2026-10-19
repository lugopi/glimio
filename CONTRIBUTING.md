# Contribuer à Glimio

Merci de contribuer. Glimio est encore en développement ; les interfaces et les formats de configuration peuvent évoluer entre versions `0.x`.

## Avant une pull request

1. Décris le problème et le changement visible/utilisateur.
2. Ajoute des tests pour tout comportement modifié.
3. Lance `python -m pytest -q src/tests` depuis la racine.
4. Pour tout changement Angular, depuis `src/web/frontend`, exécute `npm ci`, `npm run typecheck`, `npm test` et `npm run build`.
5. Ajoute des tests qui protègent le comportement observable : règles métier, réponses API, import/normalisation audio, persistance, pagination, navigation et licences. Évite les snapshots qui figent des détails de CSS ou des métadonnées SVG sans impact utilisateur.
6. Les composants Angular séparent logique, template et styles. Utilise les utilitaires Tailwind 4 via `@reference`/`@apply` et `src/styles/tailwind.css` ; conserve les règles réellement partagées dans `src/styles/components.scss`. Suis aussi les conventions et commandes de [`docs/ANGULAR_22_MIGRATION.md`](docs/ANGULAR_22_MIGRATION.md).
7. N'ajoute pas de poids IA, d'exécutables, de captures audio utilisateur, de données de séance ou de secrets dans un commit.
8. Mets à jour `CHANGELOG.md` et incrémente la version `0.x` dans `pyproject.toml`, `src/web/app.py` et `src/web/frontend/package.json` quand c'est pertinent.

## Modèles et dépendances

Documente la source, la version et la licence de toute dépendance ou tout modèle ajouté. Ne considère pas que la licence de sherpa-onnx, whisper.cpp, llama.cpp ou de Glimio couvre automatiquement les poids d'un modèle tiers. Voir [docs/MODELS.md](docs/MODELS.md).

## Données et sécurité

Glimio est conçu pour un usage local et ne fournit pas d'authentification web. Ne partage pas de séances ou de transcriptions réelles dans des tickets publics sans retirer les données sensibles. Signale les vulnérabilités potentielles en privé au mainteneur avant publication d'un correctif.
