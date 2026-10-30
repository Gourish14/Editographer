import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatProgressBar } from '@angular/material/progress-bar';

import { NotificationService } from '../../core/services/notification.service';
import { UploadService } from '../../core/services/upload.service';

interface ActiveUpload {
  readonly name: string;
  readonly percent: number;
}

/** Drag-and-drop resumable uploads. Spec: specs/07-api-and-data.md#angular-screens */
@Component({
  selector: 'app-upload-zone',
  imports: [MatProgressBar],
  template: `
    <label
      class="zone"
      [class.over]="dragging()"
      (dragover)="$event.preventDefault(); dragging.set(true)"
      (dragleave)="dragging.set(false)"
      (drop)="drop($event)"
    >
      <input type="file" multiple (change)="pick($event)" aria-label="Choose files to upload" />
      <strong>Drop clips, photos and music here</strong>
      <span class="muted">or click to choose. MP4, MOV, OSV, LRF, JPG, PNG, HEIC, MP3, WAV, M4A, FLAC</span>
    </label>
    @for (upload of uploads(); track upload.name) {
      <div class="upload">
        <div class="row spread">
          <span>{{ upload.name }}</span>
          <span class="muted">{{ upload.percent }}%</span>
        </div>
        <mat-progress-bar mode="determinate" [value]="upload.percent" />
      </div>
    }
  `,
  styles: `
    .zone {
      display: flex;
      flex-direction: column;
      gap: 4px;
      align-items: center;
      padding: 32px 16px;
      border: 1px dashed var(--border);
      border-radius: 10px;
      text-align: center;
      cursor: pointer;
    }
    .zone.over,
    .zone:hover,
    .zone:focus-within {
      border-color: var(--accent);
    }
    input {
      position: absolute;
      opacity: 0;
      width: 1px;
      height: 1px;
    }
    .upload {
      margin-top: 12px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UploadZone {
  readonly projectId = input.required<string>();
  readonly uploaded = output<void>();

  protected readonly dragging = signal(false);
  protected readonly uploads = signal<readonly ActiveUpload[]>([]);

  private readonly service = inject(UploadService);
  private readonly notifications = inject(NotificationService);
  private readonly destroyRef = inject(DestroyRef);

  protected drop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    this.start(Array.from(event.dataTransfer?.files ?? []));
  }

  protected pick(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.start(Array.from(input.files ?? []));
    input.value = '';
  }

  private start(files: readonly File[]): void {
    for (const file of files) {
      this.show(file.name, 0);
      this.service
        .upload(this.projectId(), file)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (percent) => this.show(file.name, percent),
          error: () => {
            this.hide(file.name);
            this.notifications.error(`Could not upload ${file.name}.`);
          },
          complete: () => {
            this.hide(file.name);
            this.uploaded.emit();
          },
        });
    }
  }

  private show(name: string, percent: number): void {
    this.uploads.update((uploads) => [
      ...uploads.filter((upload) => upload.name !== name),
      { name, percent },
    ]);
  }

  private hide(name: string): void {
    this.uploads.update((uploads) => uploads.filter((upload) => upload.name !== name));
  }
}
