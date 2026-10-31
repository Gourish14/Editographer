import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { RenderSettingsPage } from './render-settings';

describe('RenderSettingsPage', () => {
  it('sends the Render tonight start time as an instant and no follow point without a 360 clip', () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(RenderSettingsPage);
    fixture.componentRef.setInput('id', 'p1');
    fixture.detectChanges();
    http.expectOne('/api/styles').flush([]);
    http.expectOne('/api/projects/p1/assets').flush([]);

    const page = fixture.componentInstance as unknown as {
      form: { controls: { startAt: { setValue(value: string): void } } };
      start(): void;
    };
    page.form.controls.startAt.setValue('2026-10-30T22:00');
    page.start();

    const request = http.expectOne({ method: 'POST', url: '/api/projects/p1/renders' });
    expect(request.request.body.startAt).toBe(new Date(2026, 9, 30, 22, 0).toISOString());
    expect(request.request.body.followPoint).toBeNull();
    http.verify();
  });
});
