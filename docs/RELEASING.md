# Préparer une release Glimio

## Artefacts publiés

Chaque release produit six artefacts applicatifs pour x64. Les archives Linux sont compilées sur Ubuntu 22.04 x86_64 et requièrent glibc 2.35 ou plus récent : ce ne sont pas des binaires universels pour toutes les distributions Linux.

- **Windows CLI** : archive portable `zip` et installateur `Setup.exe`.
- **Windows Web** : archive portable `zip` et installateur `Setup.exe`. Cette édition inclut aussi le CLI.
- **Linux CLI** : archive portable `tar.gz`.
- **Linux Web** : archive portable `tar.gz`. Cette édition inclut aussi le CLI.

Il n’existe plus d’édition séparée « Web avec diarisation ». Les artefacts CLI et Web restent légers : aucun provider Python optionnel lourd n’est embarqué par défaut. Dans les éditions précompilées, `glimio providers install ID` télécharge à la demande un runtime CPython autonome, vérifié par SHA-256, puis installe les paquets déclarés par le provider dans cet environnement isolé. Depuis les sources, les extras Python restent installables via pip (`.[diarization]`, `.[separation]`). Les fichiers de modèles ONNX et SpeechBrain, les exécutables Whisper/llama.cpp/FFmpeg et les modèles GGUF restent des ressources distinctes. Les licences et sources officielles sont documentées dans [`MODELS.md`](MODELS.md) et [`LICENSING.md`](LICENSING.md).

Les données des paquets Windows sont conservées sous `%LOCALAPPDATA%\Glimio\Data`. Sous Linux, elles sont stockées dans `$XDG_DATA_HOME/Glimio/Data` si `XDG_DATA_HOME` est défini, sinon `~/.local/share/Glimio/Data`. Les applications empaquetées n’ont pas besoin d’un environnement Python ni, pour l’édition Web, de Node.js installés sur la machine. Le runtime CPython auxiliaire n’est téléchargé dans ce dossier que lorsqu’un utilisateur installe son premier provider Python optionnel.

## Publier une version

1. Choisir une version `0.x.y` et la reporter de façon identique dans `pyproject.toml`, `src/seance/__init__.py`, `src/web/app.py`, `src/web/frontend/package.json` et le champ `version` racine de `src/web/frontend/package-lock.json`.
2. Mettre à jour `CHANGELOG.md`, puis committer et pousser les changements sur `main`.
3. Créer et pousser un tag annoté correspondant exactement à la version :

   ```powershell
   git tag -a v0.5.0 -m "Glimio 0.5.0"
   git push origin v0.5.0
   ```

4. Le workflow `Build and release` valide la correspondance du tag, des versions du projet et du changelog, exécute les tests Python et Angular, puis construit les paquets Windows x64 et Linux x86_64. Chaque release est d’abord publiée dans une **release brouillon**, accompagnée de `SHA256SUMS.txt`.
5. Dans GitHub, vérifier les six artefacts applicatifs, les notes issues de la section correspondante du changelog et les sommes SHA-256, puis publier le brouillon. Sur chaque système, vérifier également le CLI sans Web avec `glimio --help`, `glimio providers --help`, `glimio providers list`, puis tester une installation provider à la demande dans un environnement propre.

Les workflows sont dans `.github/workflows/`. La CI sépare les tests Python (Python 3.10 et 3.12) et les vérifications Angular en jobs indépendants. La préparation d’une release attend ces deux jobs avant de construire quatre variantes OS/édition : Windows CLI, Windows Web, Linux CLI et Linux Web. Le workflow compile Angular une fois et réutilise le build pour les deux paquets Web ; chaque paquet gelé est validé avec un test de démarrage ciblé. Une poussée de tag `vX.Y.Z` seule déclenche la préparation de release ; le workflow ne crée pas ni ne pousse le tag à ta place.

## Continuer le développement depuis les sources

Les paquets Windows et Linux ne modifient pas le parcours de développement du dépôt. Depuis la racine, l’installation éditable Web avec diarisation reste :

```powershell
python -m pip install -e ".[web,diarization]"
```

Le frontend continue à être développé et testé dans `src/web/frontend` avec `npm ci`, `npm run typecheck`, `npm test` et `npm run build`. Le démarrage depuis les sources peut reconstruire Angular si ses fichiers ont changé ; les exécutables de release servent le frontend Angular inclus et n’ont pas besoin de Node.js. Pour une installation source sans diarisation, retire simplement `diarization` de la liste d’extras (`python -m pip install -e ".[web]"`).
