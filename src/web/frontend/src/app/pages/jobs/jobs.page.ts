import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Job, JobsResponse } from '../../core/api.models';
import { ToastService } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { JobEventsService } from '../../core/job-events.service';

@Component({
  standalone: true,
  imports: [IconComponent],
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
  readonly loadingError = signal('');
  readonly cancelingIds = signal<ReadonlySet<string>>(new Set());
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

  ngOnInit(): void {
    this.jobsSubscription = this.jobEvents.updates$.subscribe(response => { this.response.set(response); this.loadingError.set(''); });
  }

  ngOnDestroy(): void { this.jobsSubscription?.unsubscribe(); }

  refresh(): void {
    this.api.jobs().subscribe({
      next: response => { this.response.set(response); this.loadingError.set(''); },
      error: error => this.loadingError.set(`Impossible de récupérer les traitements : ${error.message}`),
    });
  }

  jobLabel(job: Job): string {
    return ({ recording: 'Enregistrement', transcribe: 'Transcription Whisper', summarize: 'Résumé', process: 'Traitement complet', import: 'Import audio / vidéo' } as Record<string, string>)[job.kind] ?? job.kind;
  }

  stateLabel(job: Job): string {
    if (job.state === 'queued') return job.queue_position ? `En attente · ${job.queue_position}` : 'En attente';
    return ({ running: 'En cours', stopping: 'Annulation…' } as Record<string, string>)[job.state] ?? job.state;
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
