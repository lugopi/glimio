import { Injectable } from '@angular/core';
import { Observable, Subject, shareReplay } from 'rxjs';
import { Job, JobsResponse, SearchResult } from './api.models';

/** One shared Server-Sent Events connection for live processing job updates. */
@Injectable({ providedIn: 'root' })
export class JobEventsService {
  private readonly searchUpdates = new Subject<SearchResult>();
  readonly searchUpdates$ = this.searchUpdates.asObservable();

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

    // EventSource reconnects automatically. Keep the observable alive while the
    // connection is retried so pages retain the latest state.
    return () => source.close();
  }).pipe(shareReplay({ bufferSize: 1, refCount: true }));
}
