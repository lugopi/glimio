# Changelog

## Unreleased

- Les bordures d’état réutilisées et le fond de succès doux sont désormais exposés comme utilitaires (`border-success-border`, `border-danger-border`, `border-accent-border`, `border-warning-border`, `bg-success-soft`) ; les composants utilisent `@apply` plutôt que de répéter `color-mix()`. Les espacements et couleurs simples de la bibliothèque et de la recherche ont aussi été convertis en utilitaires.
- Styles du bandeau d'enregistrement : rail d'état via `@apply border-l-3 border-l-danger`, couleurs de fond et halos fournis par des jetons Tailwind, et animation de pulse déclarée comme utilitaire `animate-recording-pulse`. Les règles standard ne restent plus en CSS brut lorsqu'un utilitaire Tailwind existe.
- `AGENTS.md` et `docs/FRONTEND.md` exigent maintenant `@apply` pour les propriétés standard couvertes par Tailwind ; couleurs composées, halos et animations sémantiques sont exposés comme jetons de thème.

- Correctif Tailwind 4 : déclaration effective des utilitaires typographiques sémantiques `text-compact` (13 px), `text-caption` (11 px) et `text-micro` (10 px) dans les deux sources de thème nécessaires à `@apply` et à la génération globale.
- `AGENTS.md` et `docs/FRONTEND.md` précisent qu’un utilitaire sémantique utilisé par `@apply` doit être déclaré dans le thème Tailwind et vérifié par compilation.
- Audit des valeurs arbitraires Tailwind : suppression ou remplacement de nombreuses classes `-[…]` redondantes par l’échelle existante et des utilitaires cohérents ; les grilles structurelles et dimensions de la coque sont exprimées avec des propriétés explicites et des jetons partagés. Les rares tailles précises sont gardées seulement lorsque leur rôle de mise en page le justifie. Convention ajoutée dans `AGENTS.md` et `docs/FRONTEND.md` pour prévenir la réintroduction de valeurs arbitraires inutiles.
- Correctif des menus d’action : `modern-normalize.scss` applique `summary { display: list-item; }` hors des couches Tailwind ; ajout d’un override non classé `summary.session-actions-toggle { display: grid; }` pour préserver le centrage de l’icône au lieu de laisser le reset écraser `@layer components`.
- Audit SCSS frontend — migration des propriétés standards vers les utilitaires Tailwind `@apply` et les jetons du projet dans les styles partagés (navigation, champs et actions de séance, statuts/jobs, diarisation, panneaux de réglages et contenu Markdown). Les dimensions et alignements sont lisibles et cohérents, les styles de burger/actions restent partagés. Les valeurs composées nommées du bandeau (fonds, halos et pulse) sont exposées en jetons Tailwind et consommées avec `@apply`; le CSS direct est réservé aux détails structurels et effets réellement sans utilitaire fidèle, comme certaines grilles, ombres de surface et sélecteurs conditionnels. Suppression du doublon global de `.sr-only` au profit de l’utilitaire Tailwind généré. Aucun changement des budgets Angular.
- UI compacte et cohérente : menus d’actions partagés (40 px sur ordinateur, 44 px sur mobile) avec icône de 20 px uniforme ; tous les toggles burger utilisent maintenant la même boîte d’icône de 20 px, centrée dans le bouton, y compris le menu principal mobile, la bibliothèque, la recherche et les pistes audio. Les surcharges locales bibliothèque/recherche/pistes audio ont été retirées. Les boutons courants, champs, badges d’état et statuts des providers partagent désormais des dimensions plus cohérentes, avec des espacements verticaux réduits. Le budget Angular `anyComponentStyle` reste inchangé à 12 kB en avertissement et 20 kB en erreur ; le SCSS de la bibliothèque est allégé pour revenir sous le seuil. Les panneaux Bibliothèque et Détail passent à 16 px de marge intérieure sur petit écran.
- Formats de résumé enrichis : ajout des catégories génériques `narrative` (récit, fiction, livre audio, roleplay), `dialogue` (conversation, interview, débat) et `learning` (cours, tutoriel, exposé). Les formats de suivi d’avancement, d’analyse technique, de procès-verbal et d’idéation sont conservés. CLI et Web partagent maintenant les mêmes identifiants de format ; les listes Enregistrement/Bibliothèque affichent une courte explication de chaque choix.
- Compréhension des locuteurs : les prompts de classification, d’analyse, de rédaction, de synthèse globale et de relecture précisent que `Speaker N` et les horodatages sont des marqueurs structurels, tandis que Micro/Audio Windows sont des pistes source. Le modèle ne doit associer un nom à une voix que si le contenu établit le lien sans ambiguïté, et ne doit pas confondre une voix d’acteur/narrateur avec un personnage de fiction.
- Résumés — choix automatique du format plus conservateur : les formats spécialisés nécessitent une confiance élevée et deux extraits exacts vérifiables dans la transcription originale. Si la classification est ambiguë, non structurée ou non étayée, Glimio choisit la synthèse générale. Le diagnostic consigne le motif de décision et les preuves vérifiées dans `analysis/format_selection.txt`. Le prompt distingue plus explicitement le suivi d’avancement, le brainstorming, le procès-verbal formel et l’activité technique.

- Bibliothèque — actions du résumé regroupées dans un menu compact (modifier, exporter Markdown, imprimer/PDF), avec une cible de traduction et un sélecteur séparé entre la version originale et les variantes traduites.
- Langue des résumés — ajout du choix `auto` (suivre la langue dominante de la transcription) ou d’une langue explicite sur Enregistrement et dans les options de chaque séance. En mode `auto`, une détection lexicale prudente fixe la langue des prompts, titres et étapes de génération lorsque la source est claire ; sinon, le modèle reçoit la consigne de suivre directement la transcription. Le choix appliqué est tracé dans `analysis/summary_language_selection.txt`, sans modèle ni dépendance supplémentaires.
- Traduction après génération — nouveau job `translate-summary` réutilisant le provider LLM sélectionné sans relancer transcription/analyse ; les traductions sont enregistrées sous `summary/translations/<langue>.md`, sans écraser le résumé original ni changer les préférences de génération. Le contrôle de sortie accepte également les traductions complètes de résumés courts.
- Correctif frontend — typage distinct des options de traduction, excluant explicitement `auto` du type cible pour éviter les erreurs TypeScript au lancement et au suivi des jobs de traduction.

