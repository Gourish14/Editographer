import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { ProblemDetail } from '../models/api.models';
import { NotificationService } from '../services/notification.service';

const MESSAGES: Readonly<Record<string, string>> = {
  PROJECT_NOT_FOUND: 'That project no longer exists.',
  ASSET_NOT_FOUND: 'That file is not available yet.',
  ASSET_UNSUPPORTED: 'That file type is not supported.',
  RENDER_NOT_FOUND: 'That render no longer exists.',
  RENDER_NOT_READY: 'That video is not ready yet.',
  RENDER_ALREADY_FINISHED: 'That render has already finished.',
  UPLOAD_FAILED: 'The upload could not start.',
  WORKER_UNAVAILABLE: 'The AI worker is not running.',
  INTERNAL_ERROR: 'Something went wrong on the server.',
};

/** Turns a ProblemDetail into a readable message. Spec: specs/11-coding-standards.md#5 */
export function messageFor(problem: ProblemDetail | null | undefined): string {
  const code = problem?.errorCode;
  if (code && MESSAGES[code]) {
    return MESSAGES[code];
  }
  return problem?.detail ?? 'The server could not be reached.';
}

export const errorInterceptor: HttpInterceptorFn = (request, next) => {
  const notifications = inject(NotificationService);
  return next(request).pipe(
    catchError((error: HttpErrorResponse) => {
      notifications.error(messageFor(error.error as ProblemDetail | null));
      return throwError(() => error);
    }),
  );
};
