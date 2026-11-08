import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { Job, JobsResponse } from '../../core/api.models';
import { JobEventsService } from '../../core/job-events.service';
import { JobsPageComponent } from './jobs.page';

function job(id: string, state: Job['state'], createdAt: string): Job {
  return {
    id,
    kind: 'summarize',
    state,
    phase: state,
    message: `État ${state}`,
    created_at: createdAt,
    session_id: `session-${id}`,
  };
}

function response(items: Job[]): JobsResponse {
  return {
    items,
    active: null,
    queue: { waiting: items.filter(item => item.state === 'queued').length, running: null, serial: true },
  };
}

describe('JobsPageComponent', () => {
  let fixture: ComponentFixture<JobsPageComponent>;
  let http: HttpTestingController;
  let jobUpdates: Subject<JobsResponse>;

  beforeEach(async () => {
    jobUpdates = new Subject<JobsResponse>();
    await TestBed.configureTestingModule({
      imports: [JobsPageComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: JobEventsService, useValue: { updates$: jobUpdates.asObservable() } },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(JobsPageComponent);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('loads the initial REST snapshot and separates active work from completed history', () => {
    const tasks = [
      job('queued-1', 'queued', '2026-11-08T10:00:00Z'),
      job('running-1', 'running', '2026-11-08T10:01:00Z'),
      job('done-old', 'completed', '2026-11-08T09:00:00Z'),
      job('done-new', 'completed', '2026-11-08T11:00:00Z'),
    ];
    http.expectOne('/api/jobs').flush(response(tasks));
    fixture.detectChanges();

    expect(fixture.componentInstance.jobs().map(item => item.id)).toEqual(['running-1', 'queued-1']);
    expect(fixture.componentInstance.historyJobs().map(item => item.id)).toEqual(['done-new', 'done-old']);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Historique récent');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Terminé');
  });

  it('keeps the history page within range after SSE removes old activities', () => {
    const many = Array.from({ length: 18 }, (_, index) => job(`done-${index}`, 'completed', new Date(Date.UTC(2026, 10, 8, 12 - index)).toISOString()));
    http.expectOne('/api/jobs').flush(response(many));
    fixture.componentInstance.historyPage.set(3);
    fixture.detectChanges();

    jobUpdates.next(response(many.slice(0, 3)));
    fixture.detectChanges();

    expect(fixture.componentInstance.historyPage()).toBe(1);
    expect(fixture.componentInstance.visibleHistoryJobs()).toHaveLength(3);
  });
});
