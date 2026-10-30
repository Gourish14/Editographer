import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { vi } from 'vitest';

import { NotificationService } from './notification.service';

describe('NotificationService', () => {
  const open = vi.fn();

  beforeEach(() => {
    open.mockClear();
    TestBed.configureTestingModule({
      providers: [{ provide: MatSnackBar, useValue: { open } }],
    });
  });

  it('shows errors with a dismiss action', () => {
    TestBed.inject(NotificationService).error('Nope');

    expect(open).toHaveBeenCalledWith('Nope', 'Dismiss', { duration: 5000 });
  });

  it('shows information on its own', () => {
    TestBed.inject(NotificationService).info('Done');

    expect(open).toHaveBeenCalledWith('Done', undefined, { duration: 5000 });
  });
});
