# Changelog

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
