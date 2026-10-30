import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, ErrorHandler, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { routes } from './app.routes';
import { errorInterceptor } from './core/interceptors/error.interceptor';
import { requestIdInterceptor } from './core/interceptors/request-id.interceptor';
import { ClientErrorHandler } from './core/services/client-error-handler';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    { provide: ErrorHandler, useClass: ClientErrorHandler },
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([requestIdInterceptor, errorInterceptor])),
  ],
};
