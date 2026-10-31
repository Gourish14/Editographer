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
import { MatAnchor, MatButton } from '@angular/material/button';
import { MatProgressBar } from '@angular/material/progress-bar';
import { Router, RouterLink } from '@angular/router';
import { Subscription, timer } from 'rxjs';

import { RendersApi } from '../../core/api/renders.api';
import { Render, RenderEvent } from '../../core/models/api.models';
import { SseService } from '../../core/services/sse.service';
import { StatusBadge } from '../../shared/ui/status-badge';

const RESYNC_MS = 2000;
const FINISHED = new Set(['DONE', 'FAILED', 'CANCELLED']);

/** The log lines about prompt requests the editor could not apply. */
export function skippedRequests(log: readonly string[] | undefined): readonly string[] {
  return (log ?? []).filter((line) => /skipped/i.test(line));
}

/** Progress and result of one render. Spec: specs/07-api-and-data.md#angular-screens */
@Component({
  selector: 'app-render-page',
  imports: [MatAnchor, MatButton, MatProgressBar, RouterLink, StatusBadge],
  template: `
    @if (render(); as current) {
      <div class="stack">
        <div class="row spread">
          <h1>{{ current.settings.ratio }} {{ current.settings.quality }} render</h1>
          <app-status-badge [label]="current.status.toLowerCase()" [tone]="tone()" />
        </div>

        @if (!finished()) {
          <section class="panel" aria-label="Progress">
            <div class="row spread">
              <span>{{ message() || waitingLabel() || stageLabel() }}</span>
              <span class="muted">{{ percent() }}%</span>
            </div>
            <mat-progress-bar mode="determinate" [value]="percent()" />
            <button matButton class="cancel" (click)="cancel()">Cancel</button>
          </section>
        }

        @if (current.status === 'FAILED' || current.status === 'CANCELLED') {
          <p class="panel problem">{{ current.error || 'This render stopped.' }}</p>
        }

        @if (videoUrl(); as url) {
          <section class="panel" aria-label="Video">
            <video controls [src]="url" [class.tall]="isTall()"></video>
          </section>
        }

        @if (current.status === 'DONE') {
          <div class="row">
            <a matButton="filled" [href]="downloadUrl()" download>Download</a>
            <button matButton="outlined" (click)="regenerate()">Make another version</button>
          </div>
          @if (current.editPlan; as plan) {
            <section class="panel" aria-label="Plan summary">
              <h2>Plan</h2>
              <p>
                {{ plan.style }} style · {{ plan.segments.length }} cuts ·
                {{ effectCount() }} effects
              </p>
            </section>
            @if (skipped().length > 0) {
              <section class="panel" aria-label="Skipped prompt requests">
                <h2>Skipped prompt requests</h2>
                @for (note of skipped(); track note) {
                  <p class="muted">{{ note }}</p>
                }
              </section>
            }
          }
        }

        <a [routerLink]="['/projects', current.projectId]">Back to project</a>
      </div>
    }
  `,
  styles: `
    .cancel {
      margin-top: 8px;
    }
    video {
      display: block;
      width: 100%;
      max-height: 70vh;
      background: #000;
    }
    video.tall {
      width: auto;
      max-width: 100%;
      margin: 0 auto;
    }
    p {
      margin: 0;
    }
    .problem {
      color: var(--bad);
    }
    a:not([matButton]) {
      color: var(--accent);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RenderPage {
  readonly id = input.required<string>();

  private readonly api = inject(RendersApi);
  private readonly sse = inject(SseService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly render = signal<Render | null>(null);
  protected readonly percent = signal(0);
  protected readonly message = signal('');
  private readonly previewReady = signal(false);
  private listeningTo: string | null = null;
  private subscription: Subscription | null = null;

  protected readonly finished = computed(() => FINISHED.has(this.render()?.status ?? ''));
  protected readonly stageLabel = computed(() => this.render()?.stage ?? 'Waiting in the queue');
  protected readonly waitingLabel = computed(() => {
    const current = this.render();
    const startAt = current?.status === 'QUEUED' ? current.settings.startAt : null;
    return startAt && new Date(startAt) > new Date()
      ? `Scheduled for ${new Date(startAt).toLocaleString()}`
      : '';
  });
  protected readonly tone = computed(() => {
    const status = this.render()?.status;
    if (status === 'DONE') {
      return 'good';
    }
    return status === 'FAILED' ? 'bad' : 'active';
  });
  protected readonly videoUrl = computed(() => {
    const current = this.render();
    if (current?.status === 'DONE') {
      return this.api.previewUrl(current.id);
    }
    return this.previewReady() ? this.api.previewUrl(this.id()) : null;
  });
  protected readonly downloadUrl = computed(() => this.api.downloadUrl(this.id()));
  protected readonly isTall = computed(() => {
    const [across, down] = (this.render()?.settings.ratio ?? '16:9').split(':').map(Number);
    return down > across;
  });
  /** Spec 05: a request that maps to nothing is skipped and listed in the job log. */
  protected readonly skipped = computed(() => skippedRequests(this.render()?.editPlan?.log));
  protected readonly effectCount = computed(
    () =>
      this.render()?.editPlan?.segments.reduce(
        (total, segment) => total + segment.effects.length,
        0,
      ) ?? 0,
  );

  constructor() {
    effect(() => this.load());
    this.destroyRef.onDestroy(() => this.subscription?.unsubscribe());
  }

  protected cancel(): void {
    this.api.cancel(this.id()).subscribe((render) => this.render.set(render));
  }

  protected regenerate(): void {
    this.api
      .regenerate(this.id())
      .subscribe((render) => void this.router.navigate(['/renders', render.id]));
  }

  private load(): void {
    const id = this.id();
    this.api.get(id).subscribe((render) => {
      if (id !== this.id()) {
        return;
      }
      this.render.set(render);
      this.percent.set(render.progress);
      this.previewReady.set(render.previewReady);
      if (!FINISHED.has(render.status)) {
        this.listen(id);
      }
    });
  }

  /** One stream per render: "Make another version" reuses this page with a new id. */
  private listen(id: string): void {
    if (this.listeningTo === id) {
      return;
    }
    this.subscription?.unsubscribe();
    this.listeningTo = id;
    this.message.set('');
    this.subscription = this.sse.renderEvents(id).subscribe({
      next: (event) => this.apply(event),
      // The stream ended without a final event (a cancel, a restart): ask again, then reconnect.
      complete: () => this.resync(id),
    });
  }

  private resync(id: string): void {
    if (this.listeningTo !== id) {
      return;
    }
    this.listeningTo = null;
    timer(RESYNC_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.id() === id && this.load());
  }

  private apply(event: RenderEvent): void {
    switch (event.type) {
      case 'progress':
        this.percent.set(event.percent);
        this.message.set(event.message);
        break;
      case 'preview-ready':
        this.previewReady.set(true);
        break;
      default:
        this.load();
    }
  }
}
