import { ChangeDetectorRef, ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { DecimalPipe } from '@angular/common';
import { Subscription, interval } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { JobEventsService } from '../../core/job-events.service';
import { AudioDeviceInfo, AudioDevices, AudioSourceKind, AudioSourceSelection, GlimioSettings, Job, JobsResponse, PreferencesPayload, ProviderStatus } from '../../core/api.models';
import { PreferencesService } from '../../core/preferences.service';
import { missingProviderDependencyIds, requiredProviderIdsForTask } from '../../core/provider-dependencies';
import { ToastService } from '../../core/toast.service';
import { CheckboxFieldComponent } from '../../shared/checkbox-field.component';
import { IconComponent } from '../../shared/icon.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { ProviderOptionsComponent } from '../../shared/provider-options.component';
import { providerSupportsTranscriptionLanguage, transcriptionLanguageOptions } from '../../shared/transcription-languages';
import { summaryFormatDescription, summaryFormatLabel, summaryFormatOptions } from '../../shared/summary-formats';
import { summaryLanguageOptions } from '../../shared/summary-languages';

interface ProviderSetupIssue {
  key: string;
  message: string;
  /** Provider whose status is being reported or whose dependency is missing. */
  providerId: string;
  /** If the target provider is absent, route to this requiring provider's settings. */
  fallbackProviderId: string;
  requiredProviderIds: string[];
  linkTask?: ProviderStatus['task'];
}

@Component({
  standalone: true,
  imports: [FormsModule, DecimalPipe, RouterLink, CheckboxFieldComponent, IconComponent, PaginationComponent, ProviderOptionsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './recording.page.html',
  styleUrl: './recording.page.scss',
})
export class RecordingPageComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly jobEvents = inject(JobEventsService);
  private readonly preferences = inject(PreferencesService);
  private readonly toast = inject(ToastService);
  private jobsSubscription?: Subscription;
  private hasAppliedPreferences = false;
  readonly devices = signal<AudioDevices>({ microphones: [], outputs: [], microphone_devices: [], output_devices: [] });
  readonly sourceKindToAdd = signal<AudioSourceKind>('microphone');
  readonly sourceDeviceId = signal('');
  readonly selectedAudioSources = signal<AudioSourceSelection[]>([]);
  readonly availableDevices = computed<AudioDeviceInfo[]>(() => this.sourceKindToAdd() === 'microphone'
    ? (this.devices().microphone_devices ?? this.devices().microphones.map((name, index) => ({ id: '', name, key: `microphone:${index}:${name}` })))
    : (this.devices().output_devices ?? this.devices().outputs.map((name, index) => ({ id: '', name, key: `output:${index}:${name}` }))));
  readonly deviceStatus = signal('Périphériques non vérifiés');
  readonly jobsResponse = signal<JobsResponse | null>(null);
  readonly jobs = computed(() => this.jobsResponse()?.items ?? []);
  readonly settings = computed(() => this.preferences.preferences()?.settings ?? null);
  readonly providers = signal<ProviderStatus[] | null>(null);
  readonly perJobOverrides = signal<Record<string, Record<string, unknown>>>({});
  readonly transcriptionLanguages = computed(() => transcriptionLanguageOptions(this.preferences.preferences()?.ui.language ?? 'fr'));
  readonly formats = summaryFormatOptions.map(option => option.code);
  readonly summaryLanguages = summaryLanguageOptions;
  readonly speakerCounts = [...Array.from({ length: 20 }, (_, index) => index + 1), 25, 30, 40, 50, 100];
  readonly visibleJobs = computed(() => this.jobs().slice((this.jobsPage() - 1) * this.pageSize, this.jobsPage() * this.pageSize));
  readonly activeRecording = computed(() => this.jobsResponse()?.active?.kind === 'recording' ? this.jobsResponse()?.active : this.jobs().find(job => job.kind === 'recording' && ['queued', 'running', 'stopping'].includes(job.state)) ?? null);
  /** Résumé d'état et des sources capturées, à côté du bouton d'arrêt. */
  readonly recordingStatusText = computed(() => {
    const job = this.activeRecording();
    if (!job) return '';
    // Les sources capturées ne sont pas exposées par /api/jobs : on reprend la
    // sélection de l'interface (persistée au démarrage de l'enregistrement).
    const sources: string[] = [];
    for (const source of this.selectedAudioSources()) sources.push(`${source.kind === 'microphone' ? 'microphone' : 'sortie Windows'} (${source.device_name || 'périphérique par défaut'})`);
    const suffix = sources.length ? ` · capture de ${sources.join(' + ')}` : '';
    if (job.phase === 'preparing') return `Préparation${suffix}…`;
    if (job.phase === 'finalizing' || job.state === 'stopping') return `Arrêt en cours${suffix}…`;
    return `Enregistrement en cours${suffix}`;
  });
  /** Temps écoulé depuis le début de l'enregistrement, affiché mm:ss (hh:mm:ss au-delà d'une heure). */
  readonly elapsedLabel = signal('00:00');
  private elapsedStartMs: number | null = null;
  private elapsedTick?: Subscription;
  private lastActiveJobId: string | null = null;
  private readonly cdr = inject(ChangeDetectorRef);
  readonly starting = signal(false);
  readonly importing = signal(false);
  readonly selectedFile = signal<File | null>(null);
  readonly jobsPage = signal(1);
  readonly pageSize = 6;
  title = '';
  microphone = '';
  output = '';
  captureMicrophone = true;
  captureWindows = true;
  normalizeWindows = true;
  normalizeGain = 30;
  workflow: 'none' | 'transcribe' | 'summary' = 'summary';
  importAction: 'process' | 'transcribe' = 'process';

  constructor() {
    effect(() => {
      const saved = this.preferences.preferences();
      if (saved && !this.hasAppliedPreferences) {
        this.applyPreferences();
        this.hasAppliedPreferences = true;
      }
    });
  }

  ngOnInit(): void {
    this.api.providers().subscribe({ next: response => this.providers.set(response.providers), error: () => this.providers.set([]) });
    this.refreshDevices();
    this.jobsSubscription = this.jobEvents.updates$.subscribe(data => { this.setJobsResponse(data); this.syncElapsedTimer(data); });
  }

  ngOnDestroy(): void {
    this.jobsSubscription?.unsubscribe();
    this.elapsedTick?.unsubscribe();
  }

  /** Démarre/arrête le chronomètre d'enregistrement selon l'état du job actif. */
  private syncElapsedTimer(data: JobsResponse): void {
    const active = (data.active?.kind === 'recording' ? data.active : null)
      ?? data.items.find(job => job.kind === 'recording' && ['queued', 'running', 'stopping'].includes(job.state))
      ?? null;
    if (!active) {
      if (this.lastActiveJobId !== null) { this.lastActiveJobId = null; this.resetElapsed(); }
      return;
    }
    if (active.id !== this.lastActiveJobId) {
      // Nouvel enregistrement : on repart de zéro et on (re)démarre le tick horloge.
      this.lastActiveJobId = active.id;
      this.elapsedStartMs = active.started_at ? Date.parse(active.started_at) : null;
      this.startElapsedTicker();
      return;
    }
    if (!this.elapsedStartMs && active.started_at) {
      // La capture vient juste de démarrer (started_at rempli par le backend).
      this.elapsedStartMs = Date.parse(active.started_at);
    }
    if (!this.elapsedTick) this.startElapsedTicker();
  }

  private startElapsedTicker(): void {
    this.elapsedTick?.unsubscribe();
    this.updateElapsedLabel();
    this.elapsedTick = interval(1000).subscribe(() => { this.updateElapsedLabel(); this.cdr.markForCheck(); });
  }

  private resetElapsed(): void {
    this.elapsedTick?.unsubscribe();
    this.elapsedTick = undefined;
    this.elapsedStartMs = null;
    this.elapsedLabel.set('00:00');
  }

  private updateElapsedLabel(): void {
    let seconds = 0;
    if (this.elapsedStartMs !== null && Number.isFinite(this.elapsedStartMs)) {
      seconds = Math.max(0, Math.floor((Date.now() - this.elapsedStartMs) / 1000));
    }
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    const pad = (value: number) => String(value).padStart(2, '0');
    this.elapsedLabel.set(hours > 0 ? `${hours}:${pad(minutes)}:${pad(secs)}` : `${pad(minutes)}:${pad(secs)}`);
  }

  private applyPreferences(): void {
    const ui = this.preferences.preferences()?.ui;
    if (!ui) return;
    this.microphone = ui.microphone;
    this.output = ui.output;
    const storedSources = Array.isArray(ui.audio_sources) ? ui.audio_sources : [];
    if (storedSources.length) {
      this.selectedAudioSources.set(storedSources.map(source => ({ ...source })));
    } else {
      const legacySources: AudioSourceSelection[] = [];
      if (ui.capture_microphone) legacySources.push({ kind: 'microphone', device_id: '', device_name: ui.microphone || '' });
      if (ui.capture_windows) legacySources.push({ kind: 'output', device_id: '', device_name: ui.output || '' });
      this.selectedAudioSources.set(legacySources.length ? legacySources : [{ kind: 'microphone', device_id: '', device_name: '' }]);
    }
    this.syncLegacySourceFlags();
    this.hydrateSavedSourceIds();
    this.normalizeWindows = ui.normalize_windows;
    this.normalizeGain = ui.normalize_windows_max_gain_db;
    this.workflow = ui.recording_workflow;
    this.importAction = ui.import_action;
  }

  refreshDevices(): void {
    this.deviceStatus.set('Détection des périphériques…');
    this.api.devices().subscribe({
      next: devices => {
        this.devices.set(devices);
        this.hydrateSavedSourceIds();
        this.deviceStatus.set(`${devices.microphones.length} microphone(s), ${devices.outputs.length} sortie(s)`);
      },
      error: error => { this.deviceStatus.set('Périphériques indisponibles'); this.toast.show(error.message, 'error'); },
    });
  }

  private hydrateSavedSourceIds(): void {
    const devices = this.devices();
    const microphones = devices.microphone_devices ?? devices.microphones.map(name => ({ id: '', name }));
    const outputs = devices.output_devices ?? devices.outputs.map(name => ({ id: '', name }));
    let changed = false;
    this.selectedAudioSources.update(sources => sources.map(source => {
      if (source.device_id || !source.device_name) return source;
      const list = source.kind === 'microphone' ? microphones : outputs;
      const matches = list.filter(device => device.name === source.device_name);
      // Never guess when a system reports duplicate display names: the backend
      // will require a unique name until the user picks an endpoint with an ID.
      if (matches.length !== 1 || !matches[0].id) return source;
      changed = true;
      return { ...source, device_id: matches[0].id };
    }));
    if (changed) {
      this.syncLegacySourceFlags();
      this.persistUiPreferences();
    }
  }

  refreshJobs(): void { this.api.jobs().subscribe({ next: data => this.setJobsResponse(data), error: error => this.toast.show(error.message, 'error') }); }

  private setJobsResponse(data: JobsResponse): void {
    this.jobsResponse.set(data);
    const maxPage = Math.max(1, Math.ceil(this.jobs().length / this.pageSize));
    if (this.jobsPage() > maxPage) this.jobsPage.set(maxPage);
  }

  private settingsForJob(settings: GlimioSettings): GlimioSettings {
    const support = providerSupportsTranscriptionLanguage(this.providers(), settings.transcription_provider);
    const language = support === false || settings.language === 'detect' ? 'auto' : settings.language;
    const providerOptions = { ...settings.provider_options };
    for (const [providerId, overrides] of Object.entries(this.perJobOverrides())) {
      providerOptions[providerId] = { ...(providerOptions[providerId] ?? {}), ...overrides };
    }
    return { ...settings, language, provider_options: providerOptions };
  }

  activeTranscriptionProvider(): ProviderStatus | undefined {
    const id = this.settings()?.transcription_provider;
    return this.providers()?.find(provider => provider.id === id);
  }

  providerText(provider: ProviderStatus, value: string): string {
    const language = this.preferences.preferences()?.ui.language ?? 'fr';
    return provider.translations?.[language]?.[value] ?? value;
  }

  hasPerJobOptions(provider: ProviderStatus): boolean { return provider.options.some(option => option.per_job); }


  /** Only route to settings when a provider required by the chosen workflow is not ready. */
  setupIssues(): ProviderSetupIssue[] {
    const settings = this.settings();
    const providers = this.providers();
    if (!settings || providers === null) return [];
    const hasSelectedFile = this.selectedFile() !== null;
    // Recording without post-processing must not require transcription/model resources.
    const processingRequested = hasSelectedFile || this.workflow !== 'none';
    if (!processingRequested) return [];
    const required: Array<{ task: ProviderStatus['task']; id?: string; label: string; fallbackProviderId?: string }> = [
      { task: 'transcription', id: settings.transcription_provider, label: 'transcription' },
    ];
    const needsSummary = hasSelectedFile ? this.importAction === 'process' : this.workflow === 'summary';
    if (needsSummary) required.push({ task: 'generation', id: settings.text_provider, label: 'résumés' });
    if (hasSelectedFile) required.push({ task: 'media', id: settings.media_provider, label: 'import audio/vidéo' });
    if (settings.audio_enhancement_provider && settings.audio_enhancement_provider !== 'no-enhancement') {
      required.push({ task: 'enhancement', id: settings.audio_enhancement_provider, label: 'amélioration audio' });
    }
    if (settings.source_separation_provider && settings.source_separation_provider !== 'no-separation') {
      required.push({ task: 'separation', id: settings.source_separation_provider, label: 'séparation des voix' });
    }
    if (settings.diarize) required.push({ task: 'diarization', id: settings.diarization_provider, label: 'diarisation' });

    const requiredEmbeddingIds = requiredProviderIdsForTask(
      providers,
      settings.source_separation_provider,
      'speaker_embedding',
    );
    const embeddingProviderMismatch = requiredEmbeddingIds.length > 0
      && !requiredEmbeddingIds.includes(settings.speaker_embedding_provider);
    for (const requiredProviderId of requiredEmbeddingIds) {
      const requiredProvider = providers.find(provider => provider.id === requiredProviderId);
      required.push({
        task: 'speaker_embedding', id: requiredProviderId,
        label: requiredProvider?.name ?? requiredProviderId,
        fallbackProviderId: settings.source_separation_provider,
      });
    }

    const unique = new Map<string, ProviderSetupIssue>();
    for (const item of required) {
      const provider = providers.find(candidate => candidate.task === item.task && (!item.id || candidate.id === item.id));
      const key = `${item.task}:${item.id ?? 'default'}`;
      if (!provider) {
        const missingProviderId = item.id ?? '';
        unique.set(key, {
          key,
          message: `${item.label} : provider indisponible`,
          providerId: missingProviderId,
          fallbackProviderId: item.fallbackProviderId ?? missingProviderId,
          requiredProviderIds: missingProviderId ? [missingProviderId] : [],
        });
      } else if (!provider.ready) {
        const dependencyIds = missingProviderDependencyIds(provider);
        const resourceIssues = provider.missing.filter(value => !/^(?:provider requis|required provider)\s*:/i.test(value));
        const reason = resourceIssues.length ? `${provider.message} — ${resourceIssues.join(', ')}` : provider.message;
        unique.set(key, {
          key,
          message: `${item.label} : ${reason}`,
          providerId: provider.id,
          fallbackProviderId: provider.id,
          requiredProviderIds: dependencyIds,
        });
      }
    }
    if (embeddingProviderMismatch) {
      unique.set('separation-identity-config', {
        key: 'separation-identity-config',
        message: 'Le provider de séparation nécessite un provider d’identité vocale spécifique dans les paramètres.',
        providerId: settings.source_separation_provider,
        fallbackProviderId: settings.source_separation_provider,
        requiredProviderIds: requiredEmbeddingIds,
        linkTask: 'speaker_embedding',
      });
    }
    return [...unique.values()];
  }

  /** Import needs the selected media provider; report it before uploading a large file. */
  readonly mediaImportBlocked = computed(() => {
    const providers = this.providers();
    const settings = this.settings();
    if (providers === null || !settings) return false;
    const media = providers.find(provider => provider.task === 'media' && provider.id === settings.media_provider);
    return !media || !media.ready;
  });

  perJobValues(provider: ProviderStatus): Record<string, unknown> {
    return { ...(this.settings()?.provider_options[provider.id] ?? {}), ...(this.perJobOverrides()[provider.id] ?? {}) };
  }

  patchPerJobProviderOption(provider: ProviderStatus, key: string, value: unknown): void {
    this.perJobOverrides.update(all => ({ ...all, [provider.id]: { ...(all[provider.id] ?? {}), [key]: value } }));
  }

  supportsTranscriptionLanguage(): boolean {
    const providerId = this.settings()?.transcription_provider ?? '';
    return providerSupportsTranscriptionLanguage(this.providers(), providerId) === true;
  }

  patchSetting<K extends keyof GlimioSettings>(key: K, value: GlimioSettings[K]): void {
    const current = this.preferences.preferences();
    if (!current) return;
    this.preferences.updatePreferences({ ...current, settings: { ...current.settings, [key]: value } });
    if (key === 'processing_profile') this.perJobOverrides.set({});
  }

  numberValue(value: string | number): number { return Number(value); }
  formatLabel(value: string): string { return summaryFormatLabel(value); }
  formatDescription(value: string): string { return summaryFormatDescription(value); }
  profileDescription(profile: GlimioSettings['processing_profile']): string {
    return ({
      turbo: 'Petits budgets, peu de reprises et sans relecture finale : le plus rapide, avec moins de détails.',
      balanced: 'Budgets équilibrés et relecture finale : bon compromis pour la plupart des séances.',
      quality: 'Budgets plus larges et davantage de reprises : résultats plus détaillés, traitement plus long.',
      'pixel-perfect': 'Budgets et découpages maximaux : très détaillé, mais nettement plus lent. La qualité dépend aussi du modèle.',
      custom: 'Les réglages avancés de génération sont accessibles dans Paramètres.',
    } as Record<GlimioSettings['processing_profile'], string>)[profile];
  }

  private syncLegacySourceFlags(): void {
    const sources = this.selectedAudioSources();
    this.captureMicrophone = sources.some(source => source.kind === 'microphone');
    this.captureWindows = sources.some(source => source.kind === 'output');
    this.microphone = sources.find(source => source.kind === 'microphone')?.device_name ?? '';
    this.output = sources.find(source => source.kind === 'output')?.device_name ?? '';
  }

  changeSourceKind(kind: AudioSourceKind): void {
    this.sourceKindToAdd.set(kind);
    this.sourceDeviceId.set('');
  }

  addAudioSource(): void {
    const kind = this.sourceKindToAdd();
    const devices = this.availableDevices();
    const selectedDeviceKey = this.sourceDeviceId();
    const device = selectedDeviceKey ? devices.find(item => (item.key || item.id) === selectedDeviceKey) : null;
    const id = device?.id ?? '';
    const name = device?.name ?? '';
    const normalizedName = name.trim().toLocaleLowerCase();
    const exists = this.selectedAudioSources().some(source => {
      if (source.kind !== kind) return false;
      if (id && source.device_id) return source.device_id === id;
      return source.device_name.trim().toLocaleLowerCase() === normalizedName;
    });
    if (exists) {
      this.toast.show('Cette source est déjà dans la liste.', 'error');
      return;
    }
    if (this.selectedAudioSources().length >= 16) {
      this.toast.show('La limite est de 16 sources audio par séance.', 'error');
      return;
    }
    this.selectedAudioSources.update(sources => [...sources, { kind, device_id: id, device_name: name }]);
    this.syncLegacySourceFlags();
    this.persistUiPreferences();
  }

  removeAudioSource(index: number): void {
    if (this.selectedAudioSources().length <= 1) return;
    this.selectedAudioSources.update(sources => sources.filter((_, itemIndex) => itemIndex !== index));
    this.syncLegacySourceFlags();
    this.persistUiPreferences();
  }

  sourceDisplayName(source: AudioSourceSelection): string {
    const list = source.kind === 'microphone'
      ? (this.devices().microphone_devices ?? [])
      : (this.devices().output_devices ?? []);
    const actual = list.find(device => source.device_id && device.id === source.device_id);
    return actual?.name || source.device_name || 'Périphérique par défaut';
  }

  sourceKindLabel(kind: AudioSourceKind): string { return kind === 'microphone' ? 'Microphone' : 'Sortie audio Windows'; }

  persistUiPreferences(): void {
    const current = this.preferences.preferences();
    if (!current) return;
    this.syncLegacySourceFlags();
    const next: PreferencesPayload = { ...current, ui: { ...current.ui, microphone: this.microphone, output: this.output, capture_microphone: this.captureMicrophone, capture_windows: this.captureWindows, audio_sources: this.selectedAudioSources().map(source => ({ ...source })), normalize_windows: this.normalizeWindows, normalize_windows_max_gain_db: Number(this.normalizeGain), recording_workflow: this.workflow, import_action: this.importAction } };
    this.preferences.updatePreferences(next);
  }

  startRecording(): void {
    this.persistUiPreferences();
    const preferences = this.preferences.preferences();
    if (!preferences) { this.toast.show('Les paramètres ne sont pas encore chargés.', 'error'); return; }
    if (!this.selectedAudioSources().length) {
      this.toast.show('Ajoutez au moins une source audio avant de démarrer.', 'error');
      return;
    }
    this.starting.set(true);
    const autoTranscribe = this.workflow === 'transcribe';
    const autoPv = this.workflow === 'summary';
    this.api.startRecording({
      title: this.title, microphone: this.microphone, output: this.output,
      capture_microphone: this.captureMicrophone, capture_windows: this.captureWindows,
      sources: this.selectedAudioSources().map(source => ({ ...source })),
      normalize_windows: this.normalizeWindows, normalize_windows_max_gain_db: Number(this.normalizeGain),
      auto_transcribe: autoTranscribe, auto_pv: autoPv, settings: this.settingsForJob(preferences.settings),
    }).subscribe({
      next: () => { this.toast.show('Enregistrement lancé.', 'success'); this.starting.set(false); this.refreshJobs(); },
      error: error => { this.toast.show(`Impossible de démarrer l’enregistrement : ${error.message}`, 'error'); this.starting.set(false); },
    });
  }

  stopRecording(): void {
    this.api.stopRecording().subscribe({ next: () => { this.toast.show('Arrêt demandé.', 'success'); this.refreshJobs(); }, error: error => this.toast.show(error.message, 'error') });
  }

  selectFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.acceptSelectedFile(file);
    // Let users select the same file again after an unsuccessful import.
    input.value = '';
  }

  private acceptSelectedFile(file: File | null): void {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024 * 1024) {
      this.toast.show('Le fichier dépasse la limite de 5 Go.', 'error');
      return;
    }
    const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
    const accepted = ['mp3', 'wav', 'm4a', 'flac', 'ogg', 'aac', 'opus', 'mp4', 'mkv', 'webm', 'mov', 'avi', 'mpeg', 'mpg'];
    if (!file.type.startsWith('audio/') && !file.type.startsWith('video/') && !accepted.includes(extension)) {
      this.toast.show('Format non pris en charge. Choisissez un fichier audio ou vidéo.', 'error');
      return;
    }
    this.selectedFile.set(file);
  }

  readonly fileDragging = signal(false);
  onFileDragOver(event: DragEvent): void { event.preventDefault(); this.fileDragging.set(true); }
  onFileDragLeave(event: DragEvent): void {
    const currentTarget = event.currentTarget;
    const related = event.relatedTarget;
    if (!(currentTarget instanceof HTMLElement) || !(related instanceof Node) || !currentTarget.contains(related)) this.fileDragging.set(false);
  }
  onFileDrop(event: DragEvent): void {
    event.preventDefault(); this.fileDragging.set(false);
    const file = event.dataTransfer?.files?.[0] ?? null;
    this.acceptSelectedFile(file);
  }
  fileSizeLabel(file: File): string {
    if (file.size >= 1024 ** 3) return `${(file.size / 1024 ** 3).toFixed(2)} Go`;
    if (file.size >= 1024 ** 2) return `${(file.size / 1024 ** 2).toFixed(1)} Mo`;
    return `${Math.max(1, Math.round(file.size / 1024))} Ko`;
  }

  importFile(): void {
    this.persistUiPreferences();
    const file = this.selectedFile();
    const preferences = this.preferences.preferences();
    if (!file || !preferences) return;
    if (this.mediaImportBlocked()) {
      this.toast.show('Import impossible : le moteur d’importation sélectionné n’est pas prêt. Vérifiez ses dépendances dans les paramètres.', 'error');
      return;
    }
    this.importing.set(true);
    this.api.importFile(file, this.settingsForJob(preferences.settings), this.importAction, this.normalizeWindows, Number(this.normalizeGain)).subscribe({
      next: () => { this.toast.show('Fichier ajouté à la file de traitement.', 'success'); this.importing.set(false); this.selectedFile.set(null); const fileInput = document.getElementById('import-file') as HTMLInputElement | null; if (fileInput) fileInput.value = ''; this.refreshJobs(); },
      error: error => { this.toast.show(`Échec de l’import : ${error.message}`, 'error'); this.importing.set(false); },
    });
  }

  jobLabel(job: Job): string { return ({ recording: 'Enregistrement', transcribe: 'Transcription Whisper', summarize: 'Résumé', process: 'Traitement complet', 'translate-summary': 'Traduction du résumé', import: 'Import audio / vidéo' } as Record<string, string>)[job.kind] ?? job.kind; }
  stateLabel(state: string): string { return ({ queued: 'Dans la file', running: 'En cours', stopping: 'Finalisation', completed: 'Terminé', cancelled: 'Annulé', error: 'Erreur' } as Record<string, string>)[state] ?? state; }
  isDeletable(job: Job): boolean { return !['running', 'stopping', 'queued'].includes(job.state); }
  hasDeletableJobs(): boolean { return this.jobs().some(job => this.isDeletable(job)); }

  deleteJob(job: Job): void {
    this.api.deleteJob(job.id).subscribe({ next: () => { this.toast.show('Activité effacée.', 'success'); this.refreshJobs(); }, error: error => this.toast.show(error.message, 'error') });
  }

  clearHistory(): void {
    if (!this.hasDeletableJobs() || !window.confirm('Effacer l’historique des activités terminées ? Les traitements actifs seront conservés.')) return;
    this.api.clearJobHistory().subscribe({ next: result => { this.jobsPage.set(1); this.toast.show(`${result.deleted} activité(s) effacée(s).`, 'success'); this.refreshJobs(); }, error: error => this.toast.show(error.message, 'error') });
  }
}
