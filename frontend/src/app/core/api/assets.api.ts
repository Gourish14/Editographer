import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Asset, Waveform } from '../models/api.models';

@Injectable({ providedIn: 'root' })
export class AssetsApi {
  private readonly http = inject(HttpClient);

  list(projectId: string): Observable<Asset[]> {
    return this.http.get<Asset[]>(`/api/projects/${projectId}/assets`);
  }

  waveform(id: string): Observable<Waveform> {
    return this.http.get<Waveform>(`/api/assets/${id}/waveform`);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`/api/assets/${id}`);
  }

  thumbnailUrl(id: string): string {
    return `/api/assets/${id}/thumbnail`;
  }
}