- Paramètres — affichage compact des providers prêts : leurs options restent accessibles dans un panneau repliable et l’installation, les dépendances Python et les ressources documentaires sont regroupées sous « Installation et documentation ». Les providers à configurer gardent ces éléments ouverts ; aucun contrôle ni lien n’est supprimé.
- Résumés — choix automatique du format : la classification s’appuie désormais sur des extraits de la transcription originale (début, milieu et fin), plutôt que sur les notes d’analyse reformulées. Les consignes distinguent le but de l’échange du simple vocabulaire technique, et la sélection est inscrite avec sa source dans `analysis/format_selection.txt`.
- Résumés — relecture finale : les rapports assemblés en plusieurs blocs ne sautent plus systématiquement la relecture complète. Elle est tentée si le document tient avec une marge suffisante dans le contexte ; si la marge est insuffisante, le brouillon est conservé sans réécriture à risque.
- Paramètres : les providers requis par un autre provider sélectionné (par exemple `ffmpeg` pour `ffmpeg-denoise`) restent configurables même s’ils ne sont pas le moteur actif, avec leur état de disponibilité et les providers qui les requièrent. Le message d’erreur de lancement de FFmpeg renvoie vers le provider FFmpeg au lieu d’un chemin générique.
- Providers média : l’import et le découpage audio passent par un contrat `MediaToolchainProvider` remplaçable, avec un adaptateur `ffmpeg` (FFmpeg/ffprobe, valeurs par défaut) et un adaptateur `native` (module `wave` et `numpy`, WAV PCM 16 bits à 16 kHz, aucun exécutable). La préférence `media_provider` est validée côté API, propagée à l’import Web et aux pipelines, et le CLI expose `--media-provider` ; `--ffmpeg`/`--ffprobe` restent des alias des options du provider `ffmpeg`. Le contrôle préalable d’import vérifie le provider sélectionné au lieu d’exiger FFmpeg dans tous les cas. Documentation mise à jour (providers, CLI, pipeline audio, architecture, README).
- FFmpeg/ffprobe : ajout d’une option `ffprobe` à côté de `ffmpeg` (paramètres du provider et `--ffprobe`), résolution unifiée « valeur explicite, puis voisin de FFmpeg, puis `PATH` », et propagation du chemin configuré à l’import Web, au CLI et aux pipelines. Le chemin configuré n’est plus ignoré à l’import.
- Import Web : un contrôle préalable côté interface empêche désormais d’envoyer un gros fichier quand ffmpeg/ffprobe manque, et l’API refuse l’import avec un message actionnable (HTTP 409) sans écrire de temporaire. Les fichiers temporaires sont supprimés si l’import échoue ou est annulé.
- Traitements sans FFmpeg : les sessions WAV PCM plus longues que 15 minutes sont découpées nativement lorsque FFmpeg est indisponible et que l’amélioration/séparation sont désactivées ; les erreurs de lancement de FFmpeg rappellent l’installation, le chemin configurable ou le choix « Aucune amélioration ». Les Namespaces reconstruits par `summarize` propagent les providers audio et ffprobe au lieu de retomber sur `ffmpeg-denoise`.
- CLI : `glimio import` et les autres commandes affichent une erreur lisible (sans traceback) lorsque ffmpeg/ffprobe ou un fichier requis est introuvable.
- Accessibilité : les messages d’erreur techniques des traitements ne sont plus traduits par la réécriture DOM (`data-no-translate`).
- Import Web : l’écriture des fichiers reçus est déportée hors de la boucle d’événements et les fichiers temporaires sont supprimés si l’upload ou la mise en file échoue, afin de ne pas bloquer le flux SSE ni laisser de résidus.
- Métadonnées de séance : la couche Web délègue désormais la lecture, l’écriture atomique et le marquage des artefacts obsolètes à `seance.core.sessions` au lieu de dupliquer la persistance ; les codes HTTP existants sont conservés.
- Accessibilité : les titres de séance saisis par l’utilisateur ne sont plus traduits par la réécriture DOM (`data-no-translate`), le sélecteur de séances utilise un groupe de boutons au lieu d’un motif `listbox` incomplet, et la version de référence de `ACCESSIBILITY_AUDIT.md` est corrigée.
- Tests : ajout d’une couverture unitaire des métadonnées de séance (aller-retour, repli legacy, erreurs), du nettoyage des uploads, de la résolution ffmpeg/ffprobe, du repli WAV et de la propagation des providers audio ; le nettoyage des dossiers temporaires Windows est fiabilisé pour éviter les échecs intermittents de `TemporaryDirectory`.
- CI/CD : remplacement du Python `3.12.15` demandé directement sur le runner Windows (version de sécurité sans installateur Windows disponible via `setup-python`) par Python `3.14.9`, la toolchain Python corrective actuellement ciblée par le projet. La CI couvre Python `3.12` et `3.14.9`.
- Outillage Angular : alignement de `.nvmrc` et `mise.toml` sur Node.js `26.12.1`, compatible avec Angular 22 ; mise à jour des actions GitHub vers les versions Node 24 récentes et restriction de `engines.node` aux branches explicitement supportées par Angular 22.
- Le runtime CPython `3.12.15` vérifié par SHA-256 reste réservé à l’installation à la demande des providers : il provient de `python-build-standalone`, et n’est pas la version utilisée par `actions/setup-python` pour construire les exécutables.

- Nettoyage du packaging Python : suppression du relais `web.project_paths` et de son dossier vide `web.services`, accès direct au module partagé `seance.project_paths`, renommage du résolveur de dossiers en `seance.session_paths` pour le distinguer des services métier `seance.core.sessions`, et retrait des références de package-data vers l’ancienne UI statique absente du dépôt.

- Correctif du traitement automatique après enregistrement : le job de capture est terminé de façon atomique lors du transfert vers la file de traitement, afin qu’il ne bloque pas lui-même le job de transcription ou de traitement complet. La protection contre les traitements concurrents reste active.

## 0.5.0 — recherche intelligente, providers audio et composants partagés — 2026-10-24

- Recherche intelligente par séance : ajout du ciblage de séances existantes via `@` et le sélecteur de séances, pour limiter la recherche au périmètre souhaité.
- Sélection des extraits pertinents : possibilité d’inclure ou d’exclure des extraits, de conserver les extraits exclus pour les restaurer, puis de confirmer explicitement avant de régénérer le résumé.
- Régénération ciblée des résumés : nouvel endpoint permettant de recalculer le résumé à partir des extraits retenus sans relancer la récupération documentaire ; renumérotation des références de sources selon les extraits conservés.
- Actions de recherche : ajout des exports et d’un menu d’actions pour les résumés de la recherche intelligente.
- Listes réutilisables : création de `SelectableListComponent` pour partager le conteneur de liste, les séparateurs, les états de sélection et le highlight vertical entre la bibliothèque, le sélecteur de séances et les extraits pertinents.
- États de sélection harmonisés : le highlight reste visible au survol et suit les coins arrondis du conteneur de liste, y compris aux extrémités ; les extraits exclus restent visibles mais sont distingués visuellement.
- Lecteur audio : correction de l’emplacement du menu d’actions des pistes afin qu’il reste à droite et ne soit pas coupé par le conteneur du lecteur.
- Styles Angular : extraction de styles réellement partagés et recours prioritaire aux utilitaires Tailwind avec `@apply`, y compris dans les media queries lorsque cela convient. Le budget d’avertissement des styles de composants reste à 12 kB (erreur à 20 kB).
- Packaging et CI/CD : suppression de la variante séparée « Web avec diarisation » ; les éditions CLI et Web restent légères et installent les dépendances Python de chaque provider à la demande dans un runtime isolé. Les modèles restent séparés. Le pipeline publie des éditions Windows x64 (installateur et archive portable) et Linux x86_64 (`tar.gz`), après tests Python/Angular, validations de versions et contrôles des paquets.
- CLI providers : ajout de `glimio providers list`, `info`, `install` et `doctor` pour utiliser, diagnostiquer et installer les dépendances des providers sans interface Web.

