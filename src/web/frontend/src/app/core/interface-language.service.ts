import { Injectable } from '@angular/core';

type Language = 'fr' | 'en';

const ENGLISH: Record<string, string> = {
  'Aller au contenu principal': 'Skip to main content', 'ESPACE DE TRAVAIL': 'WORKSPACE',
  'Enregistrement': 'Recording', 'Bibliothèque': 'Library', 'Recherche intelligente': 'Smart search',
  'Paramètres': 'Settings', 'Traitements': 'Processing', 'Traitements en cours': 'Active processing', 'Traitement local': 'Local processing', 'Les modèles sont exécutés sur cet appareil.': 'Models run on this device.',
  'Consultez les tâches actives et en attente. Vous pouvez annuler un traitement qui semble bloqué.': 'View active and queued tasks. You can cancel a task that appears stuck.',
  'tâche(s) en attente · les modèles sont exécutés séquentiellement.': 'task(s) queued · models run sequentially.',
  'Aucun traitement en cours ou en attente.': 'No active or queued processing.', 'Annulation…': 'Cancelling…',
  'Annulation demandée.': 'Cancellation requested.', 'Actualiser les traitements': 'Refresh processing tasks', 'Impossible de récupérer les traitements :': 'Unable to retrieve processing tasks:',
  'Impossible d’annuler le traitement :': 'Unable to cancel processing:', 'Une annulation active arrête le processus de transcription ou de génération en cours. Les fichiers déjà enregistrés restent disponibles.': 'Cancelling an active task stops the transcription or generation process. Files already saved remain available.',
  'DOSSIER DES SÉANCES': 'SESSION FOLDER', 'Copier': 'Copy', 'Thème de l’interface': 'Interface theme',
  'Sombre': 'Dark', 'Clair': 'Light', 'Minuit': 'Midnight', 'Forêt': 'Forest',
  'Fermer le menu principal': 'Close main menu', 'Ouvrir le menu principal': 'Open main menu',
  'Réduire le menu principal': 'Collapse main menu', 'Développer le menu principal': 'Expand main menu',
  'Réduire le menu': 'Collapse menu', 'Développer le menu': 'Expand menu',
  'Fermer la notification': 'Dismiss notification', 'VOTRE MÉMOIRE DE TRAVAIL': 'YOUR WORK MEMORY',
  'Bibliothèque des séances': 'Session library', 'Consultez les résumés, transcriptions et pistes audio, puis relancez les traitements nécessaires.': 'Browse summaries, transcripts, and audio tracks, then rerun processing when needed.',
  'Nouvelle séance': 'New session', 'Rechercher une séance': 'Search sessions', 'Filtrer les séances': 'Filter sessions',
  'Toutes les séances': 'All sessions', 'Avec résumé': 'With summary', 'Avec transcription': 'With transcript', 'Avec audio': 'With audio',
  'résumé(s) sur cette page': 'summary(s) on this page', 'Résumé': 'Summary', 'Transcription': 'Transcript', 'Audio': 'Audio',
  'Transcription disponible': 'Transcript available', 'Audio disponible': 'Audio available',
  'Aucun document reconnu pour le moment.': 'No document has been generated yet.',
  'Aucune séance trouvée. Enregistrez une séance ou importez un fichier depuis le centre de pilotage.': 'No sessions found. Record a session or import a file from the dashboard.',
  'Séances par page': 'Sessions per page', 'DÉTAIL DE LA SÉANCE': 'SESSION DETAILS', 'Durée': 'Duration',
  'Traiter complètement': 'Process all', 'Autres actions sur la séance': 'More session actions', 'Renommer': 'Rename',
  'Transcrire': 'Transcribe', 'Créer un résumé': 'Create summary', 'Supprimer': 'Delete',
  'Les documents ne correspondent peut-être plus aux pistes actives.': 'The documents may no longer match the active tracks.',
  'Une piste a été désactivée ou supprimée. Relancez le traitement complet pour actualiser la transcription et le résumé.': 'A track was disabled or deleted. Run full processing again to refresh the transcript and summary.',
  'Aucune piste audio n’est conservée. Les documents actuels restent consultables, mais pour les recalculer il faudra réimporter une source audio.': 'No audio tracks are stored. Existing documents remain available, but you must import an audio source again to regenerate them.',
  'Actualiser les documents': 'Refresh documents', 'Contenus de la séance': 'Session contents',
  'Les documents générés apparaissent ici directement.': 'Generated documents appear here.', 'Refaire le résumé': 'Regenerate summary',
  'Chargement du contenu…': 'Loading content…', 'Aucun résumé ni transcription': 'No summary or transcript',
  'Vous pouvez lancer « Traiter complètement » ou créer une transcription depuis le menu d’actions.': 'Run “Process all” or create a transcript from the actions menu.',
  'Pistes audio': 'Audio tracks', 'Désactivée pour les prochains traitements': 'Disabled for future processing',
  'Votre navigateur ne prend pas en charge la lecture audio.': 'Your browser does not support audio playback.',
  'Réactiver': 'Enable', 'Désactiver': 'Disable', 'Supprimer le fichier': 'Delete file',
  'Options de traitement de cette séance': 'Processing options for this session',
  'Ces choix sont enregistrés avec la séance et utilisés lors des prochains traitements.': 'These options are saved with the session and used for future processing.',
  'Enregistrer les options': 'Save options', 'Format du résumé': 'Summary format', 'Langue de transcription': 'Transcription language',
  'Automatique': 'Automatic', 'Détection Whisper': 'Whisper detection', 'Français': 'French', 'Anglais': 'English', 'Allemand': 'German', 'Italien': 'Italian', 'Espagnol': 'Spanish',
  'Nombre d’interlocuteurs': 'Number of speakers', 'Sélectionnez une séance': 'Select a session',
  'Le résumé, la transcription, l’audio et l’état du traitement apparaîtront ici.': 'The summary, transcript, audio, and processing status will appear here.',
  'CENTRE DE PILOTAGE': 'DASHBOARD', 'Enregistrement et import': 'Recording and import',
  'Enregistrez une source audio, importez un fichier ou relancez un traitement sur une séance existante.': 'Record audio, import a file, or rerun processing for an existing session.',
  'NOUVELLE SÉANCE': 'NEW SESSION', 'Configuration de l’enregistrement': 'Recording setup',
  "Configuration de l'enregistrement": 'Recording setup', 'Les pistes audio sont conservées localement. Vous pourrez les transcrire et les résumer ensuite.': 'Audio tracks are stored locally. You can transcribe and summarize them later.',
  'Titre de la séance': 'Session title', 'FACULTATIF': 'OPTIONAL', 'Sources audio': 'Audio sources',
  'Ajoutez une ou plusieurs sources': 'Add one or more sources', 'Type de source': 'Source type', 'Microphone': 'Microphone',
  'Sortie audio Windows': 'Windows audio output', 'Périphérique': 'Device', 'Périphérique par défaut': 'Default device', 'Ajouter': 'Add',
  'Détecter les appareils': 'Detect devices', 'Ajoutez au moins une source audio pour pouvoir démarrer.': 'Add at least one audio source to start recording.',
  'Une source peut être un microphone ou la sortie audio d’un périphérique. Les pistes sont enregistrées séparément. Gardez au moins une source dans la liste.': 'A source can be a microphone or a device audio output. Tracks are recorded separately. Keep at least one source in the list.',
  'Traitement après l’arrêt': 'Processing after stopping', 'Vous pourrez retraiter plus tard': 'You can process it later',
  'Enregistrer seulement': 'Record only', 'Conserver l’audio, sans lancer de modèle.': 'Keep the audio without running a model.',
  'Créer la transcription avec Whisper.': 'Create a transcript with Whisper.', 'Transcrire + résumer': 'Transcribe + summarize',
  'Enchaîner transcription et synthèse.': 'Run transcription followed by summarization.', 'Arrêter': 'Stop',
  'IMPORTER UN FICHIER': 'IMPORT A FILE', 'Audio ou vidéo existant': 'Existing audio or video',
  'Importez un fichier audio ou vidéo pour créer une séance et lancer le traitement local.': 'Import an audio or video file to create a session and start local processing.',
  'Fichier source': 'Source file', 'Cliquez ou déposez un autre fichier pour remplacer': 'Click or drop another file to replace it',
  'Déposez un fichier audio ou vidéo ici': 'Drop an audio or video file here', 'ou cliquez pour parcourir vos fichiers · 5 Go maximum': 'or click to browse your files · 5 GB maximum',
  'Exécuter la chaîne complète.': 'Run the full pipeline.', 'Transcrire seulement': 'Transcribe only', 'Créer uniquement le texte.': 'Generate text only.',
  'Importer et traiter': 'Import and process', 'Taille maximale : 5 Go. Les fichiers sont traités sur cet appareil.': 'Maximum size: 5 GB. Files are processed on this device.',
  'OPTIONS COMMUNES': 'COMMON OPTIONS', 'Options communes de traitement': 'Common processing options',
  'Ces choix s’appliquent aux nouveaux enregistrements, aux imports et servent de valeurs initiales dans la bibliothèque.': 'These options apply to new recordings and imports, and are used as defaults in the library.',
  'Automatique (langue de l’interface)': 'Automatic (interface language)', 'Détecter avec Whisper': 'Detect with Whisper',
  'La détection automatique n’effectue pas de traduction.': 'Automatic detection does not translate speech.',
  'Format du résumé par défaut': 'Default summary format', 'Gain maximal': 'Maximum gain',
  'Choisissez un nombre connu (1–20, puis des valeurs courantes jusqu’à 100) ; sinon laissez Automatique.': 'Choose a known number (1–20, then common values up to 100); otherwise leave it on Automatic.',
  'SUIVI DES TRAITEMENTS': 'PROCESSING ACTIVITY', 'Activités récentes': 'Recent activity',
  'État des enregistrements, imports, transcriptions et résumés.': 'Status of recordings, imports, transcripts, and summaries.',
  'File de traitement': 'Processing queue', 'en attente. Les modèles sont exécutés séquentiellement.': 'waiting. Models run sequentially.',
  'Aucune activité récente. Les nouveaux traitements apparaîtront ici.': 'No recent activity. New processing jobs will appear here.', 'Effacer l’historique terminé': 'Clear completed history',
  'INTERROGER VOTRE HISTORIQUE': 'SEARCH YOUR HISTORY', 'Retrouvez des passages dans plusieurs séances, puis obtenez une synthèse fondée sur les sources.': 'Find passages across sessions and get a source-based answer.',
  'MULTI-SÉANCES': 'MULTI-SESSION', 'Que souhaitez-vous retrouver ?': 'What would you like to find?',
  'Posez une question sur vos séances…': 'Ask a question about your sessions…', 'Ctrl / ⌘ + Entrée pour rechercher': 'Ctrl / ⌘ + Enter to search',
  'Annuler': 'Cancel', 'Recherche…': 'Searching…', 'Rechercher': 'Search',
  'Glimio recherche les passages pertinents dans plusieurs séances et chaque source renvoie à sa séance d’origine.': 'Glimio searches relevant passages across sessions, and each source links to its original session.',
  'Recherche dans les archives': 'Searching the archive', 'EN COURS': 'IN PROGRESS', 'Préparation de la recherche…': 'Preparing search…',
  'Synthèse générale': 'Overview', 'Synthèse indisponible': 'Summary unavailable', 'INFO': 'INFO',
  'Extraits pertinents': 'Relevant excerpts', 'Ouvrir la séance': 'Open session', 'Extraits par page': 'Excerpts per page',
  'Pagination des extraits pertinents': 'Relevant excerpts pagination', 'Explorez vos séances': 'Explore your sessions',
  'Posez une question pour réunir des informations issues de plusieurs séances.': 'Ask a question to bring together information from multiple sessions.',
  'CONFIGURATION GÉNÉRALE': 'GENERAL SETTINGS', 'Configurez les modèles, les exécutables, le traitement et la qualité d’enregistrement.': 'Configure models, executables, processing, and recording quality.',
  'Préférences générales': 'General preferences', 'Langue de l’interface': 'Interface language',
  'Dossier de sortie des séances': 'Session output folder', 'Chemin absolu ou relatif à la racine du projet. Videz le champ pour revenir au dossier par défaut.': 'Absolute path or path relative to the project root. Clear the field to restore the default folder.',
  'Modèles et exécutables': 'Models and executables', 'Modèles IA': 'AI models', 'Outils système': 'System tools',
  'Modèle ASR (Whisper)': 'ASR model (Whisper)', 'Fichier attendu :': 'Expected file:', 'Respectez la LFM Open License v1.0.': 'Follow the LFM Open License v1.0.',
  'Chemin relatif à la racine du projet ou chemin absolu.': 'Path relative to the project root or an absolute path.',
  'Lire la licence': 'Read the license', 'Lire la licence 3D-Speaker': 'Read the 3D-Speaker license',
  'Ouvrir le projet Whisper': 'Open the Whisper project', 'Ouvrir les releases whisper.cpp': 'Open whisper.cpp releases',
  'Ouvrir le projet GGUF': 'Open the GGUF project', 'Ouvrir les releases llama.cpp': 'Open llama.cpp releases',
  'Ouvrir les fichiers du modèle': 'Open model files', 'Lire les conditions pyannote': 'Read pyannote terms',
  'Exécutable whisper-cli': 'whisper-cli executable', 'Modèle LLM (GGUF)': 'LLM model (GGUF)',
  'Exécutable llama.cpp': 'llama.cpp executable', 'Exécutable FFmpeg': 'FFmpeg executable',
  'Commande ou chemin vers l’exécutable.': 'Command or path to the executable.', 'Threads CPU': 'CPU threads',
  'Périphérique OpenVINO (facultatif)': 'OpenVINO device (optional)', 'Automatique / désactivé': 'Automatic / disabled',
  'Transcription et diarisation': 'Transcription and diarization', 'Seuil de regroupement des voix': 'Speaker clustering threshold',
  'Un seuil plus élevé regroupe les voix de façon plus stricte. Ajustez-le selon la qualité audio et le nombre d’interlocuteurs.': 'A higher threshold clusters voices more strictly. Adjust it based on audio quality and the number of speakers.',
  'Qualité audio': 'Audio quality', 'Génération du résumé': 'Summary generation', 'Fenêtre de contexte': 'Context window',
  'Tokens maximum': 'Maximum tokens', 'Tokens d’analyse': 'Analysis tokens', 'Désactiver la relecture finale': 'Disable final review',
  'Réduit les étapes de vérification du résumé.': 'Reduces summary verification steps.', 'Sauvegarde automatique': 'Automatic saving',
  'Les modifications sont enregistrées automatiquement.': 'Changes are saved automatically.', 'Enregistrement des modifications…': 'Saving changes…',
  'Les chemins relatifs sont résolus depuis la racine du projet. Les changements s’appliquent aux prochains traitements.': 'Relative paths resolve from the project root. Changes apply to future processing.',
  'Licence du logiciel': 'Software license', 'Glimio est un logiciel libre.': 'Glimio is free software.',
  'Le code du projet est distribué sous licence': 'The project source is distributed under the',
  'ou ultérieure (AGPL-3.0-or-later)': 'or later (AGPL-3.0-or-later)', 'Consulter le texte officiel de la licence': 'Read the official license text',
  'Le fichier': 'The', 'fourni avec les sources contient la licence applicable au projet. Les modèles, binaires et autres composants tiers peuvent avoir leurs propres conditions.': 'file included with the source contains the project license. Models, binaries, and other third-party components may have their own terms.',
  'Chargement des paramètres…': 'Loading settings…', 'Pagination de la bibliothèque': 'Library pagination',
  'Page précédente': 'Previous page', 'Précédent': 'Previous', 'Page suivante': 'Next page', 'Suivant': 'Next',
  'Séance': 'Session', 'En attente': 'Queued', 'En cours': 'In progress', 'Finalisation': 'Finishing', 'Terminé': 'Completed', 'Erreur': 'Error', 'Arrêt en cours': 'Stopping', 'Échec': 'Failed', 'Annulé': 'Cancelled',
  'Monokai': 'Monokai', 'AUDIO · TRANSCRIPTION · NOTES': 'AUDIO · TRANSCRIPTION · NOTES',
  'Thème de l\'interface': 'Interface theme', 'Navigation de l’application': 'Application navigation', 'Navigation principale': 'Main navigation',
  'Périphériques non vérifiés': 'Devices not checked', 'Détection des périphériques…': 'Detecting devices…',
  'Périphériques indisponibles': 'Devices unavailable', 'Désactivée': 'Disabled', 'Désactivé': 'Disabled',
  'La sauvegarde automatique a échoué :': 'Automatic save failed:', 'Configuration indisponible :': 'Configuration unavailable:',
  'Le chemin du dossier des séances est indisponible.': 'The session folder path is unavailable.',
  'Chemin du dossier copié.': 'Folder path copied.', 'Copie indisponible dans ce navigateur.': 'Copy is unavailable in this browser.',
  'Résumé général': 'General summary', 'Daily — compte rendu de réunion': 'Daily — meeting notes',
  'Technique': 'Technical', 'Formel': 'Formal', 'Brainstorming': 'Brainstorming', 'Dans la file': 'Queued',
  'Diarisation vocale': 'Speaker diarization', 'Associer les segments aux voix détectées.': 'Assign transcript segments to detected speakers.',
  'Modèle d’embedding de diarisation (ONNX)': 'Diarization embedding model (ONNX)',
  'Modèle de segmentation de diarisation (ONNX)': 'Diarization segmentation model (ONNX)',
  'Vérifiez les conditions applicables au poids.': 'Check the terms that apply to this model.',
  'Le modèle pyannote impose une acceptation de ses conditions sur Hugging Face.': 'The pyannote model requires accepting its terms on Hugging Face.',
  'Aucune séance sélectionnée': 'No session selected', 'Changer de thème': 'Change theme',
  'Aucun résultat trouvé.': 'No results found.',
};

