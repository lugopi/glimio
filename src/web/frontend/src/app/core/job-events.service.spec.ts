import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Job, JobState, JobsResponse } from './api.models';
import { JobEventsService } from './job-events.service';

type EventListenerDouble = (event: MessageEvent<string>) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly listeners = new Map<string, Set<EventListenerDouble>>();
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener): void {
    const listeners = this.listeners.get(type) ?? new Set<EventListenerDouble>();
    listeners.add(listener as EventListenerDouble);
    this.listeners.set(type, listeners);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, payload: unknown): void {
    const event = { data: JSON.stringify(payload) } as MessageEvent<string>;
    this.listeners.get(type)?.forEach(listener => listener(event));
  }
}

const snapshot = (items: Job[] = []): JobsResponse => ({
  items,
  active: null,
  queue: { waiting: 0, running: null, serial: true },
});

const job = (id: string, state: JobState, kind = 'process'): Job => ({
  id,
  kind,
  state,
  phase: state,
  created_at: '2026-10-23T10:00:00+00:00',
});

describe('JobEventsService', () => {
  let service: JobEventsService;

  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
    service = new JobEventsService();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('throttles job bursts with a leading and trailing update', () => {
    const responses: JobsResponse[] = [];
    const subscription = service.updates$.subscribe(value => responses.push(value));
    const source = FakeEventSource.instances[0];

    source.emit('snapshot', snapshot([job('job-1', 'queued')]));
    expect(responses).toHaveLength(1);
    vi.advanceTimersByTime(100);

    source.emit('job', job('job-1', 'running'));
    expect(responses).toHaveLength(2);
    expect(responses[1].items[0].state).toBe('running');

    source.emit('job', job('job-1', 'completed'));
    expect(responses).toHaveLength(2);
    vi.advanceTimersByTime(99);
    expect(responses).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(responses).toHaveLength(3);
    expect(responses[2].items[0].state).toBe('completed');

    subscription.unsubscribe();
  });

  it('does not reopen a terminal job from a delayed event', () => {
    const responses: JobsResponse[] = [];
    const subscription = service.updates$.subscribe(value => responses.push(value));
    const source = FakeEventSource.instances[0];

    source.emit('snapshot', snapshot([job('job-1', 'completed')]));
    vi.advanceTimersByTime(100);

    source.emit('job', job('job-1', 'running'));
    vi.advanceTimersByTime(100);
    expect(responses.at(-1)?.items.find(item => item.id === 'job-1')?.state).toBe('completed');

    source.emit('job', job('job-2', 'running'));
    vi.advanceTimersByTime(100);
    expect(responses.at(-1)?.items.find(item => item.id === 'job-2')?.state).toBe('running');

    subscription.unsubscribe();
  });

  it('exempts recordings from the terminal state guard', () => {
    const responses: JobsResponse[] = [];
    const subscription = service.updates$.subscribe(value => responses.push(value));
    const source = FakeEventSource.instances[0];

    source.emit('snapshot', snapshot([job('recording-1', 'completed', 'recording')]));
    vi.advanceTimersByTime(100);
    source.emit('job', job('recording-1', 'running', 'recording'));
    vi.advanceTimersByTime(100);

    expect(responses.at(-1)?.items.find(item => item.id === 'recording-1')?.state).toBe('running');

    subscription.unsubscribe();
  });

  it('forwards artifact updates with their revision immediately without throttling', () => {
    const updates: Array<{ kind: string; revision?: string }> = [];
    const sourceSubscription = service.updates$.subscribe();
    const subscription = service.artifactUpdates$.subscribe(
      update => updates.push({ kind: update.kind, revision: update.revision }),
    );
    const source = FakeEventSource.instances[0];

    source.emit('artifact', { session_id: 'session-1', kind: 'summary', revision: 'r1' });
    source.emit('artifact', { session_id: 'session-1', kind: 'transcript', revision: 'r2' });
    expect(updates).toEqual([
      { kind: 'summary', revision: 'r1' },
      { kind: 'transcript', revision: 'r2' },
    ]);

    subscription.unsubscribe();
    sourceSubscription.unsubscribe();
  });

  it('closes the shared event source when the last subscriber leaves', () => {
    const subscription = service.updates$.subscribe();
    const source = FakeEventSource.instances[0];
    expect(source.closed).toBe(false);

    subscription.unsubscribe();
    expect(source.closed).toBe(true);
  });
});
