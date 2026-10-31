import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatAnchor } from '@angular/material/button';
import { Router, RouterLink } from '@angular/router';
import { catchError, EMPTY, interval, switchMap } from 'rxjs';

import { AssetsApi } from '../../core/api/assets.api';
import { ProjectsApi } from '../../core/api/projects.api';
import { Asset, ProjectDetail, Render, Waveform } from '../../core/models/api.models';
import { AssetGrid } from './asset-grid';
import { MusicWaveform } from './music-waveform';
import { UploadZone } from './upload-zone';

const POLL_MS = 2000;

/** Assets are polled while analysis runs: there is no per-project event stream (CR-011). */
@Component({
  selector: 'app-project-page',
  imports: [AssetGrid, MatAnchor, MusicWaveform, RouterLink, UploadZone],
  template: `
    @if (detail(); as project) {
      <div class="stack">
        <div class="row spread">
          <h1>{{ project.project.name }}</h1>
          <a
            matButton="filled"
            [routerLink]="['render']"
            [class.blocked]="!canRender()"
            [attr.aria-disabled]="!canRender()"
            [attr.tabindex]="canRender() ? null : -1"
            >Render</a
          >
        </div>
        @if (!canRender()) {
          <p class="muted">Add at least one clip and one song, and wait for analysis to finish.</p>
        }

        <section class="panel" aria-label="Upload">
          <app-upload-zone [projectId]="id()" (uploaded)="refresh()" />
        </section>

        @if (waveform(); as song) {
          <section class="panel" aria-label="Music">
            <h2>Music</h2>
            <app-music-waveform [data]="song" />
          </section>
        }

        @if (assets().length > 0) {
          <section aria-label="Assets">
            <h2>Assets</h2>
            <app-asset-grid
              [assets]="assets()"
              [thumbnailUrl]="thumbnailUrl"
              (remove)="remove($event)"
            />
          </section>
        }

        @if (project.renders.length > 0) {
          <section aria-label="Renders">
            <h2>Renders</h2>
            <ul class="renders">
              @for (render of project.renders; track render.id) {
                <li>
                  <a [routerLink]="['/renders', render.id]">{{ label(render) }}</a>
                </li>
              }
            </ul>
          </section>
        }
      </div>
    }
  `,
  styles: `
    .blocked {
      pointer-events: none;
      opacity: 0.5;
    }
    .renders {
      margin: 0;
      padding-left: 18px;
    }
    a {
      color: var(--accent);
    }
    p {
      margin: 0;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProjectPage {
  readonly id = input.required<string>();

  private readonly projects = inject(ProjectsApi);
  private readonly assetsApi = inject(AssetsApi);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly detail = signal<ProjectDetail | null>(null);
  protected readonly assets = signal<readonly Asset[]>([]);
  protected readonly waveform = signal<Waveform | null>(null);
  protected readonly thumbnailUrl = (assetId: string): string =>
    this.assetsApi.thumbnailUrl(assetId);

  protected readonly canRender = computed(() => {
    const ready = this.assets().filter((asset) => asset.analysisStatus === 'DONE');
    return (
      ready.some((asset) => asset.type === 'MUSIC') && ready.some((asset) => asset.type !== 'MUSIC')
    );
  });

  private readonly song = computed(() =>
    this.assets().find((asset) => asset.type === 'MUSIC' && asset.analysisStatus === 'DONE'),
  );
  private loadedWaveformFor: string | null = null;

  constructor() {
    effect(() => this.refresh());
    effect(() => this.loadWaveform(this.song()));
    interval(POLL_MS)
      .pipe(
        switchMap(() => (this.isAnalyzing() ? this.assetsApi.list(this.id()) : EMPTY)),
        catchError(() => EMPTY),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((assets) => this.assets.set(assets));
  }

  protected refresh(): void {
    this.projects.get(this.id()).subscribe({
      next: (detail) => {
        this.detail.set(detail);
        this.assets.set(detail.assets);
      },
      error: () => void this.router.navigateByUrl('/'),
    });
  }

  protected remove(assetId: string): void {
    this.assetsApi.delete(assetId).subscribe(() => this.refresh());
  }

  protected label(render: Render): string {
    const { ratio, quality, style } = render.settings;
    return `${ratio} ${quality} ${style} · ${render.status.toLowerCase()}`;
  }

  private isAnalyzing(): boolean {
    return this.assets().some(
      (asset) => asset.analysisStatus === 'PENDING' || asset.analysisStatus === 'RUNNING',
    );
  }

  private loadWaveform(song: Asset | undefined): void {
    if (song && song.id !== this.loadedWaveformFor) {
      this.loadedWaveformFor = song.id;
      this.assetsApi.waveform(song.id).subscribe((waveform) => this.waveform.set(waveform));
    }
  }
}
