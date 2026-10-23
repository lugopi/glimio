/**
 * Progressive reveal for documents that are still being generated. The helper
 * works on code points so surrogate pairs are never split between two renders.
 */

export interface ProgressiveTextScheduler {
  now(): number;
  request(callback: () => void): number;
  cancel(handle: number): void;
}

export interface ProgressiveTextOptions {
  minDurationMs?: number;
  maxDurationMs?: number;
  maxStep?: number;
  largeDocumentThreshold?: number;
  mediumDocumentThreshold?: number;
}

export function codePointLength(value: string): number {
  return Array.from(value).length;
}

export function sliceCodePoints(value: string, count: number): string {
  if (count <= 0) return '';
  const points = Array.from(value);
  return points.length <= count ? value : points.slice(0, count).join('');
}

/** FNV-1a 32-bit hash over the last `count` code points, matching the backend. */
export function codePointTailHash(value: string, count: number): string {
  const points = Array.from(value);
  const start = Math.max(0, points.length - Math.max(0, count));
  let hash = 2166136261;
  for (let index = start; index < points.length; index++) {
    hash ^= points[index].codePointAt(0)!;
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

const runtimeScheduler: ProgressiveTextScheduler = {
  now: () => (typeof performance !== 'undefined' ? performance.now() : Date.now()),
  request: callback => {
    if (typeof requestAnimationFrame === 'function') {
      return requestAnimationFrame(() => callback());
    }
    return window.setTimeout(callback, 16);
  },
  cancel: handle => {
    if (typeof requestAnimationFrame === 'function') cancelAnimationFrame(handle);
    else window.clearTimeout(handle);
  },
};

const INITIAL_BURST = 40;

export class ProgressiveTextReveal {
  private targetValue = 0;
  private revealedValue = 0;
  private frame: number | null = null;
  private lastTimestamp: number | null = null;
  private rate = 0;
  private readonly minDurationMs: number;
  private readonly maxDurationMs: number;
  private readonly maxStep: number;
  private readonly largeDocumentThreshold: number;
  private readonly mediumDocumentThreshold: number;

  constructor(
    private readonly notify: (revealed: number) => void,
    options: ProgressiveTextOptions = {},
    private readonly scheduler: ProgressiveTextScheduler = runtimeScheduler,
  ) {
    this.minDurationMs = options.minDurationMs ?? 160;
    this.maxDurationMs = options.maxDurationMs ?? 480;
    this.maxStep = options.maxStep ?? 240;
    this.largeDocumentThreshold = options.largeDocumentThreshold ?? 80_000;
    this.mediumDocumentThreshold = options.mediumDocumentThreshold ?? 20_000;
  }

  get revealed(): number {
    return this.revealedValue;
  }

  reset(count = 0): void {
    this.cancelFrame();
    const next = Math.max(0, Math.floor(count));
    this.revealedValue = next;
    this.targetValue = next;
    this.lastTimestamp = null;
    this.rate = 0;
  }

  setTarget(total: number, animate: boolean): void {
    const nextTotal = Math.max(0, Math.floor(total));
    this.targetValue = nextTotal;
    if (nextTotal <= this.revealedValue) {
      this.cancelFrame();
      if (nextTotal < this.revealedValue) {
        this.revealedValue = nextTotal;
        this.notify(this.revealedValue);
      }
      return;
    }
    if (!animate || prefersReducedMotion() || nextTotal > this.largeDocumentThreshold) {
      // A finished document, a reduced-motion preference or a very large file
      // is shown at once: animating it would only delay readable content.
      this.cancelFrame();
      this.revealedValue = nextTotal;
      this.notify(this.revealedValue);
      return;
    }
    if (this.revealedValue === 0) {
      this.revealedValue = Math.min(INITIAL_BURST, nextTotal);
      this.notify(this.revealedValue);
      if (this.revealedValue >= nextTotal) return;
    }
    const remaining = nextTotal - this.revealedValue;
    const duration = Math.min(this.maxDurationMs, Math.max(this.minDurationMs, remaining / 2.5));
    this.rate = remaining / duration;
    this.schedule();
  }

  destroy(): void {
    this.cancelFrame();
    this.targetValue = 0;
    this.revealedValue = 0;
    this.lastTimestamp = null;
    this.rate = 0;
  }

  private schedule(): void {
    if (this.frame !== null) return;
    if (this.lastTimestamp === null) this.lastTimestamp = this.scheduler.now();
    this.frame = this.scheduler.request(() => this.tick());
  }

  private tick(): void {
    this.frame = null;
    if (this.revealedValue >= this.targetValue) {
      this.lastTimestamp = null;
      return;
    }
    const now = this.scheduler.now();
    const delta = Math.max(0, now - (this.lastTimestamp ?? now));
    // Large live documents are refreshed on a 15 fps budget: rendering every
    // frame would cost more than the animation brings to the reading experience.
    const minimumDelta = this.targetValue > this.mediumDocumentThreshold ? 66 : 0;
    if (delta < minimumDelta) {
      this.schedule();
      return;
    }
    this.lastTimestamp = now;
    // The hard step cap protects small live updates; medium and large documents
    // must still be able to finish within their target duration.
    const stepLimit = this.targetValue > this.mediumDocumentThreshold
      ? Number.MAX_SAFE_INTEGER
      : this.maxStep;
    const step = Math.min(stepLimit, Math.max(1, Math.floor(this.rate * delta)));
    this.revealedValue = Math.min(this.targetValue, this.revealedValue + step);
    this.notify(this.revealedValue);
    if (this.revealedValue < this.targetValue) this.schedule();
    else this.lastTimestamp = null;
  }

  private cancelFrame(): void {
    if (this.frame === null) return;
    this.scheduler.cancel(this.frame);
    this.frame = null;
  }
}
