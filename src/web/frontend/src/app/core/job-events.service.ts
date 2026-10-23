import { Injectable } from '@angular/core';
import { Observable, Subject, shareReplay, throttleTime } from 'rxjs';
import { Job, JobsResponse, SearchResult } from './api.models';

/** Coalesce the job stream so bursty providers cannot re-render the whole UI per token. */
const JOB_UPDATE_THROTTLE_MS = 100;
const PASSIVE_JOB_STATES = new Set(['completed', 'error', 'cancelled', 'interrupted']);

/** One shared Server-Sent Events connection for live processing job updates. */
@Injectable({ providedIn: 'root' })
export class JobEventsService {
  private readonly searchUpdates = new Subject<SearchResult>();
  readonly searchUpdates$ = this.searchUpdates.asObservable();
  private readonly artifactUpdates = new Subject<{ session_id: string; kind: 'summary' | 'transcript'; revision?: string }>();
  readonly artifactUpdates$ = this.artifactUpdates.asObservable();

  readonly updates$ = new Observable<JobsResponse>(observer => {
    const source = new EventSource('/api/events');
    let current: JobsResponse = { items: [] };

    source.addEventListener('snapshot', event => {
      try {
        current = JSON.parse((event as MessageEvent<string>).data) as JobsResponse;
        observer.next(current);
      } catch {
        // Ignore malformed events; EventSource will deliver the next snapshot on reconnect.
      }
    });

    source.addEventListener('job', event => {
      try {
        const job = JSON.parse((event as MessageEvent<string>).data) as Job;
        const byId = new Map(current.items.map(item => [item.id, item]));
        const existing = byId.get(job.id);
        // A delayed update must not reopen a job that already reached a terminal
        // state. Recordings are exempt because they legitimately transition on stop.
        if (existing && PASSIVE_JOB_STATES.has(existing.state)
            && !PASSIVE_JOB_STATES.has(job.state) && job.kind !== 'recording') {
          return;
        }
        byId.set(job.id, job);
        const items = [...byId.values()].sort((left, right) => (right.created_at ?? '').localeCompare(left.created_at ?? ''));
        const recording = items.find(item => item.kind === 'recording' && ['running', 'stopping'].includes(item.state)) ?? null;
        const running = items.find(item => item.kind !== 'recording' && item.state === 'running') ?? null;
        current = {
          ...current,
          items,
          active: recording,
          queue: {
            ...current.queue,
            waiting: items.filter(item => item.kind !== 'recording' && item.state === 'queued').length,
            running,
            serial: true,
          },
        };
        observer.next(current);
      } catch {
        // Ignore malformed events; EventSource will deliver the next snapshot on reconnect.
      }
    });

    source.addEventListener('search', event => {
      try {
        this.searchUpdates.next(JSON.parse((event as MessageEvent<string>).data) as SearchResult);
      } catch {
        // Ignore malformed events; the next search update carries the current state.
      }
    });

    source.addEventListener('artifact', event => {
      try {
        const update = JSON.parse((event as MessageEvent<string>).data) as {
          session_id: string; kind: 'summary' | 'transcript'; revision?: string;
        };
        if (update.session_id && ['summary', 'transcript'].includes(update.kind)) this.artifactUpdates.next(update);
      } catch {
        // Ignore malformed events; the next artifact update will refresh the preview.
      }
    });

    // EventSource reconnects automatically. Keep the observable alive while the
    // connection is retried so pages retain the latest state.
    return () => source.close();
  }).pipe(
    throttleTime(JOB_UPDATE_THROTTLE_MS, undefined, { leading: true, trailing: true }),
    shareReplay({ bufferSize: 1, refCount: true }),
  );
}
