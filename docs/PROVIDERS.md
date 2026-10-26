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

Le provider `ffmpeg` déclare deux options : `ffmpeg` et `ffprobe`. Laissez les valeurs `ffmpeg` et `ffprobe` pour les détecter sur le `PATH` (ffprobe est d'abord cherché à côté de l'exécutable FFmpeg). Si vous installez une distribution portable, configurez les deux chemins complets, par exemple :

```json
{
  "ffmpeg": {
    "ffmpeg": "C:/tools/ffmpeg/bin/ffmpeg.exe",
    "ffprobe": "C:/tools/ffmpeg/bin/ffprobe.exe"
  }
}
```

Un ffprobe explicitement configuré mais introuvable est signalé comme ressource manquante au lieu de retomber silencieusement sur un autre binaire du `PATH`.

## Providers média (import et découpage)

L'import des fichiers et le découpage audio passent par un provider média remplaçable. Deux identifiants sont disponibles :

| Provider | Exécution | Capacités | Options | Limite principale |
|---|---|---|---|---|
| `ffmpeg` (défaut) | exécutable système | `audio-video-import`, `audio-chunking` | `ffmpeg`, `ffprobe` | FFmpeg et ffprobe doivent être résolus ; ffprobe manquant bloque l'import. |
| `native` | intégré (`embedded`) | `wav-pcm16`, `audio-chunking` | aucune | N'accepte que les WAV PCM 16 bits à 16 kHz, sans décodage d'un autre conteneur ni rééchantillonnage. |

- `ffmpeg` décode les formats audio/vidéo pris en charge par le binaire configuré, préserve chaque flux et chaque canal, puis écrit des pistes mono PCM 16 bits à 16 kHz. Il sert aussi au découpage des longues séances.
- `native` n'appelle aucun exécutable : il lit et écrit des WAV PCM 16 bits à 16 kHz avec la bibliothèque standard. À l'import, un fichier MP3, M4A, MP4 ou un WAV 8 kHz/24 bits est refusé avec un message qui demande de le convertir ou de choisir un autre provider média. Il extrait un canal par sélection directe des échantillons et moyenne les canaux (downmix) en conservant la saturation PCM16.

La sélection se fait par `media_provider` (API/paramètres Web, persisté avec les préférences) ou par `--media-provider` dans le CLI. Les options du provider restent indexées par identifiant dans `provider_options` ; pour `ffmpeg`, `--ffmpeg` et `--ffprobe` restent des alias des clés `ffmpeg`/`ffprobe`. `glimio providers list` et `GET /api/providers` rapportent la disponibilité réelle du provider choisi : `native` est prêt sans ressource externe, `ffmpeg` manque tant que les deux binaires ne sont pas résolus.

Les providers qui convertissent eux-mêmes de l'audio gardent leurs propres dépendances : `ffmpeg-denoise`, `deepfilternet` et `speechbrain-sepformer` déclarent toujours `requires=("ffmpeg",)` (SepFormer y ajoute `speechbrain-ecapa`). Sélectionner `native` pour l'import ne les dispense donc pas de FFmpeg si l'amélioration, la séparation ou le rapprochement des voix est activé.

Un provider requis par un autre reste configurable dans Paramètres même lorsqu'il n'est pas le provider actif. La section « Dépendances des providers » liste ces dépendances et affiche leurs options, leur disponibilité et les providers qui les requièrent. Par exemple, avec `native` comme provider média et `ffmpeg-denoise` comme amélioration, les options `ffmpeg` et `ffprobe` restent accessibles : un FFmpeg installé hors du `PATH` peut être configuré sans changer de provider média.

## Maintenance du catalogue

Les paquets d'installation viennent uniquement de `ProviderInfo.python_install_packages`, jamais d'une requête API/CLI libre. Pour ajouter un provider Python :

1. déclarer ses paquets strictement nécessaires et une note d'installation claire dans ses métadonnées ;
2. ajouter les exigences de modèle/binaire et les liens de provenance/licence ;
3. tester la commande en environnement source et l'environnement Python auxiliaire gelé ;
4. vérifier le CLI empaqueté (`--help`, `providers --help`, `providers list`, `providers info ID`, puis une installation réelle sur une machine de test) sur chaque OS pris en charge.

Le runtime auxiliaire n'est actuellement publié que pour Windows x64 et Linux x86_64. Les autres systèmes doivent utiliser une installation depuis les sources ou configurer les dépendances selon les instructions officielles du provider.


## Providers extensibles (plugins Python)

