export type ThemeName = 'dark' | 'light' | 'midnight' | 'forest' | 'dracula' | 'monokai';
export type ViewName = 'recording' | 'jobs' | 'library' | 'search' | 'settings';
export type JobState = 'queued' | 'running' | 'stopping' | 'completed' | 'cancelled' | 'error';
export type JobAction = 'transcribe' | 'summarize' | 'process';

export interface GlimioSettings {
  processing_profile: 'turbo' | 'balanced' | 'quality' | 'pixel-perfect' | 'custom';
  model: string;
  transcription_provider: string;
  provider_options: Record<string, Record<string, unknown>>;
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
  text_provider: string;
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
  processing_profiles: Record<string, Partial<Pick<GlimioSettings, 'max_tokens' | 'analysis_tokens' | 'analysis_retries' | 'analysis_max_splits' | 'no_review'>>>;
}

export interface ProviderStatus {
  id: string;
  name: string;
  task: 'transcription' | 'generation' | 'diarization' | 'media';
  description: string;
  execution: 'embedded' | 'bundled_executable' | 'system_executable' | 'remote';
  capabilities: string[];
  options: ProviderOption[];
  ready: boolean;
  message: string;
  version: string | null;
  missing: string[];
  details: Record<string, unknown>;
}

export interface ProviderOption {
  key: string;
  label: string;
  type: 'text' | 'path' | 'secret' | 'number' | 'boolean' | 'select';
  default: unknown;
  description: string;
  required: boolean;
  minimum: number | null;
  maximum: number | null;
  step: number | null;
  choices: { value: string; label: string }[];
  advanced: boolean;
  per_job: boolean;
  depends_on: string | null;
  depends_value: unknown;
}

export interface ProvidersResponse {
  providers: ProviderStatus[];
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

export interface SessionArtifact {
  session_id: string;
  kind: 'summary' | 'transcript';
  filename: string;
  revision: string;
  unchanged?: boolean;
  pending?: boolean;
  content?: string;
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
  provider_event?: ProviderEvent | null;
}

export interface ProviderEvent {
  provider_id: string;
  task: 'transcription' | 'generation' | 'diarization' | 'media';
  stage: string;
  message: string;
  progress: number | null;
  details: Record<string, unknown>;
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
