import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { NotificationService } from '../services/notification.service';
import { errorInterceptor, messageFor } from './error.interceptor';
import { requestIdInterceptor } from './request-id.interceptor';

describe('interceptors', () => {
  const error = vi.fn();
  let http: HttpTestingController;
  let client: HttpClient;

  beforeEach(() => {
    error.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([requestIdInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
        { provide: NotificationService, useValue: { error } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    client = TestBed.inject(HttpClient);
  });

  it('adds a request id to every call', () => {
    client.get('/api/x').subscribe();

    expect(http.expectOne('/api/x').request.headers.get('X-Request-Id')).toBeTruthy();
  });

  it('shows a readable message for a known error code', () => {
    client.get('/api/x').subscribe({ error: () => undefined });

    http
      .expectOne('/api/x')
      .flush({ errorCode: 'WORKER_UNAVAILABLE' }, { status: 503, statusText: 'Unavailable' });

    expect(error).toHaveBeenCalledWith('The AI worker is not running.');
  });

  it('falls back to the server detail, then to a generic message', () => {
    expect(messageFor({ errorCode: 'NEW_CODE', detail: 'Details' })).toBe('Details');
    expect(messageFor(null)).toBe('The server could not be reached.');
  });
});
