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

  it('re-estimates from the active phase and the phases still to come', () => {
    const phaseHistory: ProcessingDurationSample[] = [{
      sessionId: 'current',
      durationSeconds: 260,
      completedAt: 50,
      phaseHistory: [
        { phase: 'starting', durationSeconds: 2 },
        { phase: 'preparing', durationSeconds: 3 },
        { phase: 'transcribing', durationSeconds: 100 },
        { phase: 'summarizing', durationSeconds: 50 },
        { phase: 'saving', durationSeconds: 5 },
      ],
    }];

    const completedPhases = [
      { phase: 'starting', durationSeconds: 2 },
      { phase: 'preparing', durationSeconds: 3 },
      { phase: 'transcribing', durationSeconds: 100 },
    ];
    const early = estimateRemainingProcessingSeconds(phaseHistory, 'current', 600, 150, {
      phase: 'summarizing', elapsedSeconds: 10, completedPhases,
    });
    const later = estimateRemainingProcessingSeconds(phaseHistory, 'current', 600, 170, {
      phase: 'summarizing', elapsedSeconds: 30, completedPhases,
    });

    expect(early).toBe(45);
    expect(later).toBe(25);
  });

  it('prefers phase timings from the same session instead of unrelated slower runs', () => {
    const phaseHistory: ProcessingDurationSample[] = [
      {
        sessionId: 'other-session', durationSeconds: 1_000, completedAt: 80,
        phaseHistory: [
          { phase: 'starting', durationSeconds: 2 },
          { phase: 'transcribing', durationSeconds: 900 },
          { phase: 'summarizing', durationSeconds: 100 },
        ],
      },
      {
        sessionId: 'current', durationSeconds: 100, completedAt: 70,
        phaseHistory: [
          { phase: 'starting', durationSeconds: 2 },
          { phase: 'transcribing', durationSeconds: 70 },
          { phase: 'summarizing', durationSeconds: 28 },
        ],
      },
    ];

    expect(estimateRemainingProcessingSeconds(phaseHistory, 'current', 600, 40, {
      phase: 'transcribing', elapsedSeconds: 20,
      completedPhases: [{ phase: 'starting', durationSeconds: 2 }],
    })).toBe(78);
  });

  it('returns no estimate when there is no usable history', () => {
    expect(estimateRemainingProcessingSeconds([], 'new-session', 1_200, 10)).toBeNull();
  });
});
