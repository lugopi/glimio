import { ChangeDetectionStrategy, Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom, Subscription } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { GlimioSettings, Job, JobsResponse, ProcessingInfo, ProviderStatus, SessionArtifact, SessionDetail, SessionPage, SessionSummary } from '../../core/api.models';
import { LibraryStateService } from '../../core/library-state.service';
import { PreferencesService } from '../../core/preferences.service';
import { ToastService } from '../../core/toast.service';
import { CheckboxFieldComponent } from '../../shared/checkbox-field.component';
import { IconComponent } from '../../shared/icon.component';
import { SelectableListComponent } from '../../shared/selectable-list.component';
import { AudioTrackItemComponent } from '../../shared/audio-track-item.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { ProviderOptionsComponent } from '../../shared/provider-options.component';
import { DocumentExportService } from '../../shared/document-export.service';
import { renderMarkdownToHtml } from '../../shared/markdown';
import { estimateRemainingProcessingSeconds, type ProcessingDurationSample } from '../../shared/processing-eta';
import { ProgressiveTextReveal, codePointLength, codePointTailHash, sliceCodePoints } from '../../shared/progressive-text';
import { providerSupportsTranscriptionLanguage, transcriptionLanguageOptions } from '../../shared/transcription-languages';
import { SummaryTranslationLanguageCode, summaryLanguageLabel as getSummaryLanguageLabel, summaryLanguageOptions, summaryTranslationOptions } from '../../shared/summary-languages';
import { summaryFormatDescription, summaryFormatLabel, summaryFormatOptions } from '../../shared/summary-formats';
import { JobEventsService } from '../../core/job-events.service';

const ARTIFACT_REFRESH_DEBOUNCE_MS = 100;
const ARTIFACT_TAIL_CODE_POINTS = 64;

