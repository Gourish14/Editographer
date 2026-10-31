import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { RenderEvent } from '../models/api.models';

/** Live render events. Spec: specs/07-api-and-data.md (GET /api/renders/{id}/events) */
@Injectable({ providedIn: 'root' })
export class SseService {
  renderEvents(renderId: string): Observable<RenderEvent> {
    return new Observable((subscriber) => {
      const source = new EventSource(`/api/renders/${renderId}/events`);
      const data = (event: Event) => JSON.parse((event as MessageEvent<string>).data);

      source.addEventListener('progress', (event) =>
        subscriber.next({ type: 'progress', ...data(event) }),
      );
      source.addEventListener('preview-ready', () => subscriber.next({ type: 'preview-ready' }));
      source.addEventListener('done', () => {
        subscriber.next({ type: 'done' });
        subscriber.complete();
      });
      source.addEventListener('failed', (event) => {
        subscriber.next({ type: 'failed', ...data(event) });
        subscriber.complete();
      });

      // EventSource would otherwise reconnect forever after the server closes the stream.
      source.addEventListener('error', () => subscriber.complete());

      return () => source.close();
    });
  }
}
