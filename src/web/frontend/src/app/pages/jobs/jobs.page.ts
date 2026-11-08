import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Job, JobsResponse } from '../../core/api.models';
import { ToastService } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { JobEventsService } from '../../core/job-events.service';

@Component({
  standalone: true,
  imports: [IconComponent, PaginationComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './jobs.page.html',
  styleUrl: './jobs.page.scss',
})
export class JobsPageComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly jobEvents = inject(JobEventsService);
  private readonly toast = inject(ToastService);
  private jobsSubscription?: Subscription;
  readonly response = signal<JobsResponse | null>(null);
  readonly loading = signal(true);
  readonly loadingError = signal('');
  readonly cancelingIds = signal<ReadonlySet<string>>(new Set());
  readonly deletingIds = signal<ReadonlySet<string>>(new Set());
  readonly historyPage = signal(1);
  readonly historyPageSize = 8;
  readonly jobs = computed(() => {
    const response = this.response();
    const unique = new Map<string, Job>();
    for (const job of [...(response?.items ?? []), response?.active, response?.queue?.running]) {
      if (job && ['queued', 'running', 'stopping'].includes(job.state)) unique.set(job.id, job);
    }
    return [...unique.values()].sort((left, right) => {
      if (left.state === 'queued' && right.state === 'queued') return (left.queue_position ?? Number.MAX_SAFE_INTEGER) - (right.queue_position ?? Number.MAX_SAFE_INTEGER);
      if (left.state === 'queued') return 1;
      if (right.state === 'queued') return -1;
      return (left.created_at ?? '').localeCompare(right.created_at ?? '');
    });
  });
  readonly historyJobs = computed(() => (this.response()?.items ?? [])
    .filter(job => !['queued', 'running', 'stopping'].includes(job.state))
    .sort((left, right) => (right.created_at ?? '').localeCompare(left.created_at ?? '')));
  readonly visibleHistoryJobs = computed(() => this.historyJobs().slice(
    (this.historyPage() - 1) * this.historyPageSize,
    this.historyPage() * this.historyPageSize,
  ));
  readonly hasHistory = computed(() => this.historyJobs().length > 0);

  ngOnInit(): void {
    this.jobsSubscription = this.jobEvents.updates$.subscribe(response => this.setResponse(response));
    // REST provides a reliable initial state even when the SSE connection is still opening.
    this.refresh();
  }

  ngOnDestroy(): void { this.jobsSubscription?.unsubscribe(); }

  private setResponse(response: JobsResponse): void {
    this.response.set(response);
    this.loading.set(false);
    this.loadingError.set('');
    const lastPage = Math.max(1, Math.ceil(this.historyJobs().length / this.historyPageSize));
    if (this.historyPage() > lastPage) this.historyPage.set(lastPage);
  }

  refresh(): void {
    this.loading.set(true);
    this.loadingError.set('');
    this.api.jobs().subscribe({
      next: response => this.setResponse(response),
      error: error => {
        this.loading.set(false);
        this.loadingError.set(`Impossible de récupérer les traitements : ${error.message}`);
      },
    });
  }

  jobLabel(job: Job): string {
    return ({ recording: 'Enregistrement', transcribe: 'Transcription Whisper', summarize: 'Résumé', process: 'Traitement complet', 'translate-summary': 'Traduction du résumé', import: 'Import audio / vidéo' } as Record<string, string>)[job.kind] ?? job.kind;
  }

  stateLabel(job: Job): string {
    if (job.state === 'queued') return job.queue_position ? `En attente · ${job.queue_position}` : 'En attente';
    return ({
      running: 'En cours', stopping: 'Annulation…', completed: 'Terminé', cancelled: 'Annulé', error: 'Erreur',
    } as Record<string, string>)[job.state] ?? job.state;
  }

  historyIcon(job: Job): string {
    return job.state === 'completed' ? 'check-circle' : 'x-mark';
  }

  canDelete(job: Job): boolean {
    return !['queued', 'running', 'stopping'].includes(job.state);
  }

  deleteHistoryItem(job: Job): void {
    this.deletingIds.update(ids => new Set(ids).add(job.id));
    this.api.deleteJob(job.id).subscribe({
      next: () => { this.toast.show('Activité effacée.', 'success'); this.refresh(); },
      error: error => this.toast.show(`Impossible d’effacer l’activité : ${error.message}`, 'error'),
    }).add(() => this.deletingIds.update(ids => { const next = new Set(ids); next.delete(job.id); return next; }));
  }

  clearHistory(): void {
    if (!this.hasHistory() || !window.confirm('Effacer l’historique des traitements terminés ? Les tâches actives seront conservées.')) return;
    this.api.clearJobHistory().subscribe({
      next: result => { this.historyPage.set(1); this.toast.show(`${result.deleted} activité(s) effacée(s).`, 'success'); this.refresh(); },
      error: error => this.toast.show(`Impossible d’effacer l’historique : ${error.message}`, 'error'),
    });
  }

  canCancel(job: Job): boolean {
    return ['queued', 'running'].includes(job.state) && (job.kind !== 'recording' || job.phase === 'recording');
  }

  cancel(job: Job): void {
    this.cancelingIds.update(ids => new Set(ids).add(job.id));
    this.api.cancelJob(job.id).subscribe({
      next: () => { this.toast.show('Annulation demandée.', 'success'); this.refresh(); },
      error: error => this.toast.show(`Impossible d’annuler le traitement : ${error.message}`, 'error'),
    }).add(() => this.cancelingIds.update(ids => { const next = new Set(ids); next.delete(job.id); return next; }));
  }
}
