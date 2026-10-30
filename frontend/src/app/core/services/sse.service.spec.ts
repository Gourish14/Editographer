import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { RenderEvent } from '../models/api.models';
import { SseService } from './sse.service';

class FakeEventSource {
  static last: FakeEventSource;
  readonly listeners = new Map<string, (event: Event) => void>();
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.last = this;
  }

  addEventListener(name: string, listener: (event: Event) => void): void {
    this.listeners.set(name, listener);
  }

  emit(name: string, data?: unknown): void {
    this.listeners.get(name)?.({ data: JSON.stringify(data) } as MessageEvent as Event);
  }

  close(): void {
    this.closed = true;
  }
}

describe('SseService', () => {
  beforeEach(() => vi.stubGlobal('EventSource', FakeEventSource));
  afterEach(() => vi.unstubAllGlobals());

  it('passes progress on and completes when the render is done', () => {
    const received: RenderEvent[] = [];
    let completed = false;
    TestBed.inject(SseService)
      .renderEvents('r1')
      .subscribe({ next: (event) => received.push(event), complete: () => (completed = true) });
    const source = FakeEventSource.last;

    source.emit('progress', { stage: 'COMPOSING', percent: 40, message: 'm' });
    source.emit('preview-ready');
    source.emit('done');

    expect(source.url).toBe('/api/renders/r1/events');
    expect(received).toEqual([
      { type: 'progress', stage: 'COMPOSING', percent: 40, message: 'm' },
      { type: 'preview-ready' },
      { type: 'done' },
    ]);
    expect(completed).toBe(true);
    expect(source.closed).toBe(true);
  });

  it('reports failure with its error', () => {
    const received: RenderEvent[] = [];
    TestBed.inject(SseService)
      .renderEvents('r1')
      .subscribe((event) => received.push(event));

    FakeEventSource.last.emit('failed', { error: 'GPU_OUT_OF_MEMORY' });

    expect(received).toEqual([{ type: 'failed', error: 'GPU_OUT_OF_MEMORY' }]);
  });
});
