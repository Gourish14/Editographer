import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  computed,
  input,
  viewChild,
} from '@angular/core';
import WaveSurfer from 'wavesurfer.js';

import { Waveform } from '../../core/models/api.models';

const HEIGHT_PX = 88;
const PERCENT = 100;
const WAVE_COLOR = '#5fd4e3';

interface SectionBlock {
  readonly kind: string;
  readonly left: number;
  readonly width: number;
}

/** Draws the song with its sections and downbeats. Spec: specs/07-api-and-data.md#angular-screens */
@Component({
  selector: 'app-music-waveform',
  template: `
    <div class="sections" aria-hidden="true">
      @for (section of sections(); track section.left) {
        <span
          class="section"
          [class]="'section ' + section.kind"
          [style.left.%]="section.left"
          [style.width.%]="section.width"
          >{{ section.kind }}</span
        >
      }
    </div>
    <div class="wave">
      <div #wave></div>
      @for (mark of downbeats(); track mark) {
        <span class="downbeat" [style.left.%]="mark"></span>
      }
    </div>
    <p class="muted">{{ data().beats.length }} beats · {{ bpm() }} BPM</p>
  `,
  styles: `
    .sections {
      position: relative;
      height: 22px;
      margin-bottom: 4px;
    }
    .section {
      position: absolute;
      top: 0;
      padding-left: 6px;
      overflow: hidden;
      font-size: 12px;
      line-height: 22px;
      white-space: nowrap;
      background: var(--surface-2);
      border-left: 1px solid var(--border);
      color: var(--text-muted);
    }
    .section.drop {
      background: var(--accent-soft);
      color: var(--accent);
    }
    .wave {
      position: relative;
    }
    .downbeat {
      position: absolute;
      top: 0;
      bottom: 0;
      width: 1px;
      background: var(--border);
      pointer-events: none;
    }
    p {
      margin: 8px 0 0;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MusicWaveform implements AfterViewInit, OnDestroy {
  readonly data = input.required<Waveform>();

  private readonly wave = viewChild.required<ElementRef<HTMLElement>>('wave');
  private surfer: WaveSurfer | null = null;

  protected readonly sections = computed((): SectionBlock[] => {
    const { durationSec, sections } = this.data();
    return sections.map((section) => ({
      kind: section.kind,
      left: (section.start / durationSec) * PERCENT,
      width: ((section.end - section.start) / durationSec) * PERCENT,
    }));
  });

  protected readonly downbeats = computed(() => {
    const { durationSec, downbeats } = this.data();
    return downbeats.map((time) => (time / durationSec) * PERCENT);
  });

  protected readonly bpm = computed(() => {
    const { beats, durationSec } = this.data();
    return Math.round((beats.length / durationSec) * 60);
  });

  ngAfterViewInit(): void {
    const { peaks, durationSec } = this.data();
    this.surfer = WaveSurfer.create({
      container: this.wave().nativeElement,
      peaks: [Array.from(peaks)],
      duration: durationSec,
      height: HEIGHT_PX,
      waveColor: WAVE_COLOR,
      interact: false,
      cursorWidth: 0,
    });
  }

  ngOnDestroy(): void {
    this.surfer?.destroy();
  }
}
