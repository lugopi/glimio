import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ProgressiveTextReveal,
  codePointLength,
  codePointTailHash,
  prefersReducedMotion,
  sliceCodePoints,
} from './progressive-text';

class FakeScheduler {
  private readonly callbacks = new Map<number, () => void>();
  private nextHandle = 1;
  time = 0;

  now(): number {
    return this.time;
  }

  request(callback: () => void): number {
    const handle = this.nextHandle++;
    this.callbacks.set(handle, callback);
    return handle;
  }

  cancel(handle: number): void {
    this.callbacks.delete(handle);
  }

  get pending(): number {
    return this.callbacks.size;
  }

  advance(milliseconds: number): void {
    this.time += milliseconds;
    const pending = [...this.callbacks.values()];
    this.callbacks.clear();
    pending.forEach(callback => callback());
  }
}

const originalMatchMedia = Object.getOwnPropertyDescriptor(window, 'matchMedia');

afterEach(() => {
  vi.unstubAllGlobals();
  if (originalMatchMedia) Object.defineProperty(window, 'matchMedia', originalMatchMedia);
  else delete (window as { matchMedia?: unknown }).matchMedia;
});

describe('progressive text helpers', () => {
  it('counts and slices code points without splitting surrogate pairs', () => {
    expect(codePointLength('a😀b')).toBe(3);
    expect(codePointLength('')).toBe(0);
    expect(sliceCodePoints('a😀b', 2)).toBe('a😀');
    expect(sliceCodePoints('a😀b', 0)).toBe('');
    expect(sliceCodePoints('a😀b', 99)).toBe('a😀b');
  });

  it('treats an absent matchMedia as motion enabled', () => {
    vi.stubGlobal('window', undefined);
    expect(prefersReducedMotion()).toBe(false);
  });

  it('hashes the last code points with the backend FNV-1a vector', () => {
    expect(codePointTailHash('abc', 64)).toBe('1a47e90b');
    expect(codePointTailHash('xxa😀b', 3)).toBe('4e6351d2');
    expect(codePointTailHash('', 64)).toBe('811c9dc5');
  });
});

describe('ProgressiveTextReveal', () => {
  it('reveals a finished or large document at once without scheduling a frame', () => {
    const scheduler = new FakeScheduler();
    const values: number[] = [];
    const reveal = new ProgressiveTextReveal(value => values.push(value), {}, scheduler);

    reveal.setTarget(500, false);
    expect(reveal.revealed).toBe(500);
    expect(values).toEqual([500]);
    expect(scheduler.pending).toBe(0);

    reveal.reset();
    reveal.setTarget(80_001, true);
    expect(reveal.revealed).toBe(80_001);
    expect(values.at(-1)).toBe(80_001);
    expect(scheduler.pending).toBe(0);
  });

  it('reveals progressively and monotonically until the target', () => {
    const scheduler = new FakeScheduler();
    const values: number[] = [];
    const reveal = new ProgressiveTextReveal(value => values.push(value), { maxStep: 100 }, scheduler);

    reveal.setTarget(3_000, true);
    expect(reveal.revealed).toBe(40);
    expect(values).toEqual([40]);
    expect(scheduler.pending).toBe(1);

    for (let step = 0; step < 400 && scheduler.pending; step++) scheduler.advance(16);

    expect(reveal.revealed).toBe(3_000);
    expect(scheduler.pending).toBe(0);
    expect(values.every((value, index) => index === 0 || value >= values[index - 1])).toBe(true);
  });

  it('caps large live documents to a 15 fps budget', () => {
    const scheduler = new FakeScheduler();
    const reveal = new ProgressiveTextReveal(() => undefined, {}, scheduler);

    reveal.setTarget(30_000, true);
    expect(reveal.revealed).toBe(40);
    scheduler.advance(16);
    expect(reveal.revealed).toBe(40);
    expect(scheduler.pending).toBe(1);
    scheduler.advance(50);
    expect(reveal.revealed).toBeGreaterThan(40);
  });

  it('finishes a medium document within the maximum duration', () => {
    const scheduler = new FakeScheduler();
    const reveal = new ProgressiveTextReveal(() => undefined, {}, scheduler);

    reveal.setTarget(30_000, true);
    for (let step = 0; step < 200 && scheduler.pending; step++) scheduler.advance(16);

    expect(reveal.revealed).toBe(30_000);
    expect(scheduler.pending).toBe(0);
    expect(scheduler.time).toBeGreaterThan(0);
    expect(scheduler.time).toBeLessThanOrEqual(600);
  });

  it('honours prefers-reduced-motion', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: () => ({ matches: true, media: '(prefers-reduced-motion: reduce)' }),
    });
    expect(prefersReducedMotion()).toBe(true);

    const scheduler = new FakeScheduler();
    const reveal = new ProgressiveTextReveal(() => undefined, {}, scheduler);
    reveal.setTarget(5_000, true);
    expect(reveal.revealed).toBe(5_000);
    expect(scheduler.pending).toBe(0);
  });

  it('cancels a pending frame on reset and destroy', () => {
    const scheduler = new FakeScheduler();
    const reveal = new ProgressiveTextReveal(() => undefined, {}, scheduler);
    reveal.setTarget(5_000, true);
    expect(scheduler.pending).toBe(1);

    reveal.reset(7);
    expect(reveal.revealed).toBe(7);
    expect(scheduler.pending).toBe(0);

    reveal.setTarget(5_000, true);
    expect(scheduler.pending).toBe(1);
    reveal.destroy();
    expect(reveal.revealed).toBe(0);
    expect(scheduler.pending).toBe(0);
  });
});
