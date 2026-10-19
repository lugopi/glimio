import { ChangeDetectorRef, ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription, interval, startWith, switchMap } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AudioDevices, GlimioSettings, Job, JobsResponse, PreferencesPayload } from '../../core/api.models';
import { PreferencesService } from '../../core/preferences.service';
import { ToastService } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { PaginationComponent } from '../../shared/pagination.component';

@Component({
  standalone: true,
  imports: [FormsModule, IconComponent, PaginationComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './recording.page.html',
  styleUrl: './recording.page.scss',
})
export class RecordingPageComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly preferences = inject(PreferencesService);
  private readonly toast = inject(ToastService);
  private polling?: Subscription;
  private hasAppliedPreferences = false;
  readonly devices = signal<AudioDevices>({ microphones: [], outputs: [] });
  readonly deviceStatus = signal('Périphériques non vérifiés');
  readonly jobsResponse = signal<JobsResponse | null>(null);
  readonly jobs = computed(() => this.jobsResponse()?.items ?? []);
  readonly settings = computed(() => this.preferences.preferences()?.settings ?? null);
  readonly formats = ['auto', 'summary', 'daily', 'technical', 'formal', 'brainstorm'];
  readonly speakerCounts = Array.from({ length: 16 }, (_, index) => index + 1);
  readonly visibleJobs = computed(() => this.jobs().slice((this.jobsPage() - 1) * this.pageSize, this.jobsPage() * this.pageSize));
  readonly activeRecording = computed(() => this.jobsResponse()?.active?.kind === 'recording' ? this.jobsResponse()?.active : this.jobs().find(job => job.kind === 'recording' && ['queued', 'running', 'stopping'].includes(job.state)) ?? null);
  /** Libellé d'état de l'enregistrement actif (affiché dans la pastille de statut). */
  readonly recordingStatusText = computed(() => {
    const job = this.activeRecording();
    if (!job) return '';
    if (job.phase === 'preparing') return 'Préparation du micro…';
    if (job.phase === 'finalizing') return 'Finalisation de la séance…';
    if (job.state === 'stopping') return 'Arrêt en cours…';
    return 'Enregistrement en cours';
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
    this.refreshDevices();
    this.refreshJobs();
    this.polling = interval(1500).pipe(startWith(0), switchMap(() => this.api.jobs())).subscribe({
      next: data => { this.jobsResponse.set(data); this.syncElapsedTimer(data); },
      error: error => this.toast.show(`Impossible de récupérer les activités : ${error.message}`, 'error'),
    });
  }

  ngOnDestroy(): void {
    this.polling?.unsubscribe();
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
    this.captureMicrophone = ui.capture_microphone;
    this.captureWindows = ui.capture_windows;
    this.normalizeWindows = ui.normalize_windows;
    this.normalizeGain = ui.normalize_windows_max_gain_db;
    this.workflow = ui.recording_workflow;
    this.importAction = ui.import_action;
  }

  refreshDevices(): void {
    this.deviceStatus.set('Détection des périphériques…');
    this.api.devices().subscribe({
      next: devices => { this.devices.set(devices); this.deviceStatus.set(`${devices.microphones.length} microphone(s), ${devices.outputs.length} sortie(s)`); },
      error: error => { this.deviceStatus.set('Périphériques indisponibles'); this.toast.show(error.message, 'error'); },
    });
  }

  refreshJobs(): void { this.api.jobs().subscribe({ next: data => this.jobsResponse.set(data), error: error => this.toast.show(error.message, 'error') }); }

  private settingsForJob(settings: GlimioSettings): GlimioSettings {
    const language = settings.language === 'detect'
      ? 'auto'
      : settings.language === 'auto'
        ? (document.documentElement.lang.toLowerCase().startsWith('en') ? 'en' : 'fr')
        : settings.language;
    return { ...settings, language };
  }

  patchSetting<K extends keyof GlimioSettings>(key: K, value: GlimioSettings[K]): void {
    const current = this.preferences.preferences();
    if (!current) return;
    this.preferences.updatePreferences({ ...current, settings: { ...current.settings, [key]: value } });
  }

  numberValue(value: string | number): number { return Number(value); }
  formatLabel(value: string): string { return ({ auto: 'Automatique', summary: 'Synthèse générale', daily: 'Compte rendu', technical: 'Technique', formal: 'Formel', brainstorm: 'Brainstorming' } as Record<string, string>)[value] ?? value; }

  persistUiPreferences(): void {
    const current = this.preferences.preferences();
    if (!current) return;
    const next: PreferencesPayload = { ...current, ui: { ...current.ui, microphone: this.microphone, output: this.output, capture_microphone: this.captureMicrophone, capture_windows: this.captureWindows, normalize_windows: this.normalizeWindows, normalize_windows_max_gain_db: Number(this.normalizeGain), recording_workflow: this.workflow, import_action: this.importAction } };
    this.preferences.updatePreferences(next);
  }

  startRecording(): void {
    this.persistUiPreferences();
    const preferences = this.preferences.preferences();
    if (!preferences) { this.toast.show('Les paramètres ne sont pas encore chargés.', 'error'); return; }
    this.starting.set(true);
    const autoTranscribe = this.workflow === 'transcribe';
    const autoPv = this.workflow === 'summary';
    this.api.startRecording({
      title: this.title, microphone: this.microphone, output: this.output,
      capture_microphone: this.captureMicrophone, capture_windows: this.captureWindows,
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

  selectFile(event: Event): void { this.selectedFile.set((event.target as HTMLInputElement).files?.[0] ?? null); }

  importFile(): void {
    this.persistUiPreferences();
    const file = this.selectedFile();
    const preferences = this.preferences.preferences();
    if (!file || !preferences) return;
    this.importing.set(true);
    this.api.importFile(file, this.settingsForJob(preferences.settings), this.importAction).subscribe({
      next: () => { this.toast.show('Fichier ajouté à la file de traitement.', 'success'); this.importing.set(false); this.selectedFile.set(null); this.refreshJobs(); },
      error: error => { this.toast.show(`Échec de l’import : ${error.message}`, 'error'); this.importing.set(false); },
    });
  }

  jobLabel(job: Job): string { return ({ recording: 'Enregistrement', transcribe: 'Transcription Whisper', summarize: 'Résumé', process: 'Traitement complet', import: 'Import audio / vidéo' } as Record<string, string>)[job.kind] ?? job.kind; }
  stateLabel(state: string): string { return ({ queued: 'Dans la file', running: 'En cours', stopping: 'Finalisation', completed: 'Terminé', error: 'Erreur' } as Record<string, string>)[state] ?? state; }
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
