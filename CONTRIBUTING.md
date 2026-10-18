# Contribuer à Glimio

Merci de contribuer. Glimio est encore en développement ; les interfaces et les formats de configuration peuvent évoluer entre versions `0.x`.

## Avant une pull request

1. Décris le problème et le changement visible/utilisateur.
2. Ajoute des tests pour tout comportement modifié.
3. Lance `python -m unittest discover -s src/tests -v` depuis la racine.
4. Vérifie les modules JavaScript modifiés avec `node --check <fichier.js>`.
5. L'interface est full Angular : le build (`npm run build` ou `python -m web`) produit `<racine>/dist/glimio-web-ui`, hors du code source et ignoré par git. N'y ajoute rien à la main et ne recrée jamais de dossier `src/web/static`.
6. Les chaînes d'interface vivent dans les templates/composants Angular (`src/web/frontend/src/`). Ne traduis pas le contenu utilisateur, les transcriptions ou les citations.
7. N'ajoute pas de poids IA, d'exécutables, de captures audio utilisateur, de données de séance ou de secrets dans un commit.
8. Mets à jour `CHANGELOG.md` et incrémente la version `0.x` dans `pyproject.toml`, `src/web/app.py` et `src/web/frontend/package.json` quand c'est pertinent.
9. Pour la migration Angular 22, suis `docs/ANGULAR_22_MIGRATION.md` et ne remplace pas la page d'entrée stable avant que les tests de parité, d'accessibilité et de non-régression soient tous passés.

## Modèles et dépendances

Documente la source, la version et la licence de toute dépendance ou tout modèle ajouté. Ne considère pas que la licence de sherpa-onnx, whisper.cpp, llama.cpp ou de Glimio couvre automatiquement les poids d'un modèle tiers. Voir [docs/MODELS.md](docs/MODELS.md).

## Données et sécurité

Glimio est conçu pour un usage local et ne fournit pas d'authentification web. Ne partage pas de séances ou de transcriptions réelles dans des tickets publics sans retirer les données sensibles. Signale les vulnérabilités potentielles en privé au mainteneur avant publication d'un correctif.
