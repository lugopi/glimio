/** A completed phase duration captured by the Web job runner. */
export interface ProcessingPhaseDurationSample {
  phase: string;
  durationSeconds: number;
}

/** Historical observation for one completed processing job. */
export interface ProcessingDurationSample {
  sessionId: string | null;
  durationSeconds: number;
  audioDurationSeconds?: number | null;
  completedAt: number;
  phaseHistory?: ProcessingPhaseDurationSample[];
}

export interface ActiveProcessingPhase {
  phase: string;
  elapsedSeconds: number;
  completedPhases: ProcessingPhaseDurationSample[];
}

/**
 * Estimate remaining work from successful runs. When phase histories are available,
 * project the uncompleted part of the current phase and the phases usually following
 * it. Re-evaluate this on every phase/status update so the finish time can move with
 * the actual run instead of remaining a fixed historical guess.
 *
 * Older job records do not have phase history, so they use the duration-based fallback.
 */
export function estimateRemainingProcessingSeconds(
  history: ProcessingDurationSample[],
  currentSessionId: string,
  currentAudioDurationSeconds: number | null | undefined,
  elapsedSeconds: number,
  activePhase?: ActiveProcessingPhase,
): number | null {
  const valid = history
    .filter(sample => Number.isFinite(sample.durationSeconds) && sample.durationSeconds > 0
      && Number.isFinite(sample.completedAt))
    .sort((left, right) => right.completedAt - left.completedAt);
  if (!valid.length || !Number.isFinite(elapsedSeconds) || elapsedSeconds < 0) return null;

  if (activePhase && Number.isFinite(activePhase.elapsedSeconds) && activePhase.elapsedSeconds >= 0) {
    const phaseEstimate = estimateFromPhaseHistory(valid, currentSessionId, activePhase);
    if (phaseEstimate !== null) return phaseEstimate;
  }

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

function estimateFromPhaseHistory(
  history: ProcessingDurationSample[],
  currentSessionId: string,
  current: ActiveProcessingPhase,
): number | null {
  const withPhases = history.filter(sample => sample.phaseHistory?.some(item =>
    item.phase === current.phase && Number.isFinite(item.durationSeconds) && item.durationSeconds > 0,
  ));
  if (!withPhases.length) return null;

  // Prefer previous runs for this exact session when present. Otherwise use runs
  // from other sessions of the same job kind (filtered by the caller).
  const sameSessionPhaseRuns = withPhases.filter(sample => sample.sessionId === currentSessionId);
  const candidates = sameSessionPhaseRuns.length ? sameSessionPhaseRuns : withPhases;
  const completed = current.completedPhases;
  const estimates: Array<{ score: number; completedAt: number; seconds: number }> = [];

  for (const sample of candidates) {
    const phases = sample.phaseHistory ?? [];
    for (let index = 0; index < phases.length; index += 1) {
      if (phases[index].phase !== current.phase) continue;
      let score = 0;
      if (completed.length) {
        // The phase directly before the current one must match. Matching more of the
        // suffix makes the projection less likely to borrow a different workflow.
        if (index === 0 || phases[index - 1].phase !== completed[completed.length - 1].phase) continue;
        score = 1;
        let historicIndex = index - 2;
        let currentIndex = completed.length - 2;
        while (historicIndex >= 0 && currentIndex >= 0 && score < 3) {
          if (phases[historicIndex].phase !== completed[currentIndex].phase) break;
          score += 1;
          historicIndex -= 1;
          currentIndex -= 1;
        }
      }

      const currentPhaseRemaining = Math.max(0, phases[index].durationSeconds - current.elapsedSeconds);
      const futurePhaseSeconds = phases.slice(index + 1).reduce((total, item) => {
        return total + (Number.isFinite(item.durationSeconds) && item.durationSeconds > 0 ? item.durationSeconds : 0);
      }, 0);
      const remaining = currentPhaseRemaining + futurePhaseSeconds;
      if (remaining > 0) estimates.push({ score, completedAt: sample.completedAt, seconds: remaining });
    }
  }

  if (!estimates.length) return null;
  const bestScore = Math.max(...estimates.map(item => item.score));
  const best = estimates.filter(item => item.score === bestScore)
    .sort((left, right) => right.completedAt - left.completedAt)
    .slice(0, 7);
  // A slightly conservative percentile is more useful than the fastest historical run.
  return Math.max(1, Math.ceil(percentile(best.map(item => item.seconds), 0.65)));
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