Les providers installés avec un paquet Python peuvent être ajoutés au catalogue sans modifier les fichiers de Glimio. Le paquet tiers déclare un `entry point` dans son propre `pyproject.toml` :

```toml
[project.entry-points."glimio.providers"]
mon-moteur = "mon_paquet.glimio:PLUGIN"
```

L'objet référencé est un `ProviderPlugin` contenant les métadonnées neutres, une fabrique et, facultativement, une fonction de diagnostic :

```python
from pathlib import Path
from seance.providers import ProviderInfo, ProviderOption, SpeakerTurn
from seance.providers.plugins import ProviderPlugin

INFO = ProviderInfo(
    id="mon-moteur", name="Mon moteur", task="diarization",
    description="Diarisation locale avec ma bibliothèque préférée.",
    execution="embedded",
    capabilities=("local", "speaker-segmentation"),
    options=(ProviderOption(
        key="model_path", label="Modèle", type="path",
        default="models/mon-modele.onnx", required=True,
    ),),
)

class MonMoteur:
    info = INFO
    sample_rate = 16000

    def __init__(self, options):
        # Charger la bibliothèque et ses modèles ici, jamais à l'import du paquet.
        self.model_path = options["model_path"]

    def process(self, audio) -> list[SpeakerTurn]:
        # Convertir le résultat de la bibliothèque vers le contrat neutre Glimio.
        return []

def check_readiness(options, project_root: Path):
    model = Path(options.get("model_path", "models/mon-modele.onnx")).expanduser()
    if not model.is_absolute():
        model = project_root / model
    missing = () if model.is_file() else (str(model),)
    return missing, {"model_path": str(model)}

PLUGIN = ProviderPlugin(info=INFO, factory=MonMoteur, readiness=check_readiness)
```

Remplace les valeurs de démonstration par l'implémentation réelle. Les métadonnées doivent utiliser un identifiant stable et unique, déclarer les bibliothèques/ressources nécessaires, et ne jamais importer FastAPI ou du code Angular. Le plugin ne doit pas télécharger des modèles ni initialiser un runtime lourd pendant l'import. `check_readiness(options, project_root)` retourne `(ressources_manquantes, détails_json)` sans lancer de traitement ni téléchargement.

Le contrat de la fabrique dépend de la tâche :

| Tâche (`ProviderInfo.task`) | Signature attendue de la fabrique | Contrat de l'instance |
|---|---|---|
| `generation` | `(executable, model, working_directory, *, cancel_event, on_process, timeout_seconds, options)` | provider de génération, avec `info` |
| `transcription` | `(executable, *, cancel_event, options)` | provider de transcription, avec `info` |
| `diarization` | `(options)` | `info`, `sample_rate`, `process(audio) -> list[SpeakerTurn]` |
| `media` | `(options)` | opérations du contrat `MediaToolchainProvider` |
| `enhancement` | `(options)` | `enhance(request)` |
| `separation` | `(options, embedding_provider)` | `separate(request)` |
| `speaker_embedding` | `(options)` | `embed(audio, sample_rate)` |

Pour `generation`, `transcription` et `diarization`, Glimio fournit actuellement les fabriques principales partagées par CLI et Web. Les tâches média/audio consomment leurs contrats dédiés. Les options `ProviderOption` sont rendues dynamiquement dans Angular et les valeurs sont persistées sous `provider_options["mon-moteur"]`; éviter de coder les options d'un moteur dans la CLI, l'API ou le frontend. Les chemins relatifs du diagnostic sont résolus à partir de `project_root`.

Les entry points sont du code exécutable installé dans l'environnement Python : n'installe que des distributions de confiance. Un plugin absent ou dont le chargement échoue est ignoré avec avertissement. Glimio ne promet pas de pouvoir désinstaller ou mettre à jour les dépendances d'un plugin tiers à travers l'installateur réservé au catalogue intégré ; utilise le gestionnaire de paquets Python pour gérer sa distribution.

### Bibliothèque et composants d'interface

Le plugin fournit les métadonnées de son moteur, pas de template HTML/Angular exécutable. Le composant générique `glimio-provider-options` construit les champs depuis `ProviderInfo.options`; il est donc possible de changer la bibliothèque sous-jacente du moteur, son modèle et ses réglages en installant/sélectionnant un autre provider, sans embarquer la bibliothèque dans le frontend. Le remplacement du framework UI global (Angular) n'est pas un provider de moteur : cela relève d'un changement d'architecture frontend distinct.
