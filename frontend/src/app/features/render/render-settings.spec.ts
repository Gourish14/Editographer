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

  it('sends the 360 clip the subject was tapped on, and clears the point when the clip changes', () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(RenderSettingsPage);
    fixture.componentRef.setInput('id', 'p1');
    fixture.detectChanges();
    http.expectOne('/api/styles').flush([]);
    const clip = (id: string) => ({
      id,
      type: 'VIDEO',
      filename: `${id}.osv`,
      analysisStatus: 'DONE',
      cameraMode: 'OSMO360_PANO_8K',
    });
    http.expectOne('/api/projects/p1/assets').flush([clip('a'), clip('b')]);

    const page = fixture.componentInstance as unknown as {
      pick(point: { x: number; y: number } | null, clipId: string | null): void;
      choose360(id: string): void;
      start(): void;
    };
    page.pick({ x: 0.25, y: 0.5 }, 'a');
    page.choose360('b');
    page.start();
    const cleared = http.expectOne({ method: 'POST', url: '/api/projects/p1/renders' });
    expect(cleared.request.body.followPoint).toBeNull();

    page.pick({ x: 0.25, y: 0.5 }, 'b');
    page.start();
    const picked = http.expectOne({ method: 'POST', url: '/api/projects/p1/renders' });
    expect(picked.request.body.followPoint).toEqual({
      x: 0.25,
      y: 0.5,
      timeSec: 0,
      assetId: 'b',
    });
    http.verify();
  });
});
