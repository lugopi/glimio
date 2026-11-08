import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ApiError, ApiService, normalizeApiError } from './api.service';

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('uses the existing FastAPI contract for configuration', () => {
  const expected = { session_root: 'seances/', session_root_exists: true, project_root: '.', processing_mode: 'local', offline_local_mode: true, defaults: {}, preferences: {}, formats: [], processing_profiles: {} };
    api.config().subscribe(value => expect(value.session_root).toBe('seances/'));
    const request = http.expectOne('/api/config');
    expect(request.request.method).toBe('GET');
    request.flush(expected);
  });

  it('sends session jobs with the existing action/session/settings shape', () => {
    const settings = { model: 'model.bin' } as never;
    api.startSessionJob('transcribe', 'session-1', settings).subscribe(job => expect(job.id).toBe('job-1'));
    const request = http.expectOne('/api/jobs');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ action: 'transcribe', session_id: 'session-1', settings, force: false });
    request.flush({ id: 'job-1', kind: 'transcribe', state: 'queued', phase: 'queued' });
  });

  it('sends the incremental artifact revision, offset and tail hash', () => {
    api.sessionArtifact('session-1', 'transcript', 'rev-1', 120, '1a47e90b').subscribe(value => {
      expect(value.content).toBe(' suite');
      expect(value.append).toBe(true);
      expect(value.live).toBe(true);
    });
    const request = http.expectOne(req => req.url === '/api/sessions/session-1/transcript');
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('revision')).toBe('rev-1');
    expect(request.request.params.get('offset')).toBe('120');
    expect(request.request.params.get('tail_hash')).toBe('1a47e90b');
    expect(request.request.params.has('tail')).toBe(false);
    request.flush({
      session_id: 'session-1', kind: 'transcript', filename: 'transcription_en_cours.md',
      revision: 'rev-2', content: ' suite', append: true, live: true,
    });
  });

  it('saves a transcript edit with optimistic revision metadata', () => {
    api.saveSessionArtifact('session-1', 'transcript', 'Texte corrigé', 'rev-1').subscribe(value => {
      expect(value.kind).toBe('transcript');
      expect(value.content).toBe('Texte corrigé');
    });
    const request = http.expectOne('/api/sessions/session-1/transcript');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({ content: 'Texte corrigé', revision: 'rev-1' });
    request.flush({ session_id: 'session-1', kind: 'transcript', filename: 'transcription.md', revision: 'rev-2', content: 'Texte corrigé', live: false });
  });

  it('keeps FastAPI validation details readable and preserves the HTTP status', () => {
    const error = normalizeApiError(new HttpErrorResponse({
      status: 422,
      error: { detail: [{ loc: ['body', 'settings', 'context'], msg: 'Input should be greater than or equal to 2048' }] },
    }));
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
    expect(error.message).toContain('settings.context');
    expect(error.message).toContain('2048');
  });

  it('keeps conflict messages and distinguishes a disconnected API', () => {
    const conflict = normalizeApiError(new HttpErrorResponse({ status: 409, error: { detail: 'Le document a changé.' } }));
    expect(conflict.status).toBe(409);
    expect(conflict.message).toBe('Le document a changé.');

    const disconnected = normalizeApiError(new HttpErrorResponse({ status: 0, error: null }));
    expect(disconnected.status).toBe(0);
    expect(disconnected.message).toContain('Impossible de joindre l’API Glimio');
  });

});
