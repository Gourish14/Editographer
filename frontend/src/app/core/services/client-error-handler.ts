import { HttpBackend, HttpClient } from '@angular/common/http';
import { ErrorHandler, Injectable, inject } from '@angular/core';

/** Sends browser errors to the backend log. Spec: specs/11-coding-standards.md#6 */
@Injectable()
export class ClientErrorHandler implements ErrorHandler {
  // HttpBackend skips the interceptors, so a failed report cannot trigger another report.
  private readonly http = new HttpClient(inject(HttpBackend));

  handleError(error: unknown): void {
    console.error(error);
    const message = error instanceof Error ? (error.stack ?? error.message) : String(error);
    this.http.post('/api/client-logs', { message }).subscribe({ error: () => undefined });
  }
}
