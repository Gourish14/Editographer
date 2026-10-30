import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { NewRender, Render, StylePreset } from '../models/api.models';

@Injectable({ providedIn: 'root' })
export class RendersApi {
  private readonly http = inject(HttpClient);

  start(projectId: string, settings: NewRender): Observable<Render> {
    return this.http.post<Render>(`/api/projects/${projectId}/renders`, settings);
  }

  get(id: string): Observable<Render> {
    return this.http.get<Render>(`/api/renders/${id}`);
  }

  regenerate(id: string): Observable<Render> {
    return this.http.post<Render>(`/api/renders/${id}/regenerate`, null);
  }

  cancel(id: string): Observable<Render> {
    return this.http.post<Render>(`/api/renders/${id}/cancel`, null);
  }

  styles(): Observable<StylePreset[]> {
    return this.http.get<StylePreset[]>('/api/styles');
  }

  previewUrl(id: string): string {
    return `/api/renders/${id}/preview`;
  }

  downloadUrl(id: string): string {
    return `/api/renders/${id}/download`;
  }
}
