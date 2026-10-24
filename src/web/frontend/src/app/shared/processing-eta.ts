/** Historical observation for one completed processing job. */
export interface ProcessingDurationSample {
  sessionId: string | null;
  durationSeconds: number;
  audioDurationSeconds?: number | null;
  completedAt: number;
}

/**
 * Estimate remaining work from successful runs. Prefer the same session (same input),
 * then runs whose source duration is known, and only then a generic per-job estimate.
 * Returns null instead of displaying a finish time that is already in the past.
 */
export function estimateRemainingProcessingSeconds(
  history: ProcessingDurationSample[],
  currentSessionId: string,
  currentAudioDurationSeconds: number | null | undefined,
  elapsedSeconds: number,
): number | null {
  const valid = history
    .filter(sample => Number.isFinite(sample.durationSeconds) && sample.durationSeconds > 0
      && Number.isFinite(sample.completedAt))
    .sort((left, right) => right.completedAt - left.completedAt);
  if (!valid.length || !Number.isFinite(elapsedSeconds) || elapsedSeconds < 0) return null;

  const sameSession = valid.filter(sample => sample.sessionId === currentSessionId).slice(0, 5);
  let totalEstimate: number;
  if (sameSession.length) {
    totalEstimate = percentile(sameSession.map(sample => sample.durationSeconds), 0.65);
  } else {
    const normalized = valid.filter(sample =>
      Number.isFinite(sample.audioDurationSeconds) && (sample.audioDurationSeconds ?? 0) > 0,
    ).slice(0, 10);
    if (normalized.length >= 3 && (currentAudioDurationSeconds ?? 0) > 0) {
      const secondsPerAudioSecond = normalized.map(sample =>
        sample.durationSeconds / sample.audioDurationSeconds!,
      );
      totalEstimate = percentile(secondsPerAudioSecond, 0.65) * currentAudioDurationSeconds!;
    } else {
      totalEstimate = percentile(valid.slice(0, 7).map(sample => sample.durationSeconds), 0.65);
    }
  }

  if (!Number.isFinite(totalEstimate) || totalEstimate <= elapsedSeconds) return null;
  return Math.max(1, Math.ceil(totalEstimate - elapsedSeconds));
}

function percentile(values: number[], quantile: number): number {
  const sorted = values.filter(value => Number.isFinite(value) && value > 0).sort((left, right) => left - right);
  if (!sorted.length) return 0;
  const position = (sorted.length - 1) * quantile;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  const weight = position - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}
