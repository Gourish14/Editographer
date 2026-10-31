import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatFormField, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { EMPTY, catchError, switchMap, timer } from 'rxjs';

import { ProjectsApi } from '../../core/api/projects.api';
import { SystemApi } from '../../core/api/system.api';
import { Project, SystemStatus } from '../../core/models/api.models';
import { BadgeTone, StatusBadge } from '../../shared/ui/status-badge';

/** Spec 09: the worker pauses at 83 C and resumes at 75 C. */
export const PAUSE_TEMP_C = 83;
export const RESUME_TEMP_C = 75;
const SYSTEM_POLL_MS = 3000;

export function temperatureTone(tempC: number): BadgeTone {
  if (tempC >= PAUSE_TEMP_C) {
    return 'bad';
  }
  return tempC >= RESUME_TEMP_C ? 'active' : 'good';
}

@Component({
  selector: 'app-projects-page',
  imports: [
    DatePipe,
    MatButton,
    MatFormField,
    MatInput,
    MatLabel,
    ReactiveFormsModule,
    RouterLink,
    StatusBadge,
  ],
  template: `
    <div class="stack">
      <div class="row spread">
        <h1>Projects</h1>
        @if (system(); as status) {
          <div class="row status" aria-label="System status">
            <app-status-badge
              [label]="status.workerOnline ? 'Worker online' : 'Worker offline'"
              [tone]="status.workerOnline ? 'good' : 'bad'"
            />
            <app-status-badge
              [label]="status.ollamaOnline ? 'Ollama online' : 'Ollama offline'"
              [tone]="status.ollamaOnline ? 'good' : 'neutral'"
            />
            @if (status.gpu; as gpu) {
              <span class="muted">{{ gpu.name }}</span>
              <app-status-badge
                [label]="gpu.tempC + ' °C'"
                [tone]="temperatureTone(gpu.tempC)"
                aria-live="polite"
              />
            }
          </div>
        }
      </div>

      <form class="row" [formGroup]="form" (ngSubmit)="create()">
        <mat-form-field subscriptSizing="dynamic" class="name">
          <mat-label>New project name</mat-label>
          <input matInput formControlName="name" maxlength="255" />
        </mat-form-field>
        <button matButton="filled" type="submit" [disabled]="form.invalid">New project</button>
      </form>

      @if (projects().length === 0) {
        <p class="muted">No projects yet. Name one above to start an edit.</p>
      }
      <div class="grid">
        @for (project of projects(); track project.id) {
          <a class="panel card" [routerLink]="['/projects', project.id]">
            <strong>{{ project.name }}</strong>
            <span class="muted">{{ project.createdAt | date: 'mediumDate' }}</span>
          </a>
        }
      </div>
    </div>
  `,
  styles: `
    .name {
      flex: 1;
      max-width: 420px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 16px;
    }
    .card {
      display: flex;
      flex-direction: column;
      gap: 4px;
      color: var(--text);
      text-decoration: none;
    }
    .card:hover,
    .card:focus-visible {
      border-color: var(--accent);
    }
    .status {
      flex-wrap: wrap;
      justify-content: flex-end;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProjectsPage {
  private readonly api = inject(ProjectsApi);

  protected readonly projects = signal<readonly Project[]>([]);
  protected readonly system = signal<SystemStatus | null>(null);
  protected readonly form = new FormGroup({
    name: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });

  constructor() {
    this.api.list().subscribe((projects) => this.projects.set(projects));
    const systemApi = inject(SystemApi);
    timer(0, SYSTEM_POLL_MS)
      .pipe(
        switchMap(() => systemApi.status().pipe(catchError(() => EMPTY))),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe((status) => this.system.set(status));
  }

  protected readonly temperatureTone = temperatureTone;

  protected create(): void {
    this.api.create(this.form.controls.name.value).subscribe((project) => {
      this.projects.update((projects) => [project, ...projects]);
      this.form.reset();
    });
  }
}
