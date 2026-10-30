import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type BadgeTone = 'neutral' | 'active' | 'good' | 'bad';

@Component({
  selector: 'app-status-badge',
  template: `<span class="badge" [class]="'badge ' + tone()">{{ label() }}</span>`,
  styles: `
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      line-height: 18px;
      background: var(--surface-2);
      color: var(--text-muted);
    }
    .active {
      background: var(--accent-soft);
      color: var(--accent);
    }
    .good {
      background: var(--good-soft);
      color: var(--good);
    }
    .bad {
      background: var(--bad-soft);
      color: var(--bad);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StatusBadge {
  readonly label = input.required<string>();
  readonly tone = input<BadgeTone>('neutral');
}
