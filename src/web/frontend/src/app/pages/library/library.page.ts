import { ChangeDetectionStrategy, Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom, Subscription } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { GlimioSettings, Job, JobsResponse, ProcessingInfo, ProviderStatus, SessionDetail, SessionPage, SessionSummary } from '../../core/api.models';
import { LibraryStateService } from '../../core/library-state.service';
import { PreferencesService } from '../../core/preferences.service';
import { ToastService } from '../../core/toast.service';
import { CheckboxFieldComponent } from '../../shared/checkbox-field.component';
import { IconComponent } from '../../shared/icon.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { ProviderOptionsComponent } from '../../shared/provider-options.component';
import { renderMarkdownToHtml } from '../../shared/markdown';
import { providerSupportsTranscriptionLanguage, transcriptionLanguageOptions } from '../../shared/transcription-languages';
import { JobEventsService } from '../../core/job-events.service';

@Component({
  standalone: true,
    imports: [FormsModule, DecimalPipe, RouterLink, CheckboxFieldComponent, IconComponent, PaginationComponent, ProviderOptionsComponent],
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
  readonly sessions = signal<SessionSummary[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(25);
  readonly selectedId = signal<string | null>(null);
  readonly selected = signal<SessionDetail | null>(null);
  readonly mobileDetailOpen = signal(false);
  readonly working = signal(false);
  readonly sessionSettingsSaving = signal(false);
  readonly sessionSettings = signal<GlimioSettings | null>(null);
  private readonly jobHistory = signal<Job[]>([]);
  readonly providers = signal<ProviderStatus[] | null>(null);
  readonly transcriptionLanguages = computed(() => transcriptionLanguageOptions(this.preferences.preferences()?.ui.language ?? 'fr'));
  readonly formats = ['auto', 'summary', 'daily', 'technical', 'formal', 'brainstorm'];
  readonly speakerCounts = [...Array.from({ length: 20 }, (_, index) => index + 1), 25, 30, 40, 50, 100];
  readonly artifactTitle = signal('');
  readonly artifactContent = signal('');
  readonly artifactKind = signal<'summary' | 'transcript' | null>(null);
  readonly artifactLoading = signal(false);
  readonly artifactPending = signal(false);
  readonly artifactHtml = computed(() => renderMarkdownToHtml(this.artifactContent()));
  private artifactRequest = 0;
  private artifactRevision: string | null = null;
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
  private initialized = false;
  private jobsSubscription?: Subscription;
  private artifactSubscription?: Subscription;
  readonly pageItems = computed(() => this.sessions());
  readonly sessionsWithSummary = computed(() => this.sessions().filter(session => session.summary).length);

  ngOnInit(): void {
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
    this.jobsSubscription?.unsubscribe();
    this.artifactSubscription?.unsubscribe();
    window.clearTimeout(this.searchTimer);
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
        transcribing: 'Transcription en cours', summarizing: 'Génération du résumé',
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
    const changingSession = this.selectedId() !== id;
    if (changingSession) {
      void this.flushPendingSessionSettings().catch(error => this.toast.show(`Impossible d’enregistrer les options : ${error.message}`, 'error'));
      this.sessionSettings.set(null);
      this.liveArtifactPhaseKey = '';
      this.liveArtifactPhaseFollowed = false;
    }
    this.selectedId.set(id);
    if (showOnMobile) this.mobileDetailOpen.set(true);
    this.artifactRequest++;
    this.artifactRevision = null;
    this.artifactKind.set(null);
    this.artifactTitle.set('');
    this.artifactContent.set('');
    this.artifactLoading.set(false);
    this.artifactPending.set(false);
    this.api.session(id).subscribe({
      next: detail => {
        if (this.selectedId() !== id) return;
        this.selected.set(detail);
        const fallback = this.preferences.preferences()?.settings;
        const stored = detail.metadata?.['processing_settings'];
        const saved = stored && typeof stored === 'object' ? stored as Partial<GlimioSettings> : null;
        this.sessionSettings.set(fallback ? { ...fallback, ...(saved ?? {}) } : saved as GlimioSettings | null);
        const firstArtifact = detail.summary ? 'summary' : detail.transcript ? 'transcript' : null;
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
        document.querySelector<HTMLElement>('.session-card.is-selected')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
  formatLabel(value: string): string { return ({ auto: 'Automatique', summary: 'Synthèse générale', daily: 'Daily — compte rendu de réunion', technical: 'Technique', formal: 'Formel', brainstorm: 'Brainstorming' } as Record<string, string>)[value] ?? value; }

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
    const session = this.selected(); const settings = this.sessionSettings() ?? this.preferences.preferences()?.settings;
    if (!session || !settings) { this.toast.show('Les paramètres ne sont pas encore disponibles.', 'error'); return; }
    this.liveArtifactPhaseKey = '';
    this.liveArtifactPhaseFollowed = false;
    this.working.set(true);
    void this.flushPendingSessionSettings().catch(() => undefined)
      .then(() => this.persistSessionSettings(session.id, settings))
      .then(() => firstValueFrom(this.api.startSessionJob(action, session.id, this.settingsForJob(settings), force)))
      .then(() => { this.toast.show('Traitement ajouté à la file avec les options de cette séance.', 'success'); this.working.set(false); this.openSession(session.id); })
      .catch(error => {
        const message = error?.message ?? String(error);
        this.toast.show(message.startsWith('Impossible d’enregistrer les options') ? message : `Impossible d’enregistrer les options : ${message}`, 'error');
        this.working.set(false);
      });
  }

  renameSession(): void {
    const session = this.selected(); if (!session || this.sessionProcessingActive()) return;
    const title = window.prompt('Nouveau titre de la séance', session.title)?.trim();
    if (!title || title === session.title) return;
    this.api.renameSession(session.id, title).subscribe({ next: () => { this.toast.show('Séance renommée.', 'success'); this.loadSessions(); }, error: error => this.toast.show(error.message, 'error') });
  }

  deleteSession(): void {
    const session = this.selected(); if (!session || this.sessionProcessingActive()) return;
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
    if (!session || this.sessionProcessingActive()) return;
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
    if (!session || this.sessionProcessingActive()) return;
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

  onArtifactTabKeydown(event: KeyboardEvent, current: 'summary' | 'transcript'): void {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
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

  loadArtifact(kind: 'summary' | 'transcript'): void {
    const session = this.selected();
    if (!session || (kind === 'summary' && !session.summary) || (kind === 'transcript' && !session.transcript)) return;
    const request = ++this.artifactRequest;
    this.artifactRevision = null;
    this.artifactKind.set(kind);
    this.artifactTitle.set(kind === 'summary' ? 'Résumé' : 'Transcription');
    this.artifactContent.set('');
    this.artifactLoading.set(true);
    this.artifactPending.set(false);
    this.api.sessionArtifact(session.id, kind).subscribe({
      next: result => {
        if (request !== this.artifactRequest || this.selectedId() !== session.id) return;
        this.artifactRevision = result.revision;
        this.artifactPending.set(Boolean(result.pending));
        if (!result.pending) this.artifactContent.set(result.content ?? 'Contenu indisponible.');
        this.artifactLoading.set(false);
      },
      error: error => {
        if (request !== this.artifactRequest || this.selectedId() !== session.id) return;
        this.artifactLoading.set(false);
        this.artifactPending.set(false);
        this.toast.show(error.message, 'error');
      },
    });
  }

  private handleArtifactUpdate(update: { session_id: string; kind: 'summary' | 'transcript' }): void {
    if (this.selectedId() !== update.session_id) return;
    if (!this.artifactKind()) {
      this.selected.update(current => current ? { ...current, [update.kind]: true } : current);
      this.loadArtifact(update.kind);
      return;
    }
    if (this.artifactKind() !== update.kind) return;
    const request = ++this.artifactRequest;
    const offset = Array.from(this.artifactContent()).length;
    this.api.sessionArtifact(update.session_id, update.kind, this.artifactRevision, offset).subscribe({
      next: result => {
        if (request !== this.artifactRequest || this.selectedId() !== update.session_id || this.artifactKind() !== update.kind) return;
        if (!result.unchanged) {
          this.artifactRevision = result.revision;
          if (!result.pending && result.content !== undefined) {
            if (result.append) this.artifactContent.update(content => content + result.content);
            else this.artifactContent.set(result.content);
          }
        }
        this.artifactPending.set(Boolean(result.pending));
        this.artifactLoading.set(false);
      },
      error: () => { /* The SSE job state remains authoritative if a preview is not ready yet. */ },
    });
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
    const now = Date.now();
    const startedAt = Date.parse(processing.started_at);
    if (!Number.isFinite(startedAt)) return null;
    const previousDurations = this.jobHistory()
      .filter(job => job.id !== processing.job_id && job.kind === processing.kind && job.state === 'completed' && job.started_at && job.finished_at)
      .map(job => (Date.parse(job.finished_at!) - Date.parse(job.started_at!)) / 1000)
      .filter(duration => Number.isFinite(duration) && duration > 0)
      .slice(0, 7)
      .sort((left, right) => left - right);
    if (!previousDurations.length) return null;
    const middle = Math.floor(previousDurations.length / 2);
    const typicalDuration = previousDurations.length % 2
      ? previousDurations[middle]
      : (previousDurations[middle - 1] + previousDurations[middle]) / 2;
    const remaining = Math.max(0, typicalDuration - (now - startedAt) / 1000);
    const estimate = new Date(now + remaining * 1000);
    const locale = document.documentElement.lang === 'en' ? 'en-CH' : 'fr-CH';
    const time = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(estimate);
    return time;
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