- État des providers après installation : Glimio interroge à nouveau l’API de disponibilité après l’installation des dépendances Python. Si le provider est prêt, l’interface l’indique immédiatement ; si les paquets restent invisibles au processus courant, elle recommande un redémarrage ; si seuls des modèles ou chemins manquent, elle les présente comme éléments de configuration sans demander un redémarrage inutile.
- Traductions des providers isolées dans leurs propres métadonnées (`ProviderInfo.translations`) et renvoyées par l’API. Les libellés, options, choix et ressources de chaque intégration sont localisés depuis son catalogue ; le dictionnaire général ne doit contenir que les textes propres à l’application et les termes réellement partagés.
- Styles des options providers : retrait d’un sélecteur SCSS mort et vérification que les règles d’options, d’installation et de ressources restent dans la feuille de style du composant partagé, en réutilisant les classes de formulaire et tokens de thème existants.
- Tests supplémentaires : sérialisation des traductions appartenant au provider, présence des traductions EN pour les providers intégrés, et disponibilité FFmpeg conditionnée à la présence de `ffprobe`.

- Correctif DeepFilterNet : utilisation de l’option CLI correcte `--output-dir` (au lieu de `--out-dir`) et test de régression couvrant la conversion aller-retour et la production du fichier amélioré.
- Correctif de build Angular : suppression de deux clés de traduction dupliquées (`Commande ou chemin vers FFmpeg.` et `Périphérique`) qui provoquaient `TS1117` ; simplification de la vérification de `setup_links.length` pour éliminer l’avertissement Angular `NG8107`.
- Harmonisation Enregistrement / Paramètres : la diarisation possède un interrupteur explicite commun aux deux pages ; ses ressources ne s’affichent que lorsqu’elle est active. La séparation de sources (voix qui se chevauchent) et le rapprochement d’identité entre pistes/blocs sont présentés comme des fonctions distinctes, avec leurs dépendances fortes explicites.
- Configuration plus discrète pendant l’enregistrement : les liens de téléchargement et les actions d’installation des providers ne sont plus affichés dans les options par traitement. Un raccourci vers les Paramètres apparaît seulement si une ressource requise par le parcours choisi manque ou si une dépendance obligatoire n’est pas satisfaite.
- Ressources des providers regroupées dans Paramètres dans un panneau repliable, ouvert par défaut lorsqu’un provider n’est pas prêt et replié lorsque tout est configuré.
- Traductions françaises/anglaises complétées pour les nouveaux libellés de diarisation, séparation, identité vocale et d’installation des ressources audio, y compris les liens d’aide DeepFilterNet et FFmpeg.

- Interface plus discrète pour les providers optionnels : les providers de désactivation ne montrent plus leurs détails ni un état « Prêt » ; les ressources de diarisation sont masquées lorsqu’elle est désactivée ; le panneau actif de rapprochement vocal est renommé.
- Paramétrage des providers depuis l'interface : liens de téléchargement déclarés avec chaque provider vers les binaires, modèles, documentations et notices de licence ; chemins et ressources restent configurables dans les paramètres.
- Installation Python en un clic pour les providers qui déclarent un extra connu (`diarization`, `separation`) : installateur asynchrone, journal consultable, refus dans les éditions empaquetées et rappel explicite de redémarrer Glimio après installation. Les noms de paquets ne sont jamais acceptés depuis une requête utilisateur.
- Nouvelle API de suivi des installations des providers (`/api/providers/{id}/install-python`, `/api/provider-installs/{id}`) avec sérialisation de métadonnées d'installation et disponibilité adaptée au mode source/packagé.
- Architecture audio modulaire : providers distincts pour le prétraitement, la séparation de sources et les embeddings vocaux ; métadonnées déclaratives des dépendances fortes, vérification de disponibilité et sélection extensible dans le CLI et les paramètres.
- Import multipiste : tous les flux et canaux sont conservés indépendamment ; le gain source est préservé par défaut afin de ne pas amplifier un bruit de fond ou une piste faible par simple normalisation de crête (la normalisation plafonnée reste opt-in).
- Transcription longue : reprise limitée au préfixe de checkpoints valide ; une corruption ou un manque de bloc invalide la traîne afin d'éviter de réutiliser des centroïdes d'identité issus d'un état incompatible.
- Séparation de source facultative : liaison d'identités globale multi-locuteurs via embeddings ECAPA, état sérialisable pour reprise et dépendance explicite du provider SepFormer. La séparation deux voix reste opt-in à cause des limites du modèle public sur les réunions réelles.
- Documentation : ajout de la matrice des providers audio, prérequis hors ligne, modèles/permissions, critères de reprise et limites sur le bruit et le chevauchement des voix.

- Transcription longue : choix explicite d’un provider de prétraitement audio indépendant de l’ASR (débruitage FFmpeg par défaut ou DeepFilterNet facultatif) ; les fichiers originaux restent inchangés. Les modèles et binaires optionnels ne sont pas embarqués.
- Whisper.cpp : ajout des options de détection de parole Silero (VAD) afin d'éviter le traitement des longues plages silencieuses lorsqu'un modèle VAD local est disponible ; ajout des options de configuration correspondantes au catalogue du provider.
- Import audio/vidéo : conservation de tous les flux audio détectés par ffprobe dans des pistes distinctes (`audio_import.wav`, `audio_import-2.wav`, etc.) avec métadonnées par piste.
- Diarisation : suppression de la normalisation par pic appliquée à chaque piste avant le mixage, mixage par blocs avec des buffers source limités, et refus d'attribuer une voix éloignée à un segment ne chevauchant aucun tour de parole.
- Diarisation isolée dans un processus enfant : l'inférence native `sherpa-onnx` ne bloque plus le GIL du serveur, donc l'API et le flux SSE restent réactifs pendant le job ; une annulation termine le processus enfant et les transcriptions sont remplacées atomiquement.
- Consolidation des événements SSE : les mises à jour rapprochées d'un même job, d'un artefact ou d'une recherche sont regroupées avant diffusion, ce qui allège le flux et évite les rafales de rendus dans l'interface.
- Rafraîchissements d'artefacts non bloquants : les aperçus en cours de génération sont demandés en arrière-plan avec un découpage incrémental vérifié, sans interrompre l'édition ni les actions en cours.
- Affichage progressif des documents en cours de génération, avec révélation accélérée du texte déjà reçu et respect de `prefers-reduced-motion`.

