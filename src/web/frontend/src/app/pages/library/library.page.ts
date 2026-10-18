import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { GlimioSettings, SessionDetail, SessionPage, SessionSummary } from '../../core/api.models';
import { LibraryStateService } from '../../core/library-state.service';
import { PreferencesService } from '../../core/preferences.service';
import { ToastService } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { PaginationComponent } from '../../shared/pagination.component';

@Component({
  standalone: true,
  imports: [FormsModule, RouterLink, IconComponent, PaginationComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library.page.html',
  styleUrl: './library.page.scss',
})
export class LibraryPageComponent implements OnInit {
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
  readonly working = signal(false);
  readonly sessionSettings = signal<GlimioSettings | null>(null);
  readonly formats = ['auto', 'summary', 'daily', 'technical', 'formal', 'brainstorm'];
  readonly speakerCounts = Array.from({ length: 16 }, (_, index) => index + 1);
  readonly artifactTitle = signal('');
  readonly artifactContent = signal('');
  query = '';
  filter = 'all';
  private searchTimer?: number;
  private pendingSessionId: string | null = null;
  private initialized = false;
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
        if (requestedId) this.openSession(requestedId);
        else if (currentId && result.items.some(item => item.id === currentId)) this.openSession(currentId);
        else if (result.items[0]) this.openSession(result.items[0].id);
        else { this.selectedId.set(null); this.selected.set(null); }
      },
      error: error => this.toast.show(`Impossible de charger la bibliothèque : ${error.message}`, 'error'),
    });
  }

  changePage(next: number): void { this.page.set(next); this.loadSessions(); }
  changePageSize(value: number): void { this.pageSize.set(Number(value)); this.page.set(1); this.loadSessions(); }

  openSession(id: string): void {
    this.selectedId.set(id);
    this.artifactTitle.set(''); this.artifactContent.set('');
    this.api.session(id).subscribe({
      next: detail => {
        this.selected.set(detail);
        const fallback = this.preferences.preferences()?.settings;
        const stored = detail.metadata?.['processing_settings'];
        const saved = stored && typeof stored === 'object' ? stored as Partial<GlimioSettings> : null;
        this.sessionSettings.set(fallback ? { ...fallback, ...(saved ?? {}) } : saved as GlimioSettings | null);
      },
      error: error => this.toast.show(error.message, 'error'),
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
  formatLabel(value: string): string { return ({ auto: 'Automatique', summary: 'Synthèse générale', daily: 'Compte rendu', technical: 'Technique', formal: 'Formel', brainstorm: 'Brainstorming' } as Record<string, string>)[value] ?? value; }

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
        next: () => { this.toast.show(force ? 'Régénération du résumé ajoutée à la file.' : 'Traitement ajouté à la file avec les options de cette séance.', 'success'); this.working.set(false); this.openSession(session.id); },
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

  loadArtifact(kind: 'summary' | 'transcript'): void {
    const session = this.selected(); if (!session) return;
    this.api.sessionArtifact(session.id, kind).subscribe({
      next: result => { this.artifactTitle.set(({ summary: 'Résumé', transcript: 'Transcription' } as Record<string, string>)[kind]); this.artifactContent.set(result.content ?? 'Contenu indisponible.'); },
      error: error => this.toast.show(error.message, 'error'),
    });
  }

  dateLabel(value?: string, fallback = ''): string {
    if (!value) return fallback;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('fr-CH', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }
  trackLabel(filename: string): string { return filename.toLowerCase().includes('micro') ? 'Microphone' : filename.toLowerCase().includes('windows') ? 'Audio Windows' : filename; }
  audioUrl(id: string, filename: string): string { return `/api/sessions/${encodeURIComponent(id)}/audio/${encodeURIComponent(filename)}`; }
}
