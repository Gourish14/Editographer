import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { ClientErrorHandler } from './client-error-handler';

describe('ClientErrorHandler', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), ClientErrorHandler],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => vi.restoreAllMocks());

  it('sends the error to the backend log', () => {
    TestBed.inject(ClientErrorHandler).handleError('broken');

    const request = http.expectOne({ method: 'POST', url: '/api/client-logs' });
    expect(request.request.body).toEqual({ message: 'broken' });
  });

  it('stays quiet when the report itself fails', () => {
    TestBed.inject(ClientErrorHandler).handleError(new Error('broken'));

    http
      .expectOne('/api/client-logs')
      .flush(null, { status: 500, statusText: 'Server Error' });
  });
});