@Component({
  standalone: true,
    imports: [AudioTrackItemComponent, FormsModule, DecimalPipe, RouterLink, CheckboxFieldComponent, IconComponent, PaginationComponent, ProviderOptionsComponent, SelectableListComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library.page.html',
  styleUrl: './library.page.scss',
})
export class LibraryPageComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly jobEvents = inject(JobEventsService);
  private readonly route = inject(ActivatedRoute);
  private readonly preferences = inject(PreferencesService);
  private readonly libraryState = inject(LibraryStateService);
  private readonly toast = inject(ToastService);
  private readonly documentExport = inject(DocumentExportService);
  readonly sessions = signal<SessionSummary[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(25);
  readonly selectedId = signal<string | null>(null);
  readonly selected = signal<SessionDetail | null>(null);
  readonly fullProcessStartingSessionId = signal<string | null>(null);
  readonly mobileDetailOpen = signal(false);
  readonly working = signal(false);
  readonly sessionSettingsSaving = signal(false);
  readonly sessionSettings = signal<GlimioSettings | null>(null);
  private readonly jobHistory = signal<Job[]>([]);
  readonly etaNow = signal(Date.now());
  private etaRefreshTimer?: number;
  readonly providers = signal<ProviderStatus[] | null>(null);
  readonly transcriptionLanguages = computed(() => transcriptionLanguageOptions(this.preferences.preferences()?.ui.language ?? 'fr'));
  readonly formats = summaryFormatOptions.map(option => option.code);
  readonly summaryLanguages = summaryLanguageOptions;
  readonly summaryTranslationLanguages = summaryTranslationOptions;
  readonly availableSummaryTranslations = computed(() => this.selected()?.summary_translations ?? []);
  readonly artifactLanguage = signal<'source' | SummaryTranslationLanguageCode>('source');
  readonly translationTarget = signal<SummaryTranslationLanguageCode>('en');
  readonly speakerCounts = [...Array.from({ length: 20 }, (_, index) => index + 1), 25, 30, 40, 50, 100];
  readonly artifactTitle = signal('');
  readonly artifactContent = signal('');
  readonly artifactKind = signal<'summary' | 'transcript' | null>(null);
  readonly artifactLoading = signal(false);
  readonly artifactPending = signal(false);
  readonly summaryEditing = signal(false);
  readonly summaryDraft = signal('');
  readonly summarySaving = signal(false);
  readonly revealedChars = signal(0);
  readonly artifactVisibleContent = computed(() => sliceCodePoints(this.artifactContent(), this.revealedChars()));
  readonly artifactHtml = computed(() => renderMarkdownToHtml(this.artifactVisibleContent()));
  readonly artifactLive = signal(false);
  private artifactRequest = 0;
  private artifactRevision: string | null = null;
  private readonly revealedByKind: Record<'summary' | 'transcript', number> = { summary: 0, transcript: 0 };
  private readonly reveal = new ProgressiveTextReveal(count => {
    this.revealedChars.set(count);
    const kind = this.artifactKind();
    if (kind) this.revealedByKind[kind] = count;
  });
  private artifactRefreshTimer?: number;
  private artifactRefreshQueued = false;
  private artifactRefreshRunning = false;
  private pendingArtifactKind: 'summary' | 'transcript' | null = null;
  private destroyed = false;
  private liveArtifactPhaseKey = '';
  private liveArtifactPhaseFollowed = false;
  private readonly seenSessionJobs = new Set<string>();
  query = '';
  filter = 'all';
  private searchTimer?: number;
  private settingsSaveTimer?: number;
  private pendingSettingsSave: { sessionId: string; settings: GlimioSettings } | null = null;
  private settingsSaveChain: Promise<void> = Promise.resolve();
  private pendingSessionId: string | null = null;
  private translationJob: { id: string; sessionId: string; language: SummaryTranslationLanguageCode } | null = null;
  private initialized = false;
  private jobsSubscription?: Subscription;
  private artifactSubscription?: Subscription;
  readonly pageItems = computed(() => this.sessions());
  readonly sessionTrackKey = (session: SessionSummary, _index: number) => session.id;
  readonly sessionIsHighlighted = (session: SessionSummary) => this.selectedId() === session.id;
  readonly sessionsWithSummary = computed(() => this.sessions().filter(session => session.summary).length);

  providerText(provider: ProviderStatus, value: string): string {
    const language = this.preferences.preferences()?.ui.language ?? 'fr';
    return provider.translations?.[language]?.[value] ?? value;
  }

  ngOnInit(): void {
    this.etaRefreshTimer = window.setInterval(() => this.etaNow.set(Date.now()), 30_000);
    this.api.providers().subscribe({ next: response => this.providers.set(response.providers), error: () => this.providers.set([]) });
    this.route.queryParamMap.subscribe(params => {
      const requestedId = params.get('session');
      if (requestedId) {
        this.pendingSessionId = requestedId;
        this.query = '';
        this.filter = 'all';
        this.loadSessions(true);
      } else if (!this.initialized) {
        this.loadSessions();
      }
      this.initialized = true;
    });

    this.jobsSubscription = this.jobEvents.updates$.subscribe(response => this.handleJobUpdates(response));
    this.artifactSubscription = this.jobEvents.artifactUpdates$.subscribe(update => this.handleArtifactUpdate(update));
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.artifactRefreshQueued = false;
    this.jobsSubscription?.unsubscribe();
    this.artifactSubscription?.unsubscribe();
    this.reveal.destroy();
    window.clearTimeout(this.searchTimer);
    window.clearTimeout(this.artifactRefreshTimer);
    if (this.etaRefreshTimer !== undefined) window.clearInterval(this.etaRefreshTimer);
    void this.flushPendingSessionSettings().catch(() => undefined);
  }

  @HostListener('document:click', ['$event'])
  closeActionMenusOnOutsideClick(event: MouseEvent): void {
    const target = event.target;
    if (!(target instanceof Node)) return;
    document.querySelectorAll<HTMLDetailsElement>('details.session-actions-menu[open]').forEach(menu => {
      if (!menu.contains(target)) menu.open = false;
    });
  }

  @HostListener('document:keydown.escape')
  closeActionMenusOnEscape(): void {
    document.querySelectorAll<HTMLDetailsElement>('details.session-actions-menu[open]').forEach(menu => {
      menu.open = false;
    });
  }

  processingStateLabel(state: string, phase: string): string {
    if (state === 'stopping' && phase === 'finalizing') return 'Finalisation';
    if (state === 'running') {
      const activePhaseLabels: Record<string, string> = {
        starting: 'Préparation', preparing: 'Préparation', importing: 'Importation',
        transcribing: 'Transcription en cours', summarizing: 'Génération du résumé', translating: 'Traduction du résumé',
        diarizing: 'Diarisation en cours',
        processing: 'Traitement', recording: 'Enregistrement', finalizing: 'Finalisation',
        completed: 'Terminé', cancelled: 'Annulé', error: 'Échec',
      };
      return activePhaseLabels[phase] ?? 'En cours';
    }
    return ({
      queued: 'En attente', running: 'En cours', stopping: 'Arrêt en cours',
      completed: 'Terminé', error: 'Échec', cancelled: 'Annulé', interrupted: 'Interrompu',
      'recovery-error': 'Erreur de reprise', failed: 'Échec',
    } as Record<string, string>)[state] ?? state;
  }

  sessionProcessingActive(): boolean {
    const processing = this.selected()?.processing;
    return Boolean(processing?.active || processing && ['queued', 'running', 'stopping'].includes(processing.state));
  }

  processingActionDisabled(): boolean {
    return this.working() || this.sessionProcessingActive();
  }

  isFullProcessActive(): boolean {
    const sessionId = this.selectedId();
    const processing = this.selected()?.processing;
    return Boolean(sessionId && this.fullProcessStartingSessionId() === sessionId)
      || Boolean(processing?.kind === 'process' && processing.active);
  }

  searchChanged(): void {
    window.clearTimeout(this.searchTimer);
    this.searchTimer = window.setTimeout(() => this.loadSessions(true), 250);
  }

  loadSessions(reset = false): void {
    if (reset) this.page.set(1);
    const offset = (this.page() - 1) * this.pageSize();
    this.api.sessions({ query: this.query, filter: this.filter, limit: this.pageSize(), offset }).subscribe({
      next: (result: SessionPage) => {
        this.sessions.set(result.items);
        this.total.set(result.count);
        this.libraryState.total.set(result.count);
        if (this.page() > 1 && result.items.length === 0 && result.count > 0) { this.page.set(Math.max(1, Math.ceil(result.count / this.pageSize()))); this.loadSessions(); return; }
        const requestedId = this.pendingSessionId;
        this.pendingSessionId = null;
        const currentId = requestedId ?? this.selectedId();
        if (requestedId) this.openSession(requestedId, true);
        else if (currentId && result.items.some(item => item.id === currentId)) {
          if (this.selectedId() !== currentId || !this.selected()) this.openSession(currentId);
        }
        else if (result.items[0]) this.openSession(result.items[0].id);
        else { this.selectedId.set(null); this.selected.set(null); }
      },
      error: error => this.toast.show(`Impossible de charger la bibliothèque : ${error.message}`, 'error'),
    });
  }

  changePage(next: number): void { this.page.set(next); this.loadSessions(); }
  changePageSize(value: number): void { this.pageSize.set(Number(value)); this.page.set(1); this.loadSessions(); }

  openSession(id: string, showOnMobile = false): void {
    if (this.summarySaving()) {
      this.toast.show('Enregistrement du résumé en cours. Attendez sa fin avant de changer de séance.', 'info');
      return;
    }
    if (this.summaryEditing()) {
      this.toast.show('Enregistrez ou annulez les modifications du résumé avant de changer de séance ou de recharger son détail.', 'info');
      return;
    }
    this.summaryEditing.set(false);
    this.summaryDraft.set('');
    const changingSession = this.selectedId() !== id;
    if (changingSession) {
      this.artifactLanguage.set('source');
      void this.flushPendingSessionSettings().catch(error => this.toast.show(`Impossible d’enregistrer les options : ${error.message}`, 'error'));
      this.sessionSettings.set(null);
      this.liveArtifactPhaseKey = '';
      this.liveArtifactPhaseFollowed = false;
      this.pendingArtifactKind = null;
    }
    this.selectedId.set(id);
    if (showOnMobile) this.mobileDetailOpen.set(true);
    this.artifactRequest++;
    this.artifactRevision = null;
    this.artifactKind.set(null);
    this.artifactTitle.set('');
    this.reveal.reset();
    this.revealedByKind.summary = 0;
    this.revealedByKind.transcript = 0;
    this.revealedChars.set(0);
    this.artifactLive.set(false);
    window.clearTimeout(this.artifactRefreshTimer);
    this.artifactRefreshTimer = undefined;
    this.artifactRefreshQueued = false;
    this.artifactContent.set('');
    this.artifactLoading.set(false);
    this.artifactPending.set(false);
    this.api.session(id).subscribe({
      next: detail => {
        if (this.destroyed || this.selectedId() !== id) return;
        this.selected.set(detail);
        const fallback = this.preferences.preferences()?.settings;
        const stored = detail.metadata?.['processing_settings'];
        const saved = stored && typeof stored === 'object' ? stored as Partial<GlimioSettings> : null;
        this.sessionSettings.set(fallback ? { ...fallback, ...(saved ?? {}) } : saved as GlimioSettings | null);
        const pendingKind = this.pendingArtifactKind;
        this.pendingArtifactKind = null;
        const firstArtifact = pendingKind && detail[pendingKind]
          ? pendingKind
          : detail.summary ? 'summary' : detail.transcript ? 'transcript' : null;
        if (firstArtifact) this.loadArtifact(firstArtifact);
        this.followProcessingArtifact(detail);
      },
      error: error => { if (this.selectedId() === id) this.toast.show(error.message, 'error'); },
    });
  }

  backToSessionList(): void {
    this.mobileDetailOpen.set(false);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.querySelector<HTMLElement>('.selectable-list-row.is-highlighted')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    });
  }

  patchSessionSetting<K extends keyof GlimioSettings>(key: K, value: GlimioSettings[K]): void {
    const current = this.sessionSettings();
    if (current) {
      this.sessionSettings.set({ ...current, [key]: value });
      this.scheduleSessionSettingsSave();
    }
  }

  sessionTranscriptionProvider(): ProviderStatus | undefined {
    const providerId = this.sessionSettings()?.transcription_provider ?? this.preferences.preferences()?.settings.transcription_provider;
    return this.providers()?.find(provider => provider.id === providerId);
  }

  hasPerJobOptions(provider: ProviderStatus): boolean { return provider.options.some(option => option.per_job); }

  patchSessionProviderOption(provider: ProviderStatus, key: string, value: unknown): void {
    const current = this.sessionSettings();
    if (!current) return;
    const providerOptions = current.provider_options ?? {};
    this.sessionSettings.set({
      ...current,
      provider_options: { ...providerOptions, [provider.id]: { ...(providerOptions[provider.id] ?? {}), [key]: value } },
    });
    this.scheduleSessionSettingsSave();
  }

  private settingsForJob(settings: GlimioSettings): GlimioSettings {
    const support = providerSupportsTranscriptionLanguage(this.providers(), settings.transcription_provider);
    const language = support === false || settings.language === 'detect' ? 'auto' : settings.language;
    return { ...settings, language };
  }

  supportsTranscriptionLanguage(): boolean {
    const providerId = this.sessionSettings()?.transcription_provider
      ?? this.preferences.preferences()?.settings.transcription_provider
      ?? '';
    return providerSupportsTranscriptionLanguage(this.providers(), providerId) === true;
  }

  numberValue(value: string | number): number { return Number(value); }
  formatLabel(value: string): string { return summaryFormatLabel(value); }
  formatDescription(value: string): string { return summaryFormatDescription(value); }

  private scheduleSessionSettingsSave(): void {
    const sessionId = this.selectedId();
    const settings = this.sessionSettings();
    if (!sessionId || !settings) return;
    this.pendingSettingsSave = { sessionId, settings };
    window.clearTimeout(this.settingsSaveTimer);
    this.settingsSaveTimer = window.setTimeout(() => {
      this.settingsSaveTimer = undefined;
      void this.flushPendingSessionSettings().catch(error => this.toast.show(`Impossible d’enregistrer les options : ${error.message}`, 'error'));
    }, 450);
  }

  private flushPendingSessionSettings(): Promise<void> {
    window.clearTimeout(this.settingsSaveTimer);
    this.settingsSaveTimer = undefined;
    const pending = this.pendingSettingsSave;
    this.pendingSettingsSave = null;
    if (!pending) return this.settingsSaveChain;
    return this.persistSessionSettings(pending.sessionId, pending.settings);
  }

  private persistSessionSettings(sessionId: string, settings: GlimioSettings): Promise<void> {
    const save = this.settingsSaveChain.catch(() => undefined).then(async () => {
      this.sessionSettingsSaving.set(true);
      try {
        const result = await firstValueFrom(this.api.saveSessionSettings(sessionId, settings));
        if (this.selectedId() === sessionId) {
          this.selected.update(current => current ? { ...current, metadata: result.metadata } : current);
        }
      } finally {
        this.sessionSettingsSaving.set(false);
      }
    });
    this.settingsSaveChain = save;
    return save;
  }

  runJob(action: 'transcribe' | 'summarize' | 'process', force = false): void {
    if (this.sessionProcessingActive()) return;
    if (this.summaryEditing()) { this.toast.show('Enregistrez ou annulez les modifications du résumé avant de lancer un traitement.', 'info'); return; }
    const session = this.selected(); const settings = this.sessionSettings() ?? this.preferences.preferences()?.settings;
    if (!session || !settings) { this.toast.show('Les paramètres ne sont pas encore disponibles.', 'error'); return; }
    this.liveArtifactPhaseKey = '';
    this.liveArtifactPhaseFollowed = false;
    if (action === 'process') this.fullProcessStartingSessionId.set(session.id);
    this.revealedByKind.summary = 0;
    this.revealedByKind.transcript = 0;
    this.working.set(true);
    void this.flushPendingSessionSettings().catch(() => undefined)
      .then(() => this.persistSessionSettings(session.id, settings))
      .then(() => firstValueFrom(this.api.startSessionJob(action, session.id, this.settingsForJob(settings), force)))
      .then(job => {
        if (this.selectedId() === session.id) {
          this.selected.update(current => current ? { ...current, processing: this.processingInfo(job) } : current);
          this.openSession(session.id);
        }
        if (this.fullProcessStartingSessionId() === session.id) this.fullProcessStartingSessionId.set(null);
        this.toast.show('Traitement ajouté à la file avec les options de cette séance.', 'success');
        this.working.set(false);
      })
      .catch(error => {
        const message = error?.message ?? String(error);
        this.toast.show(message.startsWith('Impossible d’enregistrer les options') ? message : `Impossible d’enregistrer les options : ${message}`, 'error');
        if (this.fullProcessStartingSessionId() === session.id) this.fullProcessStartingSessionId.set(null);
        this.working.set(false);
      });
  }

  translateSummary(targetLanguage: string): void {
    const target = this.summaryTranslationLanguages.find(option => option.code === targetLanguage)?.code;
    if (!target) {
      this.toast.show('Choisissez une langue cible prise en charge.', 'error');
      return;
    }
    if (this.sessionProcessingActive() || this.working() || this.summaryEditing()) return;
    const session = this.selected();
    const baseSettings = this.sessionSettings() ?? this.preferences.preferences()?.settings;
    if (!session || !session.summary || !baseSettings) {
      this.toast.show('Aucun résumé existant à traduire.', 'error');
      return;
    }
    this.translationTarget.set(target);
    this.working.set(true);
    const translationSettings = { ...baseSettings, summary_language: target };
    void this.flushPendingSessionSettings().catch(() => undefined)
      .then(() => firstValueFrom(this.api.startSessionJob(
        'translate-summary', session.id, this.settingsForJob(translationSettings), false,
      )))
      .then(job => {
        this.translationJob = { id: job.id, sessionId: session.id, language: target };
        if (this.selectedId() === session.id) {
          this.selected.update(current => current ? { ...current, processing: this.processingInfo(job) } : current);
        }
        this.toast.show('Traduction du résumé ajoutée à la file.', 'success');
        this.working.set(false);
      })
      .catch(error => {
        this.toast.show(`Impossible de lancer la traduction : ${error?.message ?? String(error)}`, 'error');
        this.working.set(false);
      });
  }

  loadSummaryVersion(language: string): void {
    if (this.summaryEditing() || !this.selected()?.summary) return;
    if (language === 'source') {
      this.loadArtifact('summary', 'source');
      return;
    }
    const translation = this.summaryTranslationLanguages.find(option => option.code === language)?.code;
    if (translation && this.availableSummaryTranslations().includes(translation)) {
      this.loadArtifact('summary', translation);
    }
  }

  summaryLanguageLabel(language: string): string {
    return getSummaryLanguageLabel(language);
  }

  renameSession(): void {
    const session = this.selected(); if (!session || this.sessionProcessingActive() || this.summaryEditing()) return;
    const title = window.prompt('Nouveau titre de la séance', session.title)?.trim();
    if (!title || title === session.title) return;
    this.api.renameSession(session.id, title).subscribe({ next: () => { this.toast.show('Séance renommée.', 'success'); this.loadSessions(); }, error: error => this.toast.show(error.message, 'error') });
  }

  deleteSession(): void {
    const session = this.selected(); if (!session || this.sessionProcessingActive() || this.summaryEditing()) return;
    if (!window.confirm(`Supprimer définitivement la séance « ${session.title} » et ses fichiers ?`)) return;
    this.api.deleteSession(session.id).subscribe({ next: () => { this.toast.show('Séance supprimée.', 'success'); this.selected.set(null); this.selectedId.set(null); this.loadSessions(true); }, error: error => this.toast.show(error.message, 'error') });
  }

  trackLabel(filename: string): string {
    const rawSources = this.selected()?.metadata?.['audio_sources'];
    if (!Array.isArray(rawSources)) return filename;
    const source = rawSources.find((item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === 'object' && (item as Record<string, unknown>)['filename'] === filename,
    );
    if (!source) return filename;
    const name = typeof source['name'] === 'string' ? source['name'].trim() : '';
    const kind = source['kind'] === 'microphone' ? 'Microphone' : source['kind'] === 'output' ? 'Sortie audio' : 'Source audio';
    const suffixMatch = filename.match(/-(\d+)\.wav$/i);
    const suffix = suffixMatch ? ` · piste ${suffixMatch[1]}` : '';
    return `${kind}${name ? ` — ${name}` : ''}${suffix}`;
  }

  canDisableAudioTrack(filename: string): boolean {
    if (this.isAudioTrackDisabled(filename)) return true;
    const active = (this.selected()?.audio_tracks ?? []).filter(track => !this.isAudioTrackDisabled(track));
    return active.length > 1;
  }

  isAudioTrackDisabled(filename: string): boolean {
    const disabled = this.selected()?.metadata?.['disabled_audio_tracks'];
    return Array.isArray(disabled) && disabled.includes(filename);
  }

  audioArtifactsStale(): boolean {
    const metadata = this.selected()?.metadata;
    return metadata?.['audio_transcript_stale'] === true || metadata?.['audio_summary_stale'] === true;
  }

  setAudioTrackDisabled(filename: string, disabled: boolean): void {
    const session = this.selected();
    if (!session || this.sessionProcessingActive() || this.summaryEditing()) return;
    this.working.set(true);
    this.api.setAudioTrackDisabled(session.id, filename, disabled).subscribe({
      next: result => {
        if (this.selectedId() === session.id) {
          this.selected.update(current => current ? { ...current, metadata: result.metadata } : current);
        }
        this.toast.show(disabled ? 'Piste désactivée pour les prochains traitements. Le fichier est conservé.' : 'Piste réactivée.', 'success');
        this.working.set(false);
      },
      error: error => { this.toast.show(`Impossible de modifier la piste : ${error.message}`, 'error'); this.working.set(false); },
    });
  }

  deleteAudioTrack(filename: string): void {
    const session = this.selected();
    if (!session || this.sessionProcessingActive() || this.summaryEditing()) return;
    const isLastTrack = (session.audio_tracks ?? []).length <= 1;
    const lastTrackWarning = isLastTrack
      ? '\n\nC’est la dernière piste audio. Après suppression, il sera impossible de régénérer la transcription ou le résumé à partir de cette séance, sauf si vous réimportez une source audio.'
      : '';
    const approved = window.confirm(
      `Supprimer définitivement « ${filename} » ?\n\nLe fichier audio et sa transcription individuelle éventuelle seront supprimés. Le résumé et la transcription globale existants seront conservés, mais peuvent toujours contenir les informations de cette piste et seront signalés comme obsolètes. Cette action est irréversible.${lastTrackWarning}`,
    );
    if (!approved) return;
    this.working.set(true);
    this.api.deleteAudioTrack(session.id, filename).subscribe({
      next: result => {
        if (this.selectedId() === session.id) {
          this.selected.update(current => current ? {
            ...current,
            audio_tracks: result.audio_tracks,
            audio: result.audio_tracks.length > 0,
            metadata: result.metadata,
            files: current.files ? { ...current.files, audio_tracks: result.audio_tracks } : current.files,
          } : current);
        }
        this.toast.show(result.warnings?.length ? `Piste supprimée. ${result.warnings.join(' ')}` : 'Piste audio supprimée.', result.warnings?.length ? 'info' : 'success');
        this.working.set(false);
        this.loadSessions();
      },
      error: error => { this.toast.show(`Impossible de supprimer la piste : ${error.message}`, 'error'); this.working.set(false); },
    });
  }

  artifactTabsDisabled(): boolean {
    if (this.summaryEditing()) return true;
    if (!this.isFullProcessActive()) return false;
    const processing = this.selected()?.processing;
    // Once transcription is complete, let the user inspect the finished transcript
    // and follow the live summary instead of leaving both tabs inert.
    return !(processing?.active && processing.phase === 'summarizing');
  }

  onArtifactTabKeydown(event: KeyboardEvent, current: 'summary' | 'transcript'): void {
    if (this.artifactTabsDisabled() || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const session = this.selected();
    if (!session) return;
    const available: Array<'summary' | 'transcript'> = [];
    if (session.summary) available.push('summary');
    if (session.transcript) available.push('transcript');
    if (!available.length) return;
    const currentIndex = Math.max(0, available.indexOf(current));
    const targetIndex = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? available.length - 1
        : (currentIndex + (event.key === 'ArrowRight' ? 1 : -1) + available.length) % available.length;
    const target = available[targetIndex];
    event.preventDefault();
    this.loadArtifact(target);
    document.getElementById(`artifact-tab-${target}`)?.focus();
  }

  startSummaryEdit(): void {
    const session = this.selected();
    if (!session || !session.summary || this.artifactKind() !== 'summary'
        || this.sessionProcessingActive() || this.isFullProcessActive() || this.artifactLoading() || this.artifactPending()
        || !this.artifactContent().trim()) return;
    this.summaryDraft.set(this.artifactContent());
    this.summaryEditing.set(true);
  }

  cancelSummaryEdit(): void {
    if (this.summarySaving()) return;
    this.summaryEditing.set(false);
    this.summaryDraft.set('');
  }

  saveSummaryEdit(): void {
    const session = this.selected();
    const content = this.summaryDraft();
    if (!session || this.artifactKind() !== 'summary' || this.sessionProcessingActive() || this.isFullProcessActive()
        || this.summarySaving() || !content.trim() || !this.artifactRevision) return;
    this.summarySaving.set(true);
    this.api.saveSessionSummary(session.id, content, this.artifactRevision).subscribe({
      next: result => {
        this.summarySaving.set(false);
        if (this.selectedId() !== session.id) return;
        const savedContent = result.content ?? content;
        const length = codePointLength(savedContent);
        this.artifactContent.set(savedContent);
        this.artifactRevision = result.revision;
        this.artifactLive.set(false);
        this.revealedByKind.summary = length;
        this.reveal.reset(length);
        this.revealedChars.set(length);
        this.summaryEditing.set(false);
        this.summaryDraft.set('');
        this.selected.update(current => current ? { ...current, summary: true } : current);
        this.toast.show('Résumé enregistré.', 'success');
        this.loadSessions();
      },
      error: error => {
        this.summarySaving.set(false);
        this.toast.show(`Impossible d’enregistrer le résumé : ${error.message}`, 'error');
      },
    });
  }

  exportSummaryMarkdown(): void {
    const session = this.selected();
    if (!session || this.artifactKind() !== 'summary' || this.summaryEditing()) return;
    this.documentExport.downloadMarkdown(this.artifactContent(), session.title, session.id);
    this.toast.show('Résumé exporté au format Markdown.', 'success');
  }

  printSummaryPdf(): void {
    const session = this.selected();
    if (!session || this.artifactKind() !== 'summary' || this.summaryEditing()) return;
    if (!this.documentExport.openPrintView(this.artifactContent(), session.title)) {
      this.toast.show('Autorisez les fenêtres contextuelles pour imprimer ou enregistrer le résumé en PDF.', 'info');
    }
  }

  loadArtifact(kind: 'summary' | 'transcript', summaryLanguage?: string): void {
    if (this.summaryEditing() && this.artifactKind() !== kind) return;
    const session = this.selected();
    if (!session || session.id !== this.selectedId()
        || (kind === 'summary' && !session.summary)
        || (kind === 'transcript' && !session.transcript)) return;
    const requestedLanguage = kind === 'summary'
      ? (summaryLanguage ?? this.artifactLanguage())
      : 'source';
    const translation = requestedLanguage !== 'source' ? requestedLanguage : null;
    if (kind === 'summary') this.artifactLanguage.set(requestedLanguage as 'source' | SummaryTranslationLanguageCode);
    const request = ++this.artifactRequest;
    window.clearTimeout(this.artifactRefreshTimer);
    this.artifactRefreshTimer = undefined;
    this.artifactRefreshQueued = false;
    this.artifactRevision = null;
    this.artifactKind.set(kind);
    this.artifactTitle.set(kind === 'summary' ? 'Résumé' : 'Transcription');
    const base = this.revealedByKind[kind];
    this.reveal.reset(base);
    this.revealedChars.set(base);
    this.artifactContent.set('');
    this.artifactLoading.set(true);
    this.artifactPending.set(false);
    this.artifactLive.set(false);
    this.api.sessionArtifact(session.id, kind, null, undefined, null, translation).subscribe({
      next: result => {
        if (this.destroyed || request !== this.artifactRequest || this.selectedId() !== session.id) return;
        this.applyArtifactResult(result, true);
      },
      error: error => {
        if (this.destroyed || request !== this.artifactRequest || this.selectedId() !== session.id) return;
        this.artifactLoading.set(false);
        this.artifactPending.set(false);
        this.toast.show(error.message, 'error');
      },
    });
  }

  private applyArtifactResult(result: SessionArtifact, initial: boolean): void {
    this.artifactRevision = result.revision;
    this.artifactPending.set(Boolean(result.pending));
    this.artifactLive.set(Boolean(result.live));
    if (!result.pending && !result.unchanged && result.content !== undefined) {
      if (result.append && !initial) this.artifactContent.update(content => content + result.content!);
      else if (!result.append) this.artifactContent.set(result.content);
    }
    const total = codePointLength(this.artifactContent());
    const base = Math.min(this.revealedByKind[result.kind], total);
    if (this.reveal.revealed !== base) this.reveal.reset(base);
    this.revealedChars.set(base);
    this.reveal.setTarget(total, Boolean(result.live) && !result.pending);
    this.artifactLoading.set(false);
  }

  private handleArtifactUpdate(update: { session_id: string; kind: 'summary' | 'transcript'; revision?: string }): void {
    if (this.selectedId() !== update.session_id) return;
    if (update.kind === 'summary' && this.artifactLanguage() !== 'source') return;
    const selected = this.selected();
    if (!selected || selected.id !== update.session_id) {
      // The detail request is still in flight: remember the kind and load it
      // as soon as the matching session detail is available.
      this.pendingArtifactKind = update.kind;
      return;
    }
    if (!this.artifactKind()) {
      this.selected.update(current => current ? { ...current, [update.kind]: true } : current);
      this.loadArtifact(update.kind);
      return;
    }
    if (this.artifactKind() !== update.kind) return;
    if (update.revision && update.revision === this.artifactRevision) return;
    window.clearTimeout(this.artifactRefreshTimer);
    this.artifactRefreshTimer = window.setTimeout(() => {
      this.artifactRefreshTimer = undefined;
      if (!this.destroyed) void this.refreshArtifact();
    }, ARTIFACT_REFRESH_DEBOUNCE_MS);
  }

  private async refreshArtifact(): Promise<void> {
    if (this.destroyed) return;
    if (this.artifactRefreshRunning) {
      this.artifactRefreshQueued = true;
      return;
    }
    const sessionId = this.selectedId();
    const kind = this.artifactKind();
    if (!sessionId || !kind) return;
    const request = this.artifactRequest;
    const revision = this.artifactRevision;
    const content = this.artifactContent();
    const offset = codePointLength(content);
    const tailHash = offset > 0 ? codePointTailHash(content, ARTIFACT_TAIL_CODE_POINTS) : null;
    this.artifactRefreshRunning = true;
    try {
      const translation = kind === 'summary' && this.artifactLanguage() !== 'source' ? this.artifactLanguage() : null;
      const result = await firstValueFrom(this.api.sessionArtifact(sessionId, kind, revision, offset, tailHash, translation));
      if (this.destroyed || request !== this.artifactRequest
          || this.selectedId() !== sessionId || this.artifactKind() !== kind) return;
      this.applyArtifactResult(result, false);
    } catch {
      // The SSE job state remains authoritative if a preview is not ready yet.
    } finally {
      this.artifactRefreshRunning = false;
      if (this.destroyed) {
        this.artifactRefreshQueued = false;
        return;
      }
      if (this.artifactRefreshQueued) {
        this.artifactRefreshQueued = false;
        this.artifactRefreshTimer = window.setTimeout(() => {
          this.artifactRefreshTimer = undefined;
          if (!this.destroyed) void this.refreshArtifact();
        }, 0);
      }
    }
  }

  private handleJobUpdates(response: JobsResponse): void {
    this.jobHistory.set(response.items);
    const latestBySession = new Map<string, Job>();
    let discoveredSession = false;
    for (const job of response.items) {
      if (!job.session_id) continue;
      const association = `${job.id}:${job.session_id}`;
      if (!this.seenSessionJobs.has(association)) {
        this.seenSessionJobs.add(association);
        if (['recording', 'import'].includes(job.kind)
            && !this.sessions().some(session => session.id === job.session_id)) discoveredSession = true;
      }
      const existing = latestBySession.get(job.session_id);
      if (!existing || (job.updated_at ?? '').localeCompare(existing.updated_at ?? '') > 0) {
        latestBySession.set(job.session_id, job);
      }
    }
    this.sessions.update(items => items.map(item => {
      const job = latestBySession.get(item.id);
      return job ? { ...item, processing: this.processingInfo(job) } : item;
    }));
    if (discoveredSession) this.loadSessions();

    const translation = this.translationJob
      ? response.items.find(item => item.id === this.translationJob!.id)
      : undefined;
    if (translation && !['queued', 'running', 'stopping'].includes(translation.state)) {
      const completedTranslation = this.translationJob!;
      this.translationJob = null;
      if (translation.state === 'completed') {
        if (this.selectedId() === completedTranslation.sessionId) {
          this.artifactLanguage.set(completedTranslation.language);
          this.translationTarget.set(completedTranslation.language);
          this.selected.update(current => current ? {
            ...current,
            summary_translations: [...new Set([...(current.summary_translations ?? []), completedTranslation.language])],
          } : current);
          this.loadArtifact('summary', completedTranslation.language);
        }
        this.toast.show('Traduction du résumé terminée.', 'success');
      } else if (translation.state === 'error' || translation.state === 'cancelled') {
        this.toast.show(translation.error || 'La traduction du résumé n’a pas abouti.', 'error');
      }
    }

    const sessionId = this.selectedId();
    const current = this.selected();
    if (!sessionId || !current) return;
    const job = latestBySession.get(sessionId);
    if (!job) return;
    const nextProcessing = this.processingInfo(job);
    const previous = current.processing;
    const phaseChanged = previous?.job_id !== nextProcessing.job_id || previous?.phase !== nextProcessing.phase;
    const finished = previous?.active === true && previous.job_id === nextProcessing.job_id && !nextProcessing.active;
    this.selected.set({ ...current, processing: nextProcessing });

    if (phaseChanged || finished) {
      this.api.session(sessionId).subscribe({
        next: detail => {
          const latest = this.selected();
          if (this.selectedId() !== sessionId || !latest || latest.processing?.job_id !== job.id
              || latest.processing.phase !== nextProcessing.phase) return;
          this.selected.set(detail);
          if (finished) {
            this.settleArtifactsAfterProcessing(detail);
            this.loadSessions();
          } else {
            this.followProcessingArtifact(detail);
          }
        },
        error: () => { /* Job status continues to update from the event stream. */ },
      });
    } else if (nextProcessing.active) {
      this.followProcessingArtifact({ ...current, processing: nextProcessing });
    }
  }

  private processingInfo(job: Job): ProcessingInfo {
    return {
      job_id: job.id,
      kind: job.kind,
      state: job.state,
      phase: job.phase,
      active: ['queued', 'running', 'stopping'].includes(job.state),
      message: job.message ?? 'Traitement en cours…',
      error: job.error,
      started_at: job.started_at,
      finished_at: job.finished_at,
    };
  }

  processingEtaLabel(processing: ProcessingInfo): string | null {
    if (!processing.active || !processing.started_at) return null;
    const startedAt = Date.parse(processing.started_at);
    const now = this.etaNow();
    if (!Number.isFinite(startedAt) || startedAt > now) return null;

    const session = this.selected();
    const sessionId = this.selectedId();
    if (!session || !sessionId) return null;

    // The current session's duration is authoritative even when it is not on the current page.
    const audioDurations = new Map<string, number>();
    for (const item of this.sessions()) {
      if (Number.isFinite(item.duration_seconds) && (item.duration_seconds ?? 0) > 0) {
        audioDurations.set(item.id, item.duration_seconds!);
      }
    }
    if (Number.isFinite(session.duration_seconds) && (session.duration_seconds ?? 0) > 0) {
      audioDurations.set(sessionId, session.duration_seconds!);
    }

    const samples: ProcessingDurationSample[] = this.jobHistory()
      .filter(job => job.id !== processing.job_id && job.kind === processing.kind && job.state === 'completed'
        && job.started_at && job.finished_at)
      .map(job => {
        const start = Date.parse(job.started_at!);
        const finish = Date.parse(job.finished_at!);
        return {
          sessionId: job.session_id ?? null,
          durationSeconds: (finish - start) / 1000,
          audioDurationSeconds: job.session_id ? audioDurations.get(job.session_id) ?? null : null,
          completedAt: finish,
        };
      });

    const remaining = estimateRemainingProcessingSeconds(
      samples, sessionId, session.duration_seconds, (now - startedAt) / 1000,
    );
    if (remaining === null) return null;

    const estimate = new Date(now + remaining * 1000);
    const locale = document.documentElement.lang === 'en' ? 'en-CH' : 'fr-CH';
    return new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(estimate);
  }

  isArtifactLive(): boolean {
    const kind = this.artifactKind();
    const processing = this.selected()?.processing;
    return Boolean(processing?.active && (
      kind === 'transcript' && processing.phase === 'transcribing'
      || kind === 'summary' && processing.phase === 'summarizing'
    ));
  }

  private followProcessingArtifact(session: SessionDetail): void {
    const processing = session.processing;
    if (!processing?.active) {
      this.liveArtifactPhaseKey = '';
      this.liveArtifactPhaseFollowed = false;
      return;
    }
    const phaseKey = `${processing.job_id}:${processing.phase}`;
    if (phaseKey !== this.liveArtifactPhaseKey) {
      this.liveArtifactPhaseKey = phaseKey;
      this.liveArtifactPhaseFollowed = false;
    }
    const kind = processing.phase === 'transcribing' || processing.phase === 'diarizing'
      ? 'transcript'
      : processing.phase === 'summarizing'
        ? 'summary'
        : null;
    if (!kind || this.liveArtifactPhaseFollowed || !session[kind]) return;
    this.liveArtifactPhaseFollowed = true;
    if (this.artifactKind() !== kind) this.loadArtifact(kind);
  }

  private settleArtifactsAfterProcessing(session: SessionDetail): void {
    const selectedKind = this.artifactKind();
    if (selectedKind && session[selectedKind]) {
      this.loadArtifact(selectedKind);
      return;
    }

    const fallbackKind = session.summary ? 'summary' : session.transcript ? 'transcript' : null;
    if (fallbackKind) {
      this.loadArtifact(fallbackKind);
      return;
    }

    // Invalidate an in-flight preview request and clear content that belonged
    // to the now-finished live artifact (for example after cancellation).
    this.artifactRequest++;
    this.artifactRevision = null;
    this.artifactKind.set(null);
    this.artifactTitle.set('');
    this.reveal.reset();
    this.revealedByKind.summary = 0;
    this.revealedByKind.transcript = 0;
    this.revealedChars.set(0);
    this.artifactLive.set(false);
    this.artifactContent.set('');
    this.artifactLoading.set(false);
    this.artifactPending.set(false);
  }

  durationLabel(value?: number | null): string {
    if (value == null || !Number.isFinite(value) || value < 0) return '—';
    const seconds = Math.floor(value);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    const pad = (n: number) => String(n).padStart(2, '0');
    return hours > 0 ? `${hours}:${pad(minutes)}:${pad(rest)}` : `${pad(minutes)}:${pad(rest)}`;
  }



  dateLabel(value?: string, fallback = ''): string {
    if (!value) return fallback;
    const date = new Date(value);
    const locale = document.documentElement.lang === 'en' ? 'en-CH' : 'fr-CH';
    return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }
  audioUrl(id: string, filename: string): string { return `/api/sessions/${encodeURIComponent(id)}/audio/${encodeURIComponent(filename)}`; }
}
