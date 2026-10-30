import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { SystemStatus } from '../models/api.models';

@Injectable({ providedIn: 'root' })
export class SystemApi {
  private readonly http = inject(HttpClient);

  status(): Observable<SystemStatus> {
    return this.http.get<SystemStatus>('/api/system');
  }
}