## 0.4.4 — temps réel, UI mobile fluide et harmonisation du design — 2026-10-21

**Temps réel de la Bibliothèque**
- L'état d'avancement d'une séance (En attente / En cours / Terminé / Échec) s'affiche dans la liste et le panneau de détail grâce au flux SSE partagé, sans rafraîchissement périodique ni réinitialisation des aperçus d'artefacts ou des options en cours d'édition.
- Les messages d'erreur et les changements de phase des jobs sont transmis par les événements du serveur dès qu'ils sont disponibles.
- Suivi de phase de l'artefact en cours : l'aperçu suit automatiquement la nouvelle phase de traitement tant que l'utilisateur n'a pas changé d'onglet manuellement.

**Interface fluide sur mobile**
- Composants `glimio-ui` rendus fluides sur petit écran : typographie et espacements en unités relatives (`clamp()`), cibles tactiles élargies (boutons, sélecteurs, onglets ≥ 44 px), grilles et panneaux qui passent en une colonne sous les breakpoints mobile.
- Barre latérale et panneau de détail de la Bibliothèque adaptés au mobile : empilement vertical, défilement indépendant des zones et masquage progressif plutôt que destruction du contenu.
- Sélection de phase, dialogue de confirmation et champs de formulaire repensés pour rester entièrement visibles et utilisables sans zoom sur mobile.

**Harmonisation du design**
- Palette, arrondis, ombres et états de survol/focus unifiés autour des tokens de `tailwind.css` ; suppression des styles ad hoc redondants dans les pages.
- Alignement des cartes, en-têtes et listes sur une échelle d'espacement commune ; badges de statut homogénéisés (couleur, taille, libellés).
- Transitions cohérentes entre les changements d'état (sélection de séance, onglets d'artefacts, progression des jobs) pour une sensation visuelle continue.

**Autres correctifs**
- Pipeline : sauvegarde fiable des artefacts intermédiaires et réutilisation correcte des modèles chargés.
- API web : gestion renforcée des jobs et réponses d'erreur 4xx explicites.
- Application desktop : corrections de navigation et de bascule automatique entre vues.
- Accessibilité : zones de statut en `role="status"` + `aria-live="polite"` pour annoncer les transitions sans interrompre la navigation clavier.
- Versions API (`FastAPI`), frontend (`package.json` / `package-lock.json`) et projet Python alignées sur `0.4.4`.

## 0.4.3 — éditions Windows et publication GitHub

- Ajout d’un CLI pour enregistrer, transcrire, résumer ou traiter un fichier audio/vidéo ou une séance depuis le terminal.
- Préparation de trois éditions Windows x64 (CLI, Web, Web avec diarisation), chacune en installateur et archive portable ; les exécutables natifs et poids de modèles restent séparés.
- Ajout des workflows CI et de création d’une release brouillon déclenchée par un tag `vX.Y.Z`, avec contrôle des versions, tests, sommes SHA-256 et publication des six paquets.
- Les builds empaquetés servent le frontend Angular inclus et stockent les données sous `%LOCALAPPDATA%`; le workflow de développement depuis les sources conserve son build Angular habituel.
- Allègement de la suite Python : retrait des vérifications textuelles d’Angular et de documentation, désormais redondantes avec les contrôles frontend dédiés ou sans valeur de régression.

## 0.4.3 — mise development toolchain

- Added root `mise.toml` pinning Python 3.14, Node.js 26, and `npm:@angular/cli` 22, with the project virtual environment at `.venv`.
- Added a `dev` optional dependency group for pytest and documented the setup and verification commands.
- Environment note: this execution container has no `mise` binary and cannot resolve `mise.jdx.dev`; the suite was therefore checked with the available Python 3.13 environment, not the requested Python 3.14 / Node 26 toolchain.

## 0.4.3 — Angular 22.2 / TypeScript 6 build fixes

- Aligned frontend dependency ranges with Angular 22.2.3, TypeScript 6.0.3, Vitest 5, jsdom 30, Node type definitions 26, and Zone.js 0.16.3.
- Removed the deprecated TypeScript `baseUrl` option; no path aliases are configured, so it was unnecessary.
- Fixed the search button's signal access (`query()`), tightened the bitrate selector to its supported literal union, and removed an unnecessary optional chain in the guarded library template.
- Confirmed `angular.json` uses the Angular application builder and Angular's unit-test builder. A production build still needs to be run with the pinned Node.js 26 toolchain and installed npm dependencies.

## 0.4.3 — Passe complémentaire UI, Sass et tests — 2026-10-19

- Bibliothèque : dimensions explicites pour l’icône de durée, badge d’état aligné sur la première ligne du texte, panneaux des onglets encadrés et arrondis de façon cohérente.
- Pagination : plage visible aussi avec plusieurs pages, résumé aligné à droite quand il n’y a qu’une page, commandes compactées en fonction de la largeur réelle du composant et choix du nombre d’extraits par page dans la recherche.
- Recherche intelligente : extraits présentés comme des cartes de séance, espaces homogènes, pagination et taille de page cohérentes.
- Formulaires et mise en page : cases/radios alignés sur la première ligne de leur libellé, hauteur/marge de « Nombre d’interlocuteurs » normalisée et titre de page plus compact.
- Styles : entrée Tailwind 4 isolée dans un fichier CSS simple, composition Sass via `@use`, styles Markdown partagés, règles de la Bibliothèque réduites pour rester sous le budget de style de composant.
- Paramètres : les trois poids tiers ouvrent désormais leur page/release manuelle plutôt que de dépendre d’une URL directe de téléchargement ; les confirmations de licence/conditions restent nécessaires.
- Outillage : Node.js minimal indiqué explicitement (`22.22.3` sur la branche 22), import de `web.app` sans build frontend implicite, et configuration de lancement IDE ramenée à des chemins de projet plutôt qu’à des chemins locaux figés.
- Tests : suppression de trois assertions visuelles/structurelles trop fragiles et ajout de contrats centrés sur les comportements partagés. Validation Python : 111 tests réussis, `compileall` et vérification des paires de jetons de contraste réussis. Le build Angular n’a pas été validé dans cet environnement : il fournit Node `22.16.0` (trop ancien pour Angular 22.2.3), et `npm ci` n’a pas terminé correctement.

## 0.4.3 — Correctifs prioritaires build Angular et modèles — 2026-10-19

