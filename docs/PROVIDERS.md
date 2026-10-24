# Utiliser les providers Glimio

Glimio sépare le catalogue des providers de leurs dépendances lourdes. Les éditions précompilées CLI et Web n'embarquent pas SpeechBrain, PyTorch ou `sherpa-onnx` par défaut : le téléchargement initial reste léger et chaque provider Python peut être installé à la demande. Les modèles IA et les exécutables natifs sont toujours gérés séparément.

## CLI autonome

La CLI couvre aussi la bibliothèque, les artefacts, les préférences et la recherche ; voir [`CLI.md`](CLI.md). Les commandes de provider restent accessibles sans démarrer l'interface Web :

```console
glimio --help
glimio providers --help
glimio providers list
glimio providers info sherpa-onnx
glimio providers install sherpa-onnx
glimio providers doctor
```

- `providers list` affiche la disponibilité des providers et les ressources qui manquent localement.
- `providers info ID` affiche l'aide propre au provider : description, options, dépendances, modèles, binaires et documentation.
- `providers install ID` installe uniquement les dépendances Python déclarées dans les métadonnées sûres du catalogue.
- `providers doctor` effectue le diagnostic local ; `--json` sur `list` ou `doctor` produit des données lisibles par script.

Utilise `glimio providers list` pour copier un identifiant exact. Les identifiants d'installation sont limités aux providers inclus au catalogue ; une commande ne peut pas installer un paquet arbitraire passé par l'utilisateur.

## Runtime Python des éditions précompilées

Sur Windows x64 et Linux x86_64, la première commande `providers install ID` :

1. télécharge un runtime CPython autonome dans le dossier de données Glimio ;
2. vérifie son empreinte SHA-256 épinglée dans `seance/provider_runtime.py` ;
3. installe les paquets autorisés du provider dans le `site-packages` de ce runtime isolé ;
4. enregistre les chemins des bibliothèques natives pour qu'ils soient restaurés au démarrage suivant.

Le runtime isolé des providers utilise volontairement CPython 3.12.15 depuis les archives [python-build-standalone](https://github.com/astral-sh/python-build-standalone/releases) : il est distinct du Python 3.14.9 utilisé pour construire et tester Glimio, et garde une base de wheels compatible avec les providers ML optionnels. Glimio épingle la version du runtime et vérifie l’empreinte avant extraction. Les archives incluent leurs propres composants et notices de licence. Le runtime et les paquets installés sont conservés sous le dossier de données utilisateur : `%LOCALAPPDATA%\Glimio\Data\provider-runtime` sur Windows et `$XDG_DATA_HOME/Glimio/Data/provider-runtime` sous Linux (ou `~/.local/share/Glimio/Data/provider-runtime` lorsque `XDG_DATA_HOME` n'est pas défini). Ils ne sont pas écrits dans le répertoire de l'exécutable et ne remplacent pas le Python système. Redémarre Glimio après l'installation d'un provider Python pour charger ses modules natifs dans le processus principal.

La première installation nécessite Internet et le runtime seul représente un téléchargement de quelques dizaines de mégaoctets. Les roues SpeechBrain/PyTorch peuvent être beaucoup plus volumineuses. Glimio ne télécharge pas automatiquement les modèles ou les binaires tiers et n'installe pas de paquets dont les noms ne viennent pas du catalogue.

Les éditions source utilisent l'environnement Python actif au lieu de télécharger un second runtime. Les extras de développement restent facultatifs : `python -m pip install -e '.[diarization]'` pour `sherpa-onnx` et ses intégrations ou `python -m pip install -e '.[separation]'` pour SpeechBrain.

## Installer le provider et préparer ses ressources

### Diarisation avec sherpa-onnx

```console
glimio providers info sherpa-onnx
glimio providers install sherpa-onnx
```

Télécharge ensuite un modèle de segmentation et un modèle d'embeddings compatibles, puis configure leurs chemins dans Paramètres ou les options CLI `--segmentation-model` et `--embedding-model`. L'installation de `sherpa-onnx` n'inclut pas les modèles ONNX.

### Identité vocale avec SpeechBrain ECAPA

```console
glimio providers info speechbrain-ecapa
glimio providers install speechbrain-ecapa
```

Télécharge les fichiers du modèle ECAPA indiqués dans l'aide du provider et configure son dossier avec `--ecapa-model-dir` ou dans le fichier d'options JSON décrit ci-dessous. La sélection d'un périphérique CUDA nécessite un PyTorch compatible avec le pilote et le runtime du système ; en cas de doute, commence par le CPU.

### Séparation des voix avec SpeechBrain SepFormer

SepFormer dépend aussi du provider d'embeddings ECAPA :

```console
glimio providers info speechbrain-sepformer
glimio providers install speechbrain-sepformer
```

Installe également `speechbrain-ecapa`, télécharge le modèle SepFormer référencé dans l'aide du provider et vérifie que les deux modèles sont configurés. Le modèle générique fourni par SpeechBrain a été entraîné sur des mélanges propres de deux voix anglaises ; les résultats peuvent varier fortement sur les réunions réelles et le français.

## Options propres aux providers depuis le CLI

Les options proposées par chaque provider apparaissent avec `glimio providers info ID`. Pour les options autres que les raccourcis CLI documentés dans `glimio --help`, passe un fichier JSON dont les clés sont les identifiants des providers et les valeurs des objets d'options :

```json
{
  "speechbrain-ecapa": {
    "model_dir": "models/speaker-embedding/spkrec-ecapa-voxceleb"
  },
  "speechbrain-sepformer": {
    "model_dir": "models/source-separation/sepformer-wsj02mix",
    "device": "cpu",
    "chunk_seconds": 30
  }
}
```

Enregistre-le par exemple dans `providers.json` et passe `--provider-options-file providers.json` à `glimio process`, `glimio transcribe` ou `glimio summarize`. Les chemins relatifs sont résolus à partir du dossier de données/projet de Glimio. Des raccourcis sont également disponibles : `--ecapa-model-dir`, `--sepformer-model-dir`, `--provider-device` et `--sepformer-chunk-seconds`.

Les options de traitement disponibles peuvent dépendre du provider. Leur liste déclarée est présentée par `providers info ID`; les modèles et binaires peuvent demander une configuration distincte même lorsque le runtime Python indique que le paquet est installé.

## Maintenance du catalogue

Les paquets d'installation viennent uniquement de `ProviderInfo.python_install_packages`, jamais d'une requête API/CLI libre. Pour ajouter un provider Python :

1. déclarer ses paquets strictement nécessaires et une note d'installation claire dans ses métadonnées ;
2. ajouter les exigences de modèle/binaire et les liens de provenance/licence ;
3. tester la commande en environnement source et l'environnement Python auxiliaire gelé ;
4. vérifier le CLI empaqueté (`--help`, `providers --help`, `providers list`, `providers info ID`, puis une installation réelle sur une machine de test) sur chaque OS pris en charge.

Le runtime auxiliaire n'est actuellement publié que pour Windows x64 et Linux x86_64. Les autres systèmes doivent utiliser une installation depuis les sources ou configurer les dépendances selon les instructions officielles du provider.
