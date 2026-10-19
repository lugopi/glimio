# Préparer une release Glimio

## Formats publiés

Chaque release Windows x64 fournit six fichiers : un installateur et une archive portable pour chacune de ces éditions :

- **CLI** : capture et traitement audio depuis la ligne de commande.
- **Web** : application locale dans le navigateur, avec le CLI.
- **Web avec diarisation** : édition Web et CLI avec `sherpa-onnx` inclus.

Les exécutables Whisper/llama.cpp, FFmpeg et les poids des modèles ne sont pas inclus. Ils ont des licences, variantes matérielles et conditions de téléchargement distinctes. Les chemins sont configurés dans Paramètres et les sources officielles sont décrites dans [`MODELS.md`](MODELS.md). Les données de l’édition empaquetée restent sous `%LOCALAPPDATA%\Glimio\Data`, séparées du dossier installé.

## Publier une version

1. Choisir une version `0.x.y` et la reporter de façon identique dans `pyproject.toml`, `src/seance/__init__.py`, `src/web/app.py`, `src/web/frontend/package.json` et le champ `version` racine de `src/web/frontend/package-lock.json`.
2. Mettre à jour `CHANGELOG.md`, puis committer et pousser les changements sur `main`.
3. Créer et pousser un tag annoté correspondant exactement à la version :

   ```powershell
   git tag -a v0.4.3 -m "Glimio 0.4.3"
   git push origin v0.4.3
   ```

4. Le workflow `Build and release` vérifie les versions, exécute les tests Python et Angular, construit les éditions et produit les installateurs et archives portables. Les fichiers sont d’abord publiés dans une **release brouillon** avec leurs sommes SHA-256.
5. Dans GitHub, vérifier les six fichiers, les notes générées et `SHA256SUMS.txt`, puis publier le brouillon.

Les workflows sont dans `.github/workflows/`. Les pull requests et les commits sur `main` exécutent le workflow CI. Une poussée de tag `vX.Y.Z` seule déclenche la préparation de release ; le workflow ne crée pas ni ne pousse le tag à ta place.

## Continuer le développement depuis les sources

Le paquet Windows ne modifie pas le parcours de développement du dépôt. Depuis la racine, l’installation éditable reste :

```powershell
python -m pip install -e ".[web,diarization]"
```

Le frontend continue à être développé et testé dans `src/web/frontend` avec `npm ci`, `npm run typecheck`, `npm test` et `npm run build`. Le démarrage depuis les sources peut reconstruire Angular si ses fichiers ont changé ; les exécutables de release, eux, servent le frontend Angular inclus et n’ont pas besoin de Node.js.