- Compilation : ajout explicite de `IconComponent` aux imports de `PaginationComponent`, supprimant la cause des erreurs `NG8001` du composant de pagination ; suppression du `?? []` redondant ciblé par `NG8102`.
- Bibliothèque : rendu Markdown des tableaux en HTML accessible avec défilement horizontal et focus clavier ; confirmation renforcée lors de la suppression de la dernière piste audio et message correct si aucun audio ne reste.
- Modèles : liens officiels dédiés pour les modèles Whisper, LFM2.5, segmentation pyannote et embedding 3D-Speaker ; les liens LFM, pyannote et 3D-Speaker sont conditionnés à une confirmation de lecture des licences/conditions. Glimio n’exécute pas automatiquement de binaires tiers.
- Thèmes et ressources : vérification des contrastes documentés dans les six thèmes et mise à jour des contrats autour du favicon SVG.
- Validation ciblée : 39 tests de contrat/API/audio passés et `py_compile` réussi. Build Angular non exécuté dans cet environnement faute du binaire `ng` ; les avertissements de dépréciation Sass `@import` restent non bloquants et devront être retirés par une migration globale vérifiée.

## 0.4.3 — Correctifs UI, états de séance et capture audio — 2026-10-19

- Bibliothèque Angular : ajout d’un rafraîchissement périodique (2 s) de la liste et du détail de la séance pour refléter les transitions d’état des jobs, sans réinitialiser les aperçus d’artefacts ni les paramètres de traitement en cours d’édition. Le polling résiste aux erreurs réseau passagères et évite les requêtes concurrentes.
- Bibliothèque : affichage explicite des états En attente / En cours / Terminé / Échec, et des messages d’erreur quand disponibles, dans la liste et dans le panneau de détail. Le panneau de détail réutilise le composant partagé `session-live-progress`.
- Accessibilité : la carte de séance n’imbrique plus des éléments de type bloc dans un `<button>` ; la zone de sélection est un bouton dédié avec état `aria-pressed` et focus visible, le message de traitement étant son voisin dans la carte.
- Branding : SVG public sans métadonnées Inkscape/Sodipodi, calques conservés sous `layer3` (wave) et `layer2` (forme principale), les deux utilisant `currentColor` ; la vague se distingue uniquement par une opacité de 25 %.
- Capture audio : correspondance exacte et insensible à la casse en priorité ; les anciennes préférences à correspondance partielle restent acceptées uniquement si le résultat est unique. Les sélections ambiguës et noms exactement dupliqués sont refusés avec un message explicite. Un log met en évidence les noms identiques des deux endpoints Bluetooth sans désactiver arbitrairement l’une des deux pistes.
- SCSS : normalisation du padding des cartes principales sur `p-5` (20 px), retrait d’un bloc de styles en doublon pour les contrôles d’activité et tests de contrat ciblant le rafraîchissement des états et le SVG. Le vérificateur de contraste référence maintenant le véritable fichier `styles/tokens.scss` au lieu d’un `tokens.css` inexistant.
- Validation : les tests de `test_audio_streaming.py` passent (6 tests) et les fichiers Python modifiés passent `py_compile`. Le build Angular n’a pas pu être exécuté ici : les dépendances npm ne sont pas intégralement disponibles hors ligne, `ng` reste absent, et la version Node fournie (22.16.0) est inférieure à la version minimale annoncée par Angular 22.2.3 (22.22.3). Tester la compilation complète avec une version Node compatible avant fusion.

## 0.4.3 — Correctifs fonctionnels — options par séance et diarisation

- Ajout du module manquant `seance.diarization` avec chargement WAV, exécution locale sherpa-onnx, alignement des segments de voix sur la transcription horodatée, sauvegarde JSON et sauvegardes de la transcription d’origine. Un message explicite indique l’extra Python ou les modèles ONNX manquants.
- Restauration de l’import audio/vidéo FFmpeg : création d’une séance durable, conversion en WAV mono PCM 16 kHz, métadonnées de source et nettoyage du dossier partiel en cas d’échec.
- Déplacement de la langue de transcription et du format de résumé par défaut vers **Options communes** sur la page Enregistrement ; les réglages s’appliquent aux nouveaux enregistrements et imports.
- Ajout d’options propres à chaque séance dans la Bibliothèque : langue, format de résumé, diarisation et nombre d’interlocuteurs. Les valeurs sont conservées dans `metadata/seance.json` et réutilisées par les traitements relancés.
- Harmonisation des icônes de l’interface sur le sprite Heroicons local ; suppression des SVG d’icônes dessinés à la main hors du logo de marque. Cible tactile du burger mobile agrandie à 48 × 48 px et menu mis au premier plan.
- Chemins par défaut des exécutables : `bin/asr/whisper-cli.exe` et `bin/llm/llama-completion.exe`.
- Documentation README et chemins de modèles mis à jour.

## 0.4.3 — Corrections complémentaires — 2026-10-18

- Les exécutables par défaut utilisent maintenant les noms amont standards : `bin/whisper/whisper-cli.exe` et `bin/llama-cpp/llama-completion.exe`, de façon cohérente entre backend, traitements CLI, interface statique et documentation. Les anciennes valeurs génériques enregistrées sont migrées vers ces chemins lorsqu’elles ne pointent pas vers un fichier existant.
- Harmonisation des icônes SVG, des espacements internes de la diarisation, du menu mobile, du menu d’actions de séance et de l’indication discrète de sauvegarde automatique. Les activités terminées/échouées peuvent être effacées individuellement par une croix ou en lot avec « Effacer l’historique » ; les tâches en cours et en attente restent protégées.

## 0.4.2 — Réorganisation de l’interface et navigation mobile

- Déplacement des options de traitement communes sous les sections « Nouvelle séance » et « Fichier existant ».
- Déplacement du choix du nombre de participants dans la page Enregistrement ; le champ est masqué quand la détection automatique est active et la case se trouve au-dessus.
- Conservation du seuil de regroupement dans Paramètres, avec une explication de son lien avec la détection automatique.
- Remplacement de la navigation mobile horizontale par un menu burger accessible, repliable au choix d’une page, avec fermeture par Échap ou clic extérieur.
- Correctif de navigation clavier : après le choix d’une page dans le menu mobile, le focus est transféré au titre de la page sélectionnée.
- Paramètres : retrait du bouton d’enregistrement manuel ; les modifications sont sauvegardées automatiquement et un toast réutilisable confirme le succès ou annonce l’échec réel du `PUT`.
- Grilles responsives : hauteur des deux parcours d’enregistrement harmonisée sur grand écran, panneaux de la Bibliothèque alignés, OPTIONS COMMUNES adaptées à l’espace disponible et licence affichée sur toute la largeur.
- Finition de l’interface : ajout d’un espacement explicite entre les panneaux Enregistrement et OPTIONS COMMUNES, intégration des paramètres de diarisation dans cette même carte, séparation visuelle de la licence après la note de sauvegarde automatique et marge régulière autour du burger sur mobile.
- Paramètres de diarisation : titre aligné au-dessus du panneau au lieu d’être posé dans sa bordure ; contenu interne espacé et marges adaptées aux petits écrans, tout en conservant le regroupement sémantique accessible du formulaire.
- Menu : chemin complet du dossier des séances visible, repliable sur mobile avec le menu, et action de copie ; indicateur de traitement alimenté par le mode de configuration au lieu d’une promesse statique de fonctionnement hors cloud.
- Version API, paquet frontend et projet alignés sur `0.4.2`.

