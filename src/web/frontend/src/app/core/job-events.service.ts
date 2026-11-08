import { Injectable } from '@angular/core';
import { Observable, Subject, shareReplay, throttleTime } from 'rxjs';
import { Job, JobsResponse, SearchResult } from './api.models';

/** Coalesce the job stream so bursty providers cannot re-render the whole UI per token. */
const JOB_UPDATE_THROTTLE_MS = 100;
const PASSIVE_JOB_STATES = new Set(['completed', 'error', 'cancelled', 'interrupted']);
const JOB_STATES = new Set(['queued', 'running', 'stopping', 'completed', 'cancelled', 'error']);
const SEARCH_STATES = new Set(['queued', 'running', 'cancelling', 'completed', 'cancelled', 'error']);

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNullableRecord(value: unknown, guard: (candidate: unknown) => boolean): boolean {
  return value === null || guard(value);
}

function isPhaseDuration(value: unknown): boolean {
  if (!isRecord(value)) return false;
  const phase = value['phase'];
  const duration = value['duration_seconds'];
  return typeof phase === 'string' && typeof duration === 'number' && duration >= 0;
}

function isProviderEvent(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return typeof value['provider_id'] === 'string'
    && typeof value['task'] === 'string'
    && typeof value['stage'] === 'string'
    && typeof value['message'] === 'string'
    && (value['progress'] === null || typeof value['progress'] === 'number')
    && isRecord(value['details']);
}

function isJob(value: unknown): value is Job {
  if (!isRecord(value)) return false;
  const state = value['state'];
  const phaseHistory = value['phase_history'];
  const providerEvent = value['provider_event'];
  const queuePosition = value['queue_position'];
  return typeof value['id'] === 'string'
    && typeof value['kind'] === 'string'
    && typeof value['phase'] === 'string'
    && typeof state === 'string'
    && JOB_STATES.has(state)
    && (value['message'] === undefined || typeof value['message'] === 'string')
    && (phaseHistory === undefined || (Array.isArray(phaseHistory) && phaseHistory.every(isPhaseDuration)))
    && (providerEvent === undefined || providerEvent === null || isProviderEvent(providerEvent))
    && (queuePosition === undefined || queuePosition === null || typeof queuePosition === 'number');
}

function isSearchSource(value: unknown): boolean {
  if (!isRecord(value)) return false;
  const sourceNumber = value['source_number'];
  const sourceId = value['source_id'];
  const citationNumber = value['citation_number'];
  return (typeof sourceNumber === 'number' || typeof sourceNumber === 'string')
    && (sourceId === null || typeof sourceId === 'string')
    && typeof value['included'] === 'boolean'
    && (citationNumber === null || typeof citationNumber === 'number')
    && typeof value['title'] === 'string'
    && typeof value['session_id'] === 'string'
    && typeof value['filename'] === 'string'
    && typeof value['kind'] === 'string'
    && typeof value['text'] === 'string';
}

function isJobsResponse(value: unknown): value is JobsResponse {
  if (!isRecord(value)) return false;
  const items = value['items'];
  const active = value['active'];
  const queue = value['queue'];
  if (!Array.isArray(items) || !items.every(isJob) || !isNullableRecord(active, isJob) || !isRecord(queue)) return false;
  return typeof queue['waiting'] === 'number'
    && queue['waiting'] >= 0
    && isNullableRecord(queue['running'], isJob)
    && typeof queue['serial'] === 'boolean';
}

function isSearchResult(value: unknown): value is SearchResult {
  if (!isRecord(value)) return false;
  const state = value['state'];
  const sources = value['sources'];
  return typeof value['id'] === 'string'
    && typeof state === 'string'
    && SEARCH_STATES.has(state)
    && typeof value['message'] === 'string'
    && typeof value['query'] === 'string'
    && Array.isArray(value['session_ids'])
    && typeof value['sessions_total'] === 'number'
    && typeof value['sessions_scanned'] === 'number'
    && typeof value['passages_found'] === 'number'
    && Array.isArray(sources)
    && sources.every(isSearchSource)
    && (value['answer'] === null || typeof value['answer'] === 'string')
    && (value['llm_error'] === null || typeof value['llm_error'] === 'string')
    && (value['created_at'] === null || typeof value['created_at'] === 'string')
    && (value['updated_at'] === null || typeof value['updated_at'] === 'string')
    && (value['finished_at'] === null || typeof value['finished_at'] === 'string');
}

function parseEvent<T>(event: Event, guard: (value: unknown) => value is T): T | null {
  try {
    const data = (event as MessageEvent<string>).data;
    if (typeof data !== 'string') return null;
    const value: unknown = JSON.parse(data);
    return guard(value) ? value : null;
  } catch {
    return null;
  }
}

/** One shared Server-Sent Events connection for live processing job updates. */
@Injectable({ providedIn: 'root' })
export class JobEventsService {
  private readonly searchUpdates = new Subject<SearchResult>();
  readonly searchUpdates$ = this.searchUpdates.asObservable();
  private readonly artifactUpdates = new Subject<{ session_id: string; kind: 'summary' | 'transcript'; revision?: string }>();
  readonly artifactUpdates$ = this.artifactUpdates.asObservable();

  readonly updates$ = new Observable<JobsResponse>(observer => {
    const source = new EventSource('/api/events');
    let current: JobsResponse = {
      items: [],
      active: null,
      queue: { waiting: 0, running: null, serial: true },
    };

    source.addEventListener('snapshot', event => {
      const snapshot = parseEvent(event, isJobsResponse);
      if (!snapshot) return;
      current = snapshot;
      observer.next(current);
    });

    source.addEventListener('job', event => {
      const job = parseEvent(event, isJob);
      if (!job) return;
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
    });

    source.addEventListener('search', event => {
      const result = parseEvent(event, isSearchResult);
      if (result) this.searchUpdates.next(result);
    });

    source.addEventListener('artifact', event => {
      const update = parseEvent(event, (value): value is { session_id: string; kind: 'summary' | 'transcript'; revision?: string } => {
        if (!isRecord(value)) return false;
        return typeof value['session_id'] === 'string'
          && (value['kind'] === 'summary' || value['kind'] === 'transcript')
          && (value['revision'] === undefined || typeof value['revision'] === 'string');
      });
      if (update) this.artifactUpdates.next(update);
    });

    // EventSource reconnects automatically. Keep the observable alive while the
    // connection is retried so pages retain the latest state.
    return () => source.close();
  }).pipe(
    throttleTime(JOB_UPDATE_THROTTLE_MS, undefined, { leading: true, trailing: true }),
    shareReplay({ bufferSize: 1, refCount: true }),
  );
}
