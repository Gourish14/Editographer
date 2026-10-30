import { Injectable, inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

const SHOW_MS = 5000;

/** The single way user-facing messages appear. */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly snackBar = inject(MatSnackBar);

  error(message: string): void {
    this.snackBar.open(message, 'Dismiss', { duration: SHOW_MS });
  }

  info(message: string): void {
    this.snackBar.open(message, undefined, { duration: SHOW_MS });
  }
}