## Interface et maintenance — 0.4.2

### Options de diarisation

- Harmonisation des marges, du padding et du fond du champ de nombre d’interlocuteurs.
- Seuil de regroupement toujours disponible dans Paramètres, quel que soit le mode automatique ou manuel choisi sur la page Enregistrement.
- Clarification des aides en français et en anglais pour les options communes, le nombre d’interlocuteurs et le seuil de regroupement.

- Harmonisation des marges des activités, pagination de l’historique et effacement des activités terminées (les tâches actives/en attente sont conservées).
- Icônes SVG intégrées inspirées du style Heroicons, sans dépendance distante, et symbole Glimio distinctif.
- Barre de marque mobile extensible, avec le bouton de navigation maintenu à l’extrémité de la ligne.
- Chemins proposés dans Paramètres alignés sur les valeurs par défaut réellement utilisées par le backend.
- Dépendance FastAPI portée à la version minimale 0.143.4.

## UI follow-up — Heroicons, pagination partagée et espacements

- Remplacement des trois balises `<i>` du menu d’actions de la bibliothèque par l’icône `bars-3` de Heroicons v2 Outline, intégrée localement sans CDN. Ajout des mentions de licence MIT.
- Harmonisation du bouton de menu mobile avec le même composant Heroicons partagé. Correction du bug qui remplaçait son SVG par du texte (`☰` / `×`) lors du clic et pouvait donc masquer l’icône.
- Déplacement de la croix de suppression des activités dans le coin supérieur droit de la carte, avec une zone de contenu réservée pour éviter les chevauchements.
- Création d’un composant de pagination réutilisable (`paginationMarkup` + `updatePagination`) partagé entre Activités et Bibliothèque, au lieu de maintenir deux structures séparées.
- Ajout de padding intérieur cohérent à la section de diarisation et aux cartes d’activité, dans les CSS sources et les CSS statiques servis.
- Ajout de tests de contrat UI pour les icônes locales, la pagination partagée et la position de la suppression.

## UI follow-up — 2026-10-19

- Prevented responsive brand mark clipping and aligned the translucent `wave` SVG layer with `currentColor`.
- Expanded the library session action menu with Heroicons and consistent button controls.
- Prioritized session documents, then audio tracks, processing status, and per-session settings.
- Restored an understated AGPL-3.0-or-later license notice in Settings.
- Standardized spacing for the intelligent-search explanatory text and added contract coverage.

## Refactorisation Angular et identité de marque

- Extraction des templates Angular dans des fichiers HTML et des styles locaux dans des fichiers SCSS.
- Remplacement du pictogramme temporaire par le SVG de marque Glimio dans les interfaces Angular et legacy.
- Inclusion des nouveaux fichiers HTML/SCSS et de l’asset de marque dans les fichiers distribués.

## 0.4.1 — Options de traitement partagées

- Enregistrement et import : déplacement des options communes dans une carte autonome « Options de traitement », placée avant les deux parcours pour la consulter avant de démarrer un enregistrement ou un import, puis l’activité apparaît séparément en dessous. Elle est visible sans chevron/accordéon, cohérente avec les cartes du reste de l’interface.
- La diarisation reste accessible quelle que soit l’action choisie dans le panneau d’enregistrement, car sa préférence sert aussi aux fichiers importés. Elle est indiquée comme sans effet lorsque le traitement est limité à « Enregistrer seulement ».
- L’activité dispose maintenant de son propre panneau sous les flux principaux, ce qui sépare mieux les actions, les paramètres de traitement communs et le suivi des tâches.
- Suppression de la phrase « Les options inutiles sont masquées selon le flux choisi » de l’interface et des catalogues de traduction. Les catalogues FR/EN restent synchronisés.
- Version de développement, API et package frontend alignés sur `0.4.1`.

## 0.4.0 — Paramètres centralisés, qualité audio et licence copyleft

- Ajout d’une page **Paramètres** dédiée qui centralise les chemins des modèles et exécutables, le moteur FFmpeg, la langue de transcription, les options OpenVINO, les budgets de génération, les réglages de diarisation et les préférences de qualité audio.
- Les chemins par défaut du code sont génériques et basés sur le rôle du fichier (`models/asr/model.bin`, `models/llm/model.gguf`, `models/diarization/segmentation/segmentation.onnx`, `models/diarization/embedding/embedding.onnx`, `bin/asr/transcriber.exe`, `bin/llm/inference.exe`). Les sources et noms upstream restent documentés dans `docs/MODELS.md`.
- Ajout du choix de débit d’enregistrement PCM mono 16 bits (128/256/384/512/768 kbps, correspondant à 8/16/24/32/48 kHz) ; les métadonnées de séance conservent le débit et la fréquence choisis.
- Passage à la licence `AGPL-3.0-or-later` pour le code Glimio. Ajout d’une note expliquant les droits de revente, le copyleft réseau, la distinction entre licence Open Source et restriction commerciale, et la séparation de la marque et des licences de modèles tiers.

## 0.3.0 — Préparation Git, actions compactes et langue de transcription

- Bibliothèque : suppression des boutons d’en-tête redondants Résumé/Transcription (les onglets de contenu restent accessibles), maintien de « Tout traiter » comme action principale et regroupement de Transcrire, Renommer et Supprimer dans un menu d’actions compact, accessible au clavier et refermé lors d’un clic extérieur ou d’Échap.
- Enregistrement : le mode « Auto — suivre la langue de l’interface » utilise la langue courante de l’interface (fr/en) pour les prochains traitements, sans écraser la préférence enregistrée. Un mode distinct laisse Whisper détecter la langue réellement parlée. Le réglage indique la langue source à reconnaître et ne prétend pas traduire la transcription.
- Versionnement de développement ramené à `0.x` ; versions Python, API et frontend alignées sur `0.3.0`.
- Ajout d’une licence MIT pour le code/documentation Glimio, d’un `.gitignore` étendu pour les poids/exécutables/données locales, d’un `.gitattributes`, d’un guide Git, d’une politique de contribution et d’une note sécurité.
- README réorganisé et guide de modèles ajouté : sources éditeurs et conditions distinctes des modèles LFM2.5, Whisper, pyannote/Titanet, des exécutables natifs et de FFmpeg.

