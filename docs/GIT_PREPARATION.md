# Préparation Git et publication

Ce document décrit les règles de propreté du dépôt Glimio : ce qui doit être
poussé, ce qui ne doit **jamais** l'être, et comment vérifier avant une publication.

## Ce qui vit hors du dépôt (ignoré par `.gitignore`)

- **Build du front Angular** : `<racine>/dist/` (généré par `npm run build` ou
  automatiquement par `python -m web`), `src/web/frontend/dist/`, cache `.angular/`,
  `node_modules/`. Le dossier legacy `src/web/static/` n'existe plus et ne doit
  jamais être recréé.
- **Python** : `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, œufs et wheels.
- **Données utilisateur** : `/seances/`, `.glimio/`, bases `*.sqlite3` / `*.db`,
  captures audio `*.wav` / `*.mp3` / `*.mp4`.
- **Poids et binaires** : `/models/`, `/bin/`, `*.gguf`, `*.onnx`, `*.bin`,
  `*.exe`, `*.dll`.
- **Secrets** : `.env`, `.env.*`, tout jeton ou clé.

Ne forcez jamais un fichier ignoré avec `git add -f` ; si un artefact semble
légitimement nécessaire au paquet, corrigez le build (`pyproject.toml`,
`angular.json`) plutôt que le dépôt.

## Vérifier la propreté de l'index

```bash
git ls-files | grep -E "node_modules|__pycache__|^dist/|src/web/static"   # doit être vide
git check-ignore -v dist/glimio-web-ui/index.html                          # doit correspondre à /dist/
```

## Avant une release `0.x`

1. Version alignée dans `pyproject.toml`, `src/seance/__init__.py`,
   `src/web/app.py`, `src/web/frontend/package.json`, la racine de
   `src/web/frontend/package-lock.json` et `CHANGELOG.md`.
2. Build complet vérifié depuis zéro : supprimer `dist/` puis
   `python -m web` (le build Angular se relance automatiquement) et ouvrir
   http://127.0.0.1:8765.
3. `CONTRIBUTING.md`, `SECURITY.md`, `docs/MODELS.md`, `docs/LICENSING.md`,
   `LICENSE` et `NOTICE` présents et à jour (licence AGPL-3.0-or-later,
   licences des modèles documentées séparément).
