import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Project, ProjectDetail } from '../models/api.models';

@Injectable({ providedIn: 'root' })
export class ProjectsApi {
  private readonly http = inject(HttpClient);

  list(): Observable<Project[]> {
    return this.http.get<Project[]>('/api/projects');
  }

  get(id: string): Observable<ProjectDetail> {
    return this.http.get<ProjectDetail>(`/api/projects/${id}`);
  }

  create(name: string): Observable<Project> {
    return this.http.post<Project>('/api/projects', { name });
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`/api/projects/${id}`);
  }
}
