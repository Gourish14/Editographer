import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatButton } from '@angular/material/button';

import { Asset } from '../../core/models/api.models';
import { BadgeTone, StatusBadge } from '../../shared/ui/status-badge';

const NATIVE_SLOW_MO_FPS = 100;

interface AssetView {
  readonly asset: Asset;
  readonly status: string;
  readonly tone: BadgeTone;
  readonly badges: readonly string[];
  readonly hasThumbnail: boolean;
}

const STATUS: Readonly<Record<Asset['analysisStatus'], { label: string; tone: BadgeTone }>> = {
  PENDING: { label: 'Waiting', tone: 'neutral' },
  RUNNING: { label: 'Analyzing', tone: 'active' },
  DONE: { label: 'Ready', tone: 'good' },
  FAILED: { label: 'Failed', tone: 'bad' },
};

function badgesFor(asset: Asset): string[] {
  const badges: string[] = [];
  if (asset.cameraMode?.startsWith('OSMO360')) {
    badges.push('360');
  }
  if ((asset.fps ?? 0) >= NATIVE_SLOW_MO_FPS) {
    badges.push('Slow-mo');
  }
  if (asset.logProfile) {
    badges.push('D-Log');
  }
  return badges;
}

/** Spec: specs/07-api-and-data.md#angular-screens */
@Component({
  selector: 'app-asset-grid',
  imports: [MatButton, StatusBadge],
  template: `
    <div class="grid">
      @for (view of views(); track view.asset.id) {
        <article class="panel asset">
          @if (view.hasThumbnail) {
            <img [src]="thumbnailUrl()(view.asset.id)" [alt]="view.asset.filename" loading="lazy" />
          } @else {
            <div class="placeholder muted">{{ view.asset.type.toLowerCase() }}</div>
          }
          <strong class="name" [title]="view.asset.filename">{{ view.asset.filename }}</strong>
          <div class="row wrap">
            <app-status-badge [label]="view.status" [tone]="view.tone" />
            @for (badge of view.badges; track badge) {
              <app-status-badge [label]="badge" tone="active" />
            }
          </div>
          <button
            matButton
            [attr.aria-label]="'Remove ' + view.asset.filename"
            (click)="remove.emit(view.asset.id)"
          >
            Remove
          </button>
        </article>
      }
    </div>
  `,
  styles: `
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 150px), 1fr));
      gap: 16px;
    }
    .asset {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 12px;
      min-width: 0;
    }
    img,
    .placeholder {
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      border-radius: 6px;
      background: var(--surface-2);
    }
    .placeholder {
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .name {
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
    .wrap {
      flex-wrap: wrap;
      gap: 6px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AssetGrid {
  readonly assets = input.required<readonly Asset[]>();
  readonly thumbnailUrl = input.required<(id: string) => string>();
  readonly remove = output<string>();

  protected readonly views = computed(() =>
    this.assets().map((asset): AssetView => {
      const status = STATUS[asset.analysisStatus];
      return {
        asset,
        status: status.label,
        tone: status.tone,
        badges: badgesFor(asset),
        hasThumbnail: asset.analysisStatus === 'DONE' && asset.type !== 'MUSIC',
      };
    }),
  );
}
