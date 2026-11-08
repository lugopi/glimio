import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';
import {
  AppConfig, AudioDevices, AudioSourceSelection, GlimioSettings, JobsResponse, JobAction, Job,
  PreferencesPayload, SearchResult, SessionArtifact, SessionDetail, SessionPage,
  ProvidersResponse, ProviderInstallResponse, SessionMutationResponse, SessionDeleteResponse,
  DeletedJobResponse, ClearJobHistoryResponse,
} from './api.models';

/** Structured error for callers that need both a readable message and HTTP context. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function formatValidationDetail(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) {
    const messages = detail.map(item => {
      if (!item || typeof item !== 'object') return '';
      const value = item as { loc?: unknown; msg?: unknown };
      const location = Array.isArray(value.loc)
        ? value.loc.filter(part => part !== 'body' && part !== 'query' && part !== 'path')
          .map(part => String(part)).join('.')
        : '';
      const message = typeof value.msg === 'string' ? value.msg : '';
      return [location, message].filter(Boolean).join(' : ');
    }).filter(Boolean);
    return messages.length ? messages.join(' · ') : null;
  }
  if (detail && typeof detail === 'object') {
    const value = detail as { message?: unknown; error?: unknown };
    if (typeof value.message === 'string' && value.message.trim()) return value.message.trim();
    if (typeof value.error === 'string' && value.error.trim()) return value.error.trim();
  }
  return null;
}

/** Convert FastAPI, network and unexpected errors without discarding their status/details. */
export function normalizeApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof HttpErrorResponse) {
    const body = error.error as { detail?: unknown; error?: unknown; message?: unknown } | null;
    const details = body && typeof body === 'object'
      ? body.detail ?? body.error ?? body.message ?? body
      : body;
    const message = error.status === 0
      ? 'Impossible de joindre l’API Glimio. Vérifiez que le serveur est démarré.'
      : formatValidationDetail(details) ?? `Erreur HTTP ${error.status}`;
    return new ApiError(message, error.status, details);
  }
  return new ApiError(
    error instanceof Error ? error.message : 'Une erreur inattendue est survenue.',
    null,
    error,
  );
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  config(): Observable<AppConfig> {
    return this.get<AppConfig>('/api/config');
  }

  providers(): Observable<ProvidersResponse> {
    return this.get<ProvidersResponse>('/api/providers');
  }

  installProviderDependencies(providerId: string): Observable<ProviderInstallResponse> {
    return this.http.post<ProviderInstallResponse>(`/api/providers/${encodeURIComponent(providerId)}/install-python`, {}).pipe(catchError(this.normalizeError));
  }

  providerInstallStatus(installId: string): Observable<ProviderInstallResponse> {
    return this.get<ProviderInstallResponse>(`/api/provider-installs/${encodeURIComponent(installId)}`);
  }

  preferences(): Observable<PreferencesPayload> {
    return this.get<PreferencesPayload>('/api/preferences');
  }

  savePreferences(payload: PreferencesPayload): Observable<PreferencesPayload> {
    return this.http.put<PreferencesPayload>('/api/preferences', payload).pipe(catchError(this.normalizeError));
  }

  devices(): Observable<AudioDevices> {
    return this.get<AudioDevices>('/api/devices');
  }

  sessions(options: { query?: string; filter?: string; limit?: number | 'all'; offset?: number } = {}): Observable<SessionPage> {
    let params = new HttpParams()
      .set('q', options.query ?? '')
      .set('filter_by', options.filter ?? 'all')
      .set('limit', String(options.limit ?? 25))
      .set('offset', String(options.offset ?? 0));
    return this.get<SessionPage>('/api/sessions', params);
  }

  session(id: string): Observable<SessionDetail> {
    return this.get<SessionDetail>(`/api/sessions/${encodeURIComponent(id)}`);
  }

  saveSessionArtifact(id: string, kind: 'summary' | 'transcript', content: string, revision: string | null): Observable<SessionArtifact> {
    return this.http.put<SessionArtifact>(
      `/api/sessions/${encodeURIComponent(id)}/${kind}`, { content, revision },
    ).pipe(catchError(this.normalizeError));
  }

  sessionArtifact(id: string, kind: 'summary' | 'transcript',
                  revision?: string | null, offset?: number, tailHash?: string | null,
                  translationLanguage?: string | null): Observable<SessionArtifact> {
    let params = new HttpParams();
    if (revision) params = params.set('revision', revision);
    if (offset) params = params.set('offset', offset);
    if (tailHash) params = params.set('tail_hash', tailHash);
    if (translationLanguage) params = params.set('translation', translationLanguage);
    return this.get<SessionArtifact>(`/api/sessions/${encodeURIComponent(id)}/${kind}`, params);
  }

  renameSession(id: string, title: string): Observable<SessionMutationResponse> {
    return this.http.patch<SessionMutationResponse>(`/api/sessions/${encodeURIComponent(id)}`, { title }).pipe(catchError(this.normalizeError));
  }

  deleteSession(id: string): Observable<SessionDeleteResponse> {
    return this.http.delete<SessionDeleteResponse>(`/api/sessions/${encodeURIComponent(id)}`).pipe(catchError(this.normalizeError));
  }

  setAudioTrackDisabled(id: string, filename: string, disabled: boolean): Observable<SessionMutationResponse> {
    return this.http.patch<SessionMutationResponse>(
      `/api/sessions/${encodeURIComponent(id)}/audio/${encodeURIComponent(filename)}`, { disabled },
    ).pipe(catchError(this.normalizeError));
  }

  deleteAudioTrack(id: string, filename: string): Observable<SessionMutationResponse> {
    return this.http.delete<SessionMutationResponse>(
      `/api/sessions/${encodeURIComponent(id)}/audio/${encodeURIComponent(filename)}`,
    ).pipe(catchError(this.normalizeError));
  }

  saveSessionSettings(id: string, settings: GlimioSettings): Observable<SessionMutationResponse> {
    return this.http.put<SessionMutationResponse>(`/api/sessions/${encodeURIComponent(id)}/settings`, { settings }).pipe(catchError(this.normalizeError));
  }

  jobs(): Observable<JobsResponse> {
    return this.get<JobsResponse>('/api/jobs');
  }

  cancelJob(id: string): Observable<Job> {
    return this.http.post<Job>(`/api/jobs/${encodeURIComponent(id)}/cancel`, {}).pipe(catchError(this.normalizeError));
  }

  deleteJob(id: string): Observable<DeletedJobResponse> {
    return this.http.delete<DeletedJobResponse>(`/api/jobs/${encodeURIComponent(id)}`).pipe(catchError(this.normalizeError));
  }

  clearJobHistory(): Observable<ClearJobHistoryResponse> {
    return this.http.delete<ClearJobHistoryResponse>('/api/jobs/history').pipe(catchError(this.normalizeError));
  }

  startSessionJob(action: JobAction, sessionId: string, settings: GlimioSettings, force = false): Observable<Job> {
    return this.http.post<Job>('/api/jobs', { action, session_id: sessionId, settings, force }).pipe(catchError(this.normalizeError));
  }

  startRecording(payload: {
    title: string; microphone: string; output: string; capture_microphone: boolean;
    capture_windows: boolean; normalize_windows: boolean; normalize_windows_max_gain_db: number;
    sources?: AudioSourceSelection[];
    auto_transcribe: boolean; auto_pv: boolean; settings: GlimioSettings;
  }): Observable<Job> {
    return this.http.post<Job>('/api/recording/start', payload).pipe(catchError(this.normalizeError));
  }

  stopRecording(): Observable<Job> {
    return this.http.post<Job>('/api/recording/stop', {}).pipe(catchError(this.normalizeError));
  }

  importFile(file: File, settings: GlimioSettings, action: 'process' | 'transcribe', normalizeWindows = true, normalizeGainDb = 30): Observable<Job> {
    const body = new FormData();
    body.append('file', file, file.name);
    body.append('settings_json', JSON.stringify(settings));
    body.append('action', action);
    body.append('normalize_windows', String(normalizeWindows));
    body.append('normalize_windows_max_gain_db', String(normalizeGainDb));
    return this.http.post<Job>('/api/import', body).pipe(catchError(this.normalizeError));
  }

  startSearch(query: string, settings: GlimioSettings, topK = 8, sessionIds: string[] = []): Observable<SearchResult> {
    return this.http.post<SearchResult>('/api/search/start', {
      query, settings, top_k: topK, session_ids: sessionIds,
    }).pipe(catchError(this.normalizeError));
  }

  synthesizeSearch(id: string, sourceIds: string[]): Observable<SearchResult> {
    return this.http.post<SearchResult>(`/api/search/${encodeURIComponent(id)}/synthesize`, {
      source_ids: sourceIds,
    }).pipe(catchError(this.normalizeError));
  }

  search(id: string): Observable<SearchResult> {
    return this.get<SearchResult>(`/api/search/${encodeURIComponent(id)}`);
  }

  cancelSearch(id: string): Observable<SearchResult> {
    return this.http.post<SearchResult>(`/api/search/${encodeURIComponent(id)}/cancel`, {}).pipe(catchError(this.normalizeError));
  }

  private get<T>(url: string, params?: HttpParams): Observable<T> {
    return this.http.get<T>(url, { params }).pipe(catchError(this.normalizeError));
  }

  private readonly normalizeError = (error: unknown) =>
    throwError(() => normalizeApiError(error));
}
