import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';
import {
  AppConfig, AudioDevices, AudioSourceSelection, GlimioSettings, JobsResponse, JobAction, Job,
  PreferencesPayload, SearchResult, SessionArtifact, SessionDetail, SessionPage,
  ProvidersResponse, ProviderInstallResponse,
} from './api.models';

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

  saveSessionSummary(id: string, content: string, revision: string | null): Observable<SessionArtifact> {
    return this.http.put<SessionArtifact>(
      `/api/sessions/${encodeURIComponent(id)}/summary`, { content, revision },
    ).pipe(catchError(this.normalizeError));
  }

  sessionArtifact(id: string, kind: 'summary' | 'transcript',
                  revision?: string | null, offset?: number, tailHash?: string | null): Observable<SessionArtifact> {
    let params = new HttpParams();
    if (revision) params = params.set('revision', revision);
    if (offset) params = params.set('offset', offset);
    if (tailHash) params = params.set('tail_hash', tailHash);
    return this.get<SessionArtifact>(`/api/sessions/${encodeURIComponent(id)}/${kind}`, params);
  }

  renameSession(id: string, title: string): Observable<SessionDetail> {
    return this.http.patch<SessionDetail>(`/api/sessions/${encodeURIComponent(id)}`, { title }).pipe(catchError(this.normalizeError));
  }

  deleteSession(id: string): Observable<{ deleted: string }> {
    return this.http.delete<{ deleted: string }>(`/api/sessions/${encodeURIComponent(id)}`).pipe(catchError(this.normalizeError));
  }

  setAudioTrackDisabled(id: string, filename: string, disabled: boolean): Observable<{ id: string; filename: string; disabled_audio_tracks: string[]; metadata: Record<string, unknown> }> {
    return this.http.patch<{ id: string; filename: string; disabled_audio_tracks: string[]; metadata: Record<string, unknown> }>(
      `/api/sessions/${encodeURIComponent(id)}/audio/${encodeURIComponent(filename)}`, { disabled },
    ).pipe(catchError(this.normalizeError));
  }

  deleteAudioTrack(id: string, filename: string): Observable<{ id: string; filename: string; audio_tracks: string[]; metadata: Record<string, unknown>; warnings: string[] }> {
    return this.http.delete<{ id: string; filename: string; audio_tracks: string[]; metadata: Record<string, unknown>; warnings: string[] }>(
      `/api/sessions/${encodeURIComponent(id)}/audio/${encodeURIComponent(filename)}`,
    ).pipe(catchError(this.normalizeError));
  }

  saveSessionSettings(id: string, settings: GlimioSettings): Observable<{ id: string; settings: GlimioSettings; metadata: Record<string, unknown> }> {
    return this.http.put<{ id: string; settings: GlimioSettings; metadata: Record<string, unknown> }>(`/api/sessions/${encodeURIComponent(id)}/settings`, { settings }).pipe(catchError(this.normalizeError));
  }

  jobs(): Observable<JobsResponse> {
    return this.get<JobsResponse>('/api/jobs');
  }

  cancelJob(id: string): Observable<Job> {
    return this.http.post<Job>(`/api/jobs/${encodeURIComponent(id)}/cancel`, {}).pipe(catchError(this.normalizeError));
  }

  deleteJob(id: string): Observable<{ deleted: string }> {
    return this.http.delete<{ deleted: string }>(`/api/jobs/${encodeURIComponent(id)}`).pipe(catchError(this.normalizeError));
  }

  clearJobHistory(): Observable<{ deleted: number }> {
    return this.http.delete<{ deleted: number }>('/api/jobs/history').pipe(catchError(this.normalizeError));
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

  startSearch(query: string, settings: GlimioSettings, topK = 8): Observable<SearchResult> {
    return this.http.post<SearchResult>('/api/search/start', { query, settings, top_k: topK }).pipe(catchError(this.normalizeError));
  }

  search(id: string): Observable<SearchResult> {
    return this.get<SearchResult>(`/api/search/${encodeURIComponent(id)}`);
  }

  cancelSearch(id: string): Observable<unknown> {
    return this.http.post(`/api/search/${encodeURIComponent(id)}/cancel`, {}).pipe(catchError(this.normalizeError));
  }

  private get<T>(url: string, params?: HttpParams): Observable<T> {
    return this.http.get<T>(url, { params }).pipe(catchError(this.normalizeError));
  }

  private readonly normalizeError = (error: unknown) => {
    if (error instanceof HttpErrorResponse) {
      const detail = typeof error.error === 'object' && error.error !== null
        ? error.error.detail ?? error.error.error
        : error.error;
      return throwError(() => new Error(String(detail || `Erreur HTTP ${error.status}`)));
    }
    return throwError(() => error instanceof Error ? error : new Error('Une erreur inattendue est survenue.'));
  };
}
