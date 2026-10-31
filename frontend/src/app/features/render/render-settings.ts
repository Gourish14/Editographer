import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatFormField, MatHint, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { MatOption, MatSelect } from '@angular/material/select';
import { MatSlideToggle } from '@angular/material/slide-toggle';
import { Router, RouterLink } from '@angular/router';

import { AssetsApi } from '../../core/api/assets.api';
import { RendersApi } from '../../core/api/renders.api';
import { Asset, NewRender, StylePreset } from '../../core/models/api.models';
import { TapPoint } from './equirect-math';
import { Preview360 } from './preview-360';
import { SPEED_TIPS } from './speed-tips';
import { nextEvening, toInstant } from './start-time';

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
    MatHint,
    MatInput,
    MatLabel,
    MatOption,
    MatSelect,
    MatSlideToggle,
    Preview360,
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
          <mat-label>Length in seconds</mat-label>
          <input matInput type="number" min="1" formControlName="lengthSec" />
          <mat-hint>Empty for Auto</mat-hint>
        </mat-form-field>
        <mat-form-field class="wide">
          <mat-label>Prompt (optional)</mat-label>
          <textarea matInput rows="3" formControlName="prompt"></textarea>
        </mat-form-field>
        <mat-slide-toggle class="wide" formControlName="coolMode">Cool mode</mat-slide-toggle>
        <div class="wide row tonight">
          <mat-form-field class="start-at">
            <mat-label>Render tonight: start at</mat-label>
            <input matInput type="datetime-local" formControlName="startAt" />
            <mat-hint>Empty to start now</mat-hint>
          </mat-form-field>
          <button matButton type="button" (click)="tonight()">Tonight at 22:00</button>
          @if (form.controls.startAt.value) {
            <button matButton type="button" (click)="form.controls.startAt.setValue('')">
              Start now
            </button>
          }
        </div>
        @if (clip360(); as clip) {
          <section class="wide follow" aria-label="Subject to follow">
            <h2>Subject to follow</h2>
            <p class="muted">
              Drag to look around {{ clip.filename }}, then tap the person or vehicle to follow.
            </p>
            <app-preview-360 [imageUrl]="thumbnailUrl(clip.id)" (picked)="follow.set($event)" />
            <div class="row">
              @if (follow(); as point) {
                <span>Following the spot at {{ percent(point.x) }}, {{ percent(point.y) }}</span>
                <button matButton type="button" (click)="follow.set(null)">Clear</button>
              } @else {
                <span class="muted">No subject picked, the app will choose.</span>
              }
            </div>
          </section>
        }
        <div class="wide row">
          <button matButton="filled" type="submit" [disabled]="form.invalid || starting()">
            Start render
          </button>
          <a matButton [routerLink]="['/projects', id()]">Back</a>
        </div>
      </form>

      <details class="panel help">
        <summary>Tips for faster renders</summary>
        <ul>
          @for (tip of speedTips; track tip) {
            <li>{{ tip }}</li>
          }
        </ul>
      </details>
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
    .tonight {
      flex-wrap: wrap;
      align-items: flex-start;
      margin-top: 12px;
    }
    .start-at {
      flex: 1 1 260px;
      max-width: 360px;
    }
    .tonight button {
      margin-top: 8px;
    }
    .follow {
      margin-top: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .follow h2,
    .follow p {
      margin: 0;
    }
    .help summary {
      cursor: pointer;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RenderSettingsPage {
  readonly id = input.required<string>();

  private readonly api = inject(RendersApi);
  private readonly assets = inject(AssetsApi);
  private readonly router = inject(Router);

  protected readonly ratios = RATIOS;
  protected readonly qualities = QUALITIES;
  protected readonly frameRates = FRAME_RATES;
  protected readonly modes = MODES;
  protected readonly speedTips = SPEED_TIPS;
  protected readonly styles = signal<readonly StylePreset[]>([]);
  protected readonly starting = signal(false);
  protected readonly projectAssets = signal<readonly Asset[]>([]);
  protected readonly follow = signal<TapPoint | null>(null);
  /** The first analyzed 360 clip: its thumbnail is the equirectangular frame to tap on. */
  protected readonly clip360 = computed(
    () =>
      this.projectAssets().find(
        (asset) => asset.cameraMode?.startsWith('OSMO360') && asset.analysisStatus === 'DONE',
      ) ?? null,
  );

  protected readonly form = new FormGroup({
    ratio: new FormControl('9:16', { nonNullable: true }),
    quality: new FormControl('4K', { nonNullable: true }),
    fps: new FormControl(30, { nonNullable: true }),
    style: new FormControl('auto', { nonNullable: true }),
    mode: new FormControl('fast', { nonNullable: true }),
    lengthSec: new FormControl<number | null>(null, [Validators.min(1)]),
    prompt: new FormControl('', { nonNullable: true }),
    coolMode: new FormControl(false, { nonNullable: true }),
    startAt: new FormControl('', { nonNullable: true }),
  });

  constructor() {
    this.api.styles().subscribe((styles) => this.styles.set(styles));
    effect(() => this.assets.list(this.id()).subscribe((list) => this.projectAssets.set(list)));
  }

  protected thumbnailUrl(id: string): string {
    return this.assets.thumbnailUrl(id);
  }

  protected percent(value: number): string {
    return `${Math.round(value * 100)}%`;
  }

  protected tonight(): void {
    this.form.controls.startAt.setValue(nextEvening(new Date()));
  }

  protected start(): void {
    const { startAt, ...values } = this.form.getRawValue();
    const point = this.follow();
    const settings: NewRender = {
      ...values,
      prompt: values.prompt.trim() || null,
      startAt: toInstant(startAt),
      // The preview shows the clip's thumbnail, a frame from the start of the clip.
      followPoint: point && this.clip360() ? { x: point.x, y: point.y, timeSec: 0 } : null,
    };
    this.starting.set(true);
    this.api.start(this.id(), settings).subscribe({
      next: (render) => void this.router.navigate(['/renders', render.id]),
      error: () => this.starting.set(false),
    });
  }
}
