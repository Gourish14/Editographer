import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatFormField, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { MatOption, MatSelect } from '@angular/material/select';
import { MatSlideToggle } from '@angular/material/slide-toggle';
import { Router, RouterLink } from '@angular/router';

import { RendersApi } from '../../core/api/renders.api';
import { NewRender, StylePreset } from '../../core/models/api.models';

const RATIOS = ['9:16', '16:9', '1:1', '4:5', '4:3', '21:9'];
const QUALITIES = ['4K', '6K', '8K'];
const FRAME_RATES = [24, 30, 60];
const MODES = [
  { id: 'preview', label: 'Preview' },
  { id: 'fast', label: 'Fast' },
  { id: 'max', label: 'Max quality' },
];

/** Every option from specs/00-overview.md#user-choices. */
@Component({
  selector: 'app-render-settings',
  imports: [
    MatButton,
    MatFormField,
    MatInput,
    MatLabel,
    MatOption,
    MatSelect,
    MatSlideToggle,
    ReactiveFormsModule,
    RouterLink,
  ],
  template: `
    <div class="stack">
      <h1>Render settings</h1>
      <form class="panel fields" [formGroup]="form" (ngSubmit)="start()">
        <mat-form-field>
          <mat-label>Aspect ratio</mat-label>
          <mat-select formControlName="ratio">
            @for (ratio of ratios; track ratio) {
              <mat-option [value]="ratio">{{ ratio }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field>
          <mat-label>Quality</mat-label>
          <mat-select formControlName="quality">
            @for (quality of qualities; track quality) {
              <mat-option [value]="quality">{{ quality }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field>
          <mat-label>Frame rate</mat-label>
          <mat-select formControlName="fps">
            @for (fps of frameRates; track fps) {
              <mat-option [value]="fps">{{ fps }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field>
          <mat-label>Style</mat-label>
          <mat-select formControlName="style">
            @for (style of styles(); track style.id) {
              <mat-option [value]="style.id">{{ style.name }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field>
          <mat-label>Render mode</mat-label>
          <mat-select formControlName="mode">
            @for (mode of modes; track mode.id) {
              <mat-option [value]="mode.id">{{ mode.label }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field>
          <mat-label>Length in seconds (empty for Auto)</mat-label>
          <input matInput type="number" min="1" formControlName="lengthSec" />
        </mat-form-field>
        <mat-form-field class="wide">
          <mat-label>Prompt (optional)</mat-label>
          <textarea matInput rows="3" formControlName="prompt"></textarea>
        </mat-form-field>
        <mat-slide-toggle class="wide" formControlName="coolMode">Cool mode</mat-slide-toggle>
        <div class="wide row">
          <button matButton="filled" type="submit" [disabled]="form.invalid || starting()">
            Start render
          </button>
          <a matButton [routerLink]="['/projects', id()]">Back</a>
        </div>
      </form>
    </div>
  `,
  styles: `
    .fields {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 8px 16px;
    }
    .wide {
      grid-column: 1 / -1;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RenderSettingsPage {
  readonly id = input.required<string>();

  private readonly api = inject(RendersApi);
  private readonly router = inject(Router);

  protected readonly ratios = RATIOS;
  protected readonly qualities = QUALITIES;
  protected readonly frameRates = FRAME_RATES;
  protected readonly modes = MODES;
  protected readonly styles = signal<readonly StylePreset[]>([]);
  protected readonly starting = signal(false);

  protected readonly form = new FormGroup({
    ratio: new FormControl('9:16', { nonNullable: true }),
    quality: new FormControl('4K', { nonNullable: true }),
    fps: new FormControl(30, { nonNullable: true }),
    style: new FormControl('auto', { nonNullable: true }),
    mode: new FormControl('fast', { nonNullable: true }),
    lengthSec: new FormControl<number | null>(null, [Validators.min(1)]),
    prompt: new FormControl('', { nonNullable: true }),
    coolMode: new FormControl(false, { nonNullable: true }),
  });

  constructor() {
    this.api.styles().subscribe((styles) => this.styles.set(styles));
  }

  protected start(): void {
    const values = this.form.getRawValue();
    const settings: NewRender = { ...values, prompt: values.prompt.trim() || null };
    this.starting.set(true);
    this.api.start(this.id(), settings).subscribe({
      next: (render) => void this.router.navigate(['/renders', render.id]),
      error: () => this.starting.set(false),
    });
  }
}
