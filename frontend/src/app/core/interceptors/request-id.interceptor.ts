import { HttpInterceptorFn } from '@angular/common/http';

/** Tags each call so a browser error can be matched to the backend log. */
export const requestIdInterceptor: HttpInterceptorFn = (request, next) =>
  next(request.clone({ setHeaders: { 'X-Request-Id': crypto.randomUUID() } }));