## 0.2.5 — Localisation FR/EN et tailles de texte relatives

- Ajout d’un sélecteur de langue accessible dans la barre supérieure : français et anglais. La langue est mémorisée localement ; au premier démarrage, la langue du navigateur est utilisée si elle est prise en charge, avec repli sur le français.
- Ajout de catalogues JSON `fr` et `en`, d’une couche de traduction hors ligne sans dépendance JavaScript tierce, d’un mécanisme pour les messages avec variables et d’une mise à jour du `lang` de la page. Les nouvelles chaînes sont gérées avec des identifiants de type *gettext* (message source) pour les catalogues natifs.
- Les chaînes d’interface statiques et générées sont traduites ; les contenus de séance, transcriptions, extraits source et réponses IA sont exclus de la traduction automatique. Les dates suivent aussi la langue sélectionnée.
- Les tailles de texte explicites restent en `rem` et suivent la taille racine du navigateur ; les champs de saisie héritent de la typographie. Les dimensions non textuelles restent exprimées selon leur besoin de mise en page.
- Ajout de tests de contrat pour les catalogues, le sélecteur et l’inclusion des ressources de langue dans le paquet Python.

## 0.2.4 — Typographie, reset navigateur et état d’enregistrement

- Masquage de « Nouvelle séance » dans la Bibliothèque pendant une capture active ; le bouton reste l’action principale de cette page au repos, tandis que la bannière propose « Revenir à l’enregistrement » pendant la capture.
- Base typographique portée à `1rem` (16 px par défaut) et tailles de texte exprimées en `rem` dans les styles d’exécution et les sources Tailwind. Les micro-textes les plus petits ont été relevés pour améliorer la lisibilité et restent adaptables au zoom et aux préférences du navigateur.
- Marque affichée « Glimio » en italique léger, sans augmenter l’encombrement de la navigation.
- Ajout d’une feuille de normalisation navigateur basée sur modern-normalize (licence MIT), chargée avant les styles de l’application ; import équivalent ajouté aux sources frontend.
- README conservé comme documentation d’installation et d’utilisation ; les modifications sont consignées dans ce Changelog.

## 0.2.3 — Action de nouvelle séance contextuelle

- Bibliothèque : le bouton principal « Nouvelle séance » est masqué lorsqu’une capture audio est en préparation, en cours ou en finalisation. La bannière « Revenir à l’enregistrement » devient alors le seul appel à l’action principal lié à la capture active.
- Bibliothèque : conservation du bouton « Nouvelle séance » dans l’en-tête lorsque la capture est inactive ; c’est son emplacement le plus prévisible pour démarrer depuis l’historique.
- Bibliothèque vide : retrait du bouton « Nouvelle séance » redondant dans le panneau de détail. L’en-tête constitue désormais l’unique point d’entrée, ce qui évite les doubles appels à l’action et garde leur visibilité synchronisée avec l’état d’enregistrement.
- Version de distribution Python, API et package UI avancés à `0.2.3`.

## 0.2.2 — Accès direct à l’enregistrement actif depuis la bibliothèque

- Bibliothèque : ajout d’une bannière d’état lorsqu’une capture audio est en préparation, en cours ou en finalisation. Le libellé distingue explicitement l’enregistrement des traitements Whisper/LLM.
- Bibliothèque : bouton « Revenir à l’enregistrement » qui ramène au panneau Enregistrement et place le focus sur le bouton Arrêter lorsque la capture est active, sinon sur son statut.
- Cartes de séances et détails : les statuts affichent « Enregistrement en cours », « Whisper en cours » ou « Résumé LLM en cours » au lieu d’un état générique ambigu.
- Bannière responsive et annoncée comme région de statut pour les technologies d’assistance ; le retour à l’enregistrement respecte la préférence de réduction des animations.
- Version de distribution Python, API et package UI avancés à `0.2.2`.

## 0.2.1 — Survols pleine largeur dans les listes

- Navigation latérale : suppression du retrait horizontal interne pour que le survol et l’élément actif remplissent toute la largeur du groupe arrondi. Le défilement horizontal sur petit écran est conservé.
- Bibliothèque : les lignes des séances s’étendent maintenant de bord à bord dans leur conteneur, sans marge latérale qui coupe le surlignage.
- Activité : les lignes de jobs remplissent la largeur du panneau ; le fond de survol déborde jusqu’aux bords intérieurs du panneau tandis que le texte reste aligné sur l’en-tête. Le débordement s’adapte au padding responsive.
- Recherche intelligente : les sources utilisent une liste continue avec séparateurs fins au lieu de fonds de survol fragmentés par des espaces verticaux.
- Ajout de contrats de tests CSS pour éviter la régression des listes pleine largeur.
- Version de distribution, métadonnées API et package UI avancés à `0.2.1`.

## 0.2.0 — Persistance, reprise et interface aplatie

- Bibliothèque : lancer Whisper, la synthèse LLM ou le traitement complet ne redirige plus vers la page Enregistrement. La séance reste ouverte et son état est rafraîchi.
- Thèmes : palettes rééquilibrées vers des tons plus neutres, avec un accent bleu lisible et moins de dominante violette ; les quatre variantes restent configurables.
- Design plat : suppression des ombres fortes et bordures décoratives, couleurs de surface plus sobres, rayons plus contenus. La navigation latérale et la liste des séances sont traitées comme des groupes arrondis plutôt que comme une collection de cartes individuelles. Le focus clavier reste explicite.
- Nouvelle persistance SQLite séparée par responsabilité : `sqlite_db.py` pour le chemin/les migrations, `job_store.py` pour l'historique et la file de jobs, `preferences_store.py` pour les préférences utilisateur.
- La file FIFO est durable : action, paramètres du traitement, séance, état, phase et point de contrôle sont écrits avant l'ajout du job au worker. Au démarrage, les tâches en attente ou interrompues sont reconstruites dans l'ordre et redémarrent depuis le dernier point de contrôle exploitable.
- Traitement complet : le point de contrôle `transcribed` permet de reprendre directement la synthèse après une coupure ; une coupure pendant Whisper entraîne la reprise de la transcription pour ne pas réutiliser un fichier partiel. Si le résumé final est déjà validé, le job est marqué terminé sans relancer les modèles.
- Les options de Whisper, llama.cpp, diarisation, workflow, sources audio, périphériques et thème sont enregistrées dans SQLite et rechargées au démarrage, au lieu de dépendre uniquement du navigateur.
- Les jobs de capture interrompus par un arrêt machine ne sont pas relancés automatiquement : les fichiers WAV éventuellement incomplets sont signalés à l'utilisateur, puisque le flux audio live ne peut pas être reconstitué.
- Base locale par défaut : `.glimio/glimio.sqlite3` à la racine du projet ; `GLIMIO_DATA_DIR` permet de choisir un autre dossier, par exemple un dossier de données durable.
- Durabilité SQLite renforcée par WAL et `synchronous=FULL` sur chaque connexion ; ordre FIFO déterministe même lorsque des jobs partagent le même horodatage. Le nouveau `.gitignore` exclut la base locale et les artefacts de développement du contrôle de version.
- Version de distribution, métadonnées API et package UI avancés à `0.2.0`.