@Injectable({ providedIn: 'root' })
export class InterfaceLanguageService {
  private language: Language = 'fr';
  private readonly sourceText = new WeakMap<Text, string>();
  private readonly appliedText = new WeakMap<Text, string>();
  private readonly sourceAttributes = new WeakMap<Element, Map<string, string>>();
  private readonly appliedAttributes = new WeakMap<Element, Map<string, string>>();
  private readonly observer = new MutationObserver(records => this.onMutations(records));

  constructor() {
    this.observer.observe(document.documentElement, {
      subtree: true, childList: true, characterData: true, attributes: true,
      attributeFilter: ['aria-label', 'aria-description', 'placeholder', 'title', 'alt'],
    });
  }

  setLanguage(language: Language): void {
    this.language = language;
    document.documentElement.lang = language;
    this.translateTree(document.documentElement);
  }

  private onMutations(records: MutationRecord[]): void {
    for (const record of records) {
      if (record.type === 'characterData' && record.target instanceof Text) this.translateText(record.target);
      if (record.type === 'attributes' && record.target instanceof Element) this.translateAttributes(record.target);
      for (const node of Array.from(record.addedNodes)) if (node instanceof Element) this.translateTree(node);
      else if (node instanceof Text) this.translateText(node);
    }
  }

  private translateTree(root: Node): void {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) if (node instanceof Text) this.translateText(node);
    if (root instanceof Element) {
      this.translateAttributes(root);
      root.querySelectorAll('*').forEach(element => this.translateAttributes(element));
    }
  }

  private ignored(node: Text): boolean {
    return !!node.parentElement?.closest('[data-no-translate], script, style, code, pre, textarea, .artifact-rendered, .search-source-excerpt, .session-card-select > strong');
  }

  private translateText(node: Text): void {
    if (this.ignored(node)) return;
    const current = node.data;
    const previous = this.appliedText.get(node);
    let source = this.sourceText.get(node);
    if (previous !== undefined && current !== previous) {
      source = current;
      this.sourceText.set(node, source);
    } else if (source === undefined) {
      source = current;
      this.sourceText.set(node, source);
    }
    const translated = this.translate(source);
    if (translated !== current) node.data = translated;
    this.appliedText.set(node, translated);
  }

  private translateAttributes(element: Element): void {
    if (element.closest('[data-no-translate]')) return;
    const names = ['aria-label', 'aria-description', 'placeholder', 'title', 'alt'];
    for (const name of names) {
      const current = element.getAttribute(name);
      if (current === null) continue;
      let sources = this.sourceAttributes.get(element);
      if (!sources) { sources = new Map(); this.sourceAttributes.set(element, sources); }
      let applied = this.appliedAttributes.get(element);
      if (!applied) { applied = new Map(); this.appliedAttributes.set(element, applied); }
      const source = applied.get(name) === current ? sources.get(name) ?? current : current;
      sources.set(name, source);
      const translated = this.translate(source);
      if (translated !== current) element.setAttribute(name, translated);
      applied.set(name, translated);
    }
  }

  private translate(value: string): string {
    if (this.language === 'fr') return value;
    const leading = value.match(/^\s*/)?.[0] ?? '';
    const trailing = value.match(/\s*$/)?.[0] ?? '';
    const content = value.trim();
    const translated = ENGLISH[content] ?? content
      .replace(/^(\d+) résumé\(s\) sur cette page$/, '$1 summary(s) on this page')
      .replace(/^(\d+) séance\(s\)$/, '$1 session(s)')
      .replace(/^Source (\d+)$/, 'Source $1')
      .replace(/^Page (\d+)$/, 'Page $1')
      .replace(/^SÉANCE · (.+)$/, 'SESSION · $1')
      .replace(/^(\d+) éléments$/, '$1 items')
      .replace(/^(\d+) séance\(s\) analysée\(s\)$/, '$1 session(s) analyzed')
      .replace(/^(\d+) microphone\(s\), (\d+) sortie\(s\)$/, '$1 microphone(s), $2 output(s)');
    return translated === content ? value : `${leading}${translated}${trailing}`;
  }
}
