import { describe, expect, it } from 'vitest';
import { estimateRemainingProcessingSeconds, type ProcessingDurationSample } from './processing-eta';

const history: ProcessingDurationSample[] = [
  { sessionId: 'other-1', durationSeconds: 300, audioDurationSeconds: 600, completedAt: 30 },
  { sessionId: 'other-2', durationSeconds: 330, audioDurationSeconds: 660, completedAt: 20 },
  { sessionId: 'other-3', durationSeconds: 360, audioDurationSeconds: 720, completedAt: 10 },
];

describe('estimateRemainingProcessingSeconds', () => {
  it('prefers completed runs for the same session over unrelated history', () => {
    const samples = [
      { sessionId: 'current', durationSeconds: 600, completedAt: 40 },
      { sessionId: 'current', durationSeconds: 620, completedAt: 35 },
      ...history,
    ];
    expect(estimateRemainingProcessingSeconds(samples, 'current', 900, 100)).toBeGreaterThan(500);
  });

  it('normalizes previous runtimes by source audio duration when enough samples exist', () => {
    expect(estimateRemainingProcessingSeconds(history, 'new-session', 1_200, 100)).toBe(500);
  });

  it('does not show an ETA once the estimated completion time has passed', () => {
    expect(estimateRemainingProcessingSeconds(history, 'new-session', 1_200, 700)).toBeNull();
  });

  it('returns no estimate when there is no usable history', () => {
    expect(estimateRemainingProcessingSeconds([], 'new-session', 1_200, 10)).toBeNull();
  });
});