## 0.1.0 — File de traitement séquentielle et capture indépendante

- Séparation entre capture audio et calcul IA : l’enregistrement web se termine à la finalisation des WAV, puis la transcription/synthèse automatique est ajoutée à la file de traitement.
- Nouvelle file FIFO à consommateur unique : les jobs de transcription, de résumé, de traitement complet et d’import sont exécutés un par un. Chaque traitement complet enchaîne Whisper puis llama.cpp sans lancer deux moteurs IA simultanément.
- Possibilité de démarrer une nouvelle capture pendant que les modèles traitent une séance précédente. Une seule capture audio reste permise à la fois pour éviter les conflits de périphériques.
- Les tâches manuelles et les imports sont mis en file au lieu de renvoyer une erreur dès qu’un autre traitement utilise Whisper ou llama.cpp.
- Verrou partagé `seance.runtime.AI_ENGINE_LOCK` entre Whisper et llama.cpp : les deux moteurs lourds ne chargent pas leurs modèles en même temps dans le même processus. L’attente de llama.cpp reste annulable ; la capture audio ne prend pas ce verrou et continue donc pendant le traitement.
- API des tâches enrichie avec état `queued`, position dans la file et aperçu du travail courant ; la page Activité distingue les tâches en attente du travail en cours.
- L’historique des tâches est conservé dans SQLite ; les jobs en attente/actifs sont restaurés après redémarrage en 2.2.0. Les WAV et les artefacts de séance restent sur disque indépendamment de la base.
- Version de distribution et métadonnées API avancées à `0.1.0`.

Les changements notables sont regroupés par version. Les versions sont celles du projet distribué, pas nécessairement celles de chaque moteur natif.

## 0.0.2 — Finition visuelle et documentation

- Recherche intelligente : conservation du nom fonctionnel, marges/paddings harmonisés, compositeur de question adaptatif et commandes intégrées au pied du champ.
- Enregistrement : déplacement du bouton **Arrêter** dans la barre d’état d’enregistrement. Le texte d’état, le compteur et le bouton restent alignés sur la même ligne ; sur les petites largeurs, le libellé long est tronqué visuellement mais disponible via son attribut `title`.
- Design plus plat : réduction des bordures visibles et des ombres lourdes, avec des surfaces tonales, des reflets internes légers et des halos d’accent subtils au survol/focus. Le focus clavier visible est conservé.
- Version de distribution avancée à `0.0.2`.
- Suppression des README ponctuels de correctifs `README_TAILWIND_COMPONENTS.md`, `README_UI_CLEANUP.md`, `README_UI_UX_IMPROVEMENTS.md`, `README_AUDIO_NORMALIZATION.md` et `README_ACTIVITY_LIBRARY_LINK.md`. Leurs notes de composants Tailwind, de simplification UI, de gestion des séances, de navigation depuis l’activité et de normalisation audio ont été regroupées ci-dessous. Le README de racine reste la documentation principale et ce fichier reste l’historique des évolutions.

### Notes historiques regroupées depuis les README de correctifs

- **Composants Tailwind / états asynchrones** : tokens de thème partagés entre sources Tailwind et CSS runtime, helper commun de chargement des boutons, distinction des curseurs `not-allowed` et `wait`, restauration des états originaux, styles runtime autonomes sans Node.js à l’exécution.
- **Simplification de l’interface** : retrait des badges et mentions répétitives sur le traitement local, textes plus orientés vers la fonction, maintien des contrôles de normalisation audio et cohérence entre le CSS source et livré.
- **Gestion des séances et recherche intelligente** : pagination, renommage/suppression protégés pendant les tâches actives, titres automatiques fondés sur le résumé, navigation depuis les événements d’activité vers la séance liée et protection contre les réponses réseau obsolètes.
- **Normalisation audio Windows** : normalisation de crête progressive de `audio/windows.wav` après fermeture, cible proche de `-6 dBFS`, gain maximum réglable, silence et pistes déjà fortes préservés, valeurs consignées dans les métadonnées et script de normalisation de fichiers existants avec sauvegarde.
- **Finitions d’accessibilité et d’interface** : sources audio alignées, options conditionnelles, diarisation avec nombre de participants manuel/automatique, seuil réglable en mode automatique, texte sélectionnable, lien de saut clavier et prise en compte de la préférence de réduction du mouvement. Le rapport d’accessibilité reste dans `ACCESSIBILITY_AUDIT.md`.

## 0.0.1 — Recherche intelligente et finition UI

- Renommage cohérent de la rubrique « Recherche IA » en **Recherche intelligente** dans la navigation et le titre de page.
- Refonte de la zone de question : textarea à hauteur automatique (jusqu’à 260 px, puis défilement interne), actions intégrées dans le pied du champ et bouton « Rechercher » aligné avec le contrôle au lieu de flotter à côté.
- Espacements et marges de la recherche harmonisés avec les panneaux et cartes du reste de l’application, y compris sur les petits écrans.
- Bordures des cartes et panneaux adoucies, états de focus/hover renforcés, rayons et hauteurs des boutons/champs rapprochés pour donner un langage visuel plus régulier.
- Aide clavier explicite : `Ctrl + Entrée` (ou `⌘ + Entrée` sur macOS) lance la recherche ; limite de saisie de 12 000 caractères pour préserver la réactivité.
- README conservé comme documentation de référence du projet ; l’historique des évolutions est consigné ici.

## 0.0.0 — Glimio

- Renommage public de l’application en **Glimio**, avec le descriptif « Audio, transcription et notes ».
- Renommage de la distribution Python en `glimio-notes` et ajout des commandes `glimio` / `glimio-web`. Les noms `seance`, `seance-web` et le namespace `seance.*` sont conservés comme couche de compatibilité.
- Ajout d’un README de projet, d’un rapport d’état WCAG et d’un contrôle reproductible des principales paires de contraste.
- Ajout d’un lien de saut vers le contenu principal, d’un landmark principal ciblable au clavier, et de la relation `aria-controls` sur les réglages avancés.
- Nouvelles variables `GLIMIO_*` prioritaires, avec prise en charge des variables `SEANCE_*` historiques.
- Conservation des corrections UI/UX précédentes : gestion des séances, pagination, titres automatiques, états conditionnels, contrôle du nombre de participants et des seuils, alignements et styles cohérents.

