export type ThemeName = 'dark' | 'light' | 'midnight' | 'forest' | 'dracula' | 'monokai';
export type ViewName = 'recording' | 'library' | 'search' | 'settings';
export type JobState = 'queued' | 'running' | 'stopping' | 'completed' | 'error';
export type JobAction = 'transcribe' | 'summarize' | 'process';

export interface GlimioSettings {
  model: string;
  whisper_cli: string;
  language: string;
  threads: number;
  openvino_device: string | null;
  ffmpeg: string;
  diarize: boolean;
  diarization_segmentation_model: string;
  diarization_embedding_model: string;
  diarization_num_speakers: number;
  audio_bitrate_kbps: 128 | 256 | 384 | 512 | 768;
  diarization_threshold: number;
  gguf: string;
  llama_completion: string;
  context: number;
  max_tokens: number;
  analysis_tokens: number;
  analysis_retries: number;
  analysis_max_splits: number;
  format: string;
  no_review: boolean;
}

export interface UiPreferences {
  theme: ThemeName;
  language: 'fr' | 'en';
  session_root: string;
  microphone: string;
  output: string;
  capture_microphone: boolean;
  capture_windows: boolean;
  audio_sources: AudioSourceSelection[];
  normalize_windows: boolean;
  normalize_windows_max_gain_db: number;
  recording_workflow: 'none' | 'transcribe' | 'summary';
  import_action: 'process' | 'transcribe';
}

export interface PreferencesPayload {
  settings: GlimioSettings;
  ui: UiPreferences;
}

export interface AppConfig {
  session_root: string;
  session_root_exists: boolean;
  project_root: string;
  processing_mode: 'local' | 'hybrid' | 'cloud' | string;
  offline_local_mode: boolean;
  defaults: GlimioSettings;
  preferences: PreferencesPayload;
  formats: string[];
}

export type AudioSourceKind = 'microphone' | 'output';

export interface AudioSourceSelection {
  kind: AudioSourceKind;
  device_id: string;
  device_name: string;
}

export interface AudioDeviceInfo {
  id: string;
  name: string;
  key?: string;
}

export interface AudioDevices {
  microphones: string[];
  outputs: string[];
  microphone_devices?: AudioDeviceInfo[];
  output_devices?: AudioDeviceInfo[];
}

export interface ProcessingInfo {
  job_id: string;
  kind: string;
  state: JobState;
  phase: string;
  active: boolean;
  message: string;
  error?: string | null;
}

export interface SessionSummary {
  id: string;
  title: string;
  started_at?: string;
  summary_excerpt?: string;
  summary: boolean;
  transcript: boolean;
  audio: boolean;
  audio_tracks?: string[];
  duration_seconds?: number | null;
  processing?: ProcessingInfo | null;
}

export interface SessionPage {
  items: SessionSummary[];
  count: number;
  page_count: number;
  limit: number | string;
  offset: number;
  root: string;
  root_exists: boolean;
  project_root: string;
}

export interface SessionDetail extends SessionSummary {
  metadata?: Record<string, unknown>;
  files?: { summary: boolean; transcript: boolean; audio_tracks: string[]; analysis: boolean };
}

export interface Job {
  id: string;
  kind: string;
  state: JobState;
  phase: string;
  message?: string;
  error?: string | null;
  session_id?: string | null;
  created_at?: string;
  updated_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  queue_position?: number | null;
}

export interface JobsResponse {
  items: Job[];
  active?: Job | null;
  queue?: { waiting?: number; running?: Job | null };
}

export interface SearchSource {
  source_number: number | string;
  title: string;
  session_id: string;
  filename: string;
  kind: string;
  text: string;
}

export interface SearchResult {
  id: string;
  state: 'queued' | 'running' | 'completed' | 'cancelled' | 'error';
  message?: string;
  sessions_total?: number;
  sessions_scanned?: number;
  passages_found?: number;
  answer?: string;
  llm_error?: string;
  sources?: SearchSource[];
}
