import { ChangeDetectionStrategy, Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { Subscription, catchError, exhaustMap, interval, map, of, startWith, switchMap } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { GlimioSettings, SessionDetail, SessionPage, SessionSummary } from '../../core/api.models';
import { LibraryStateService } from '../../core/library-state.service';
import { PreferencesService } from '../../core/preferences.service';
import { ToastService } from '../../core/toast.service';
import { CheckboxFieldComponent } from '../../shared/checkbox-field.component';
import { IconComponent } from '../../shared/icon.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { renderMarkdownToHtml } from '../../shared/markdown';

@Component({
  standalone: true,
  imports: [FormsModule, RouterLink, CheckboxFieldComponent, IconComponent, PaginationComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library.page.html',
  styleUrl: './library.page.scss',
})
export class LibraryPageComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
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
  readonly sessionSettings = signal<GlimioSettings | null>(null);
  readonly formats = ['auto', 'summary', 'daily', 'technical', 'formal', 'brainstorm'];
  readonly speakerCounts = [...Array.from({ length: 20 }, (_, index) => index + 1), 25, 30, 40, 50, 100];
  readonly artifactTitle = signal('');
  readonly artifactContent = signal('');
  readonly artifactKind = signal<'summary' | 'transcript' | null>(null);
  readonly artifactLoading = signal(false);
  readonly artifactHtml = computed(() => renderMarkdownToHtml(this.artifactContent()));
  private artifactRequest = 0;
  query = '';
  filter = 'all';
  private searchTimer?: number;
  private pendingSessionId: string | null = null;
  private initialized = false;
  private polling?: Subscription;
  readonly pageItems = computed(() => this.sessions());
  readonly sessionsWithSummary = computed(() => this.sessions().filter(session => session.summary).length);

  ngOnInit(): void {
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

    // Job state is live data: refresh the visible list and selected detail while
    // the library is open, without re-opening the session (which clears artifact
    // previews and can overwrite unsaved form state).
    this.polling = interval(2000).pipe(
      startWith(0),
      exhaustMap(() => {
        const options = {
          query: this.query,
          filter: this.filter,
          limit: this.pageSize(),
          offset: (this.page() - 1) * this.pageSize(),
        };
        return this.api.sessions(options).pipe(
          switchMap(result => {
            const id = this.selectedId();
            if (!id) return of({ result, id: null, detail: null });
            return this.api.session(id).pipe(
              map(detail => ({ result, id, detail })),
              catchError(() => of({ result, id, detail: null })),
            );
          }),
          // Keep the interval alive after transient HTTP/network failures.
          catchError(() => of(null)),
        );
      }),
    ).subscribe({
      next: payload => {
        if (!payload) return;
        const { result, id, detail } = payload;
        this.sessions.set(result.items);
        this.total.set(result.count);
        this.libraryState.total.set(result.count);
        if (detail && id && this.selectedId() === id) {
          const previous = this.selected();
          this.selected.set(detail);
          const defaultKind = detail.summary ? 'summary' : detail.transcript ? 'transcript' : null;
          if (!this.artifactKind() && defaultKind) {
            this.loadArtifact(defaultKind);
          } else if (previous?.processing?.active && !detail.processing?.active && this.artifactKind() && (detail.summary || detail.transcript)) {
            const kind = this.artifactKind()!;
            if ((kind === 'summary' && detail.summary) || (kind === 'transcript' && detail.transcript)) this.loadArtifact(kind);
          }
        }
      },
    });
  }

  ngOnDestroy(): void {
    this.polling?.unsubscribe();
    window.clearTimeout(this.searchTimer);
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

  processingStateLabel(state: string): string {
    return ({
      queued: 'En attente', running: 'En cours', stopping: 'Arrêt en cours',
      completed: 'Terminé', error: 'Échec', cancelled: 'Annulé',
    } as Record<string, string>)[state] ?? state;
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
    this.selectedId.set(id);
    if (showOnMobile) this.mobileDetailOpen.set(true);
    this.artifactRequest++;
    this.artifactKind.set(null);
    this.artifactTitle.set('');
    this.artifactContent.set('');
    this.artifactLoading.set(false);
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
      },
      error: error => { if (this.selectedId() === id) this.toast.show(error.message, 'error'); },
    });
  }

  backToSessionList(): void {
    this.mobileDetailOpen.set(false);
    requestAnimationFrame(() => {
      document.querySelector<HTMLElement>('.session-card.is-selected')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  patchSessionSetting<K extends keyof GlimioSettings>(key: K, value: GlimioSettings[K]): void {
    const current = this.sessionSettings();
    if (current) this.sessionSettings.set({ ...current, [key]: value });
  }

  private settingsForJob(settings: GlimioSettings): GlimioSettings {
    const language = settings.language === 'detect'
      ? 'auto'
      : settings.language === 'auto'
        ? (document.documentElement.lang.toLowerCase().startsWith('en') ? 'en' : 'fr')
        : settings.language;
    return { ...settings, language };
  }

  numberValue(value: string | number): number { return Number(value); }
  formatLabel(value: string): string { return ({ auto: 'Automatique', summary: 'Synthèse générale', daily: 'Daily — compte rendu de réunion', technical: 'Technique', formal: 'Formel', brainstorm: 'Brainstorming' } as Record<string, string>)[value] ?? value; }

  saveSessionSettings(): void {
    const session = this.selected(); const settings = this.sessionSettings();
    if (!session || !settings) return;
    this.working.set(true);
    this.api.saveSessionSettings(session.id, settings).subscribe({
      next: result => {
        this.selected.update(current => current ? { ...current, metadata: result.metadata } : current);
        this.toast.show('Options de la séance enregistrées.', 'success');
        this.working.set(false);
      },
      error: error => { this.toast.show(`Impossible d’enregistrer les options : ${error.message}`, 'error'); this.working.set(false); },
    });
  }

  runJob(action: 'transcribe' | 'summarize' | 'process', force = false): void {
    const session = this.selected(); const settings = this.sessionSettings() ?? this.preferences.preferences()?.settings;
    if (!session || !settings) { this.toast.show('Les paramètres ne sont pas encore disponibles.', 'error'); return; }
    this.working.set(true);
    this.api.saveSessionSettings(session.id, settings).subscribe({
      next: () => this.api.startSessionJob(action, session.id, this.settingsForJob(settings), force).subscribe({
        next: () => { this.toast.show('Traitement ajouté à la file avec les options de cette séance.', 'success'); this.working.set(false); this.openSession(session.id); },
        error: error => { this.toast.show(error.message, 'error'); this.working.set(false); },
      }),
      error: error => { this.toast.show(`Impossible d’enregistrer les options : ${error.message}`, 'error'); this.working.set(false); },
    });
  }

  renameSession(): void {
    const session = this.selected(); if (!session) return;
    const title = window.prompt('Nouveau titre de la séance', session.title)?.trim();
    if (!title || title === session.title) return;
    this.api.renameSession(session.id, title).subscribe({ next: () => { this.toast.show('Séance renommée.', 'success'); this.loadSessions(); }, error: error => this.toast.show(error.message, 'error') });
  }

  deleteSession(): void {
    const session = this.selected(); if (!session) return;
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
    if (!session) return;
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
    if (!session) return;
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
    this.artifactKind.set(kind);
    this.artifactTitle.set(kind === 'summary' ? 'Résumé' : 'Transcription');
    this.artifactContent.set('');
    this.artifactLoading.set(true);
    this.api.sessionArtifact(session.id, kind).subscribe({
      next: result => {
        if (request !== this.artifactRequest || this.selectedId() !== session.id) return;
        this.artifactContent.set(result.content ?? 'Contenu indisponible.');
        this.artifactLoading.set(false);
      },
      error: error => {
        if (request !== this.artifactRequest || this.selectedId() !== session.id) return;
        this.artifactLoading.set(false);
        this.toast.show(error.message, 'error');
      },
    });
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
