import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AssetsApi } from './assets.api';
import { ProjectsApi } from './projects.api';
import { RendersApi } from './renders.api';
import { SystemApi } from './system.api';

describe('API clients', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('lists, creates, reads and deletes projects', () => {
    const api = TestBed.inject(ProjectsApi);
    api.list().subscribe();
    api.create('Goa').subscribe();
    api.get('p1').subscribe();
    api.delete('p1').subscribe();

    http.expectOne({ method: 'GET', url: '/api/projects' });
    const create = http.expectOne({ method: 'POST', url: '/api/projects' });
    expect(create.request.body).toEqual({ name: 'Goa' });
    http.expectOne({ method: 'GET', url: '/api/projects/p1' });
    http.expectOne({ method: 'DELETE', url: '/api/projects/p1' });
  });

  it('builds asset urls', () => {
    const api = TestBed.inject(AssetsApi);
    api.list('p1').subscribe();
    api.waveform('a1').subscribe();
    api.delete('a1').subscribe();

    http.expectOne('/api/projects/p1/assets');
    http.expectOne('/api/assets/a1/waveform');
    expect(http.expectOne('/api/assets/a1').request.method).toBe('DELETE');
    expect(api.thumbnailUrl('a1')).toBe('/api/assets/a1/thumbnail');
  });

  it('starts, regenerates and cancels renders', () => {
    const api = TestBed.inject(RendersApi);
    api.start('p1', { ratio: '1:1' }).subscribe();
    api.get('r1').subscribe();
    api.regenerate('r1').subscribe();
    api.cancel('r1').subscribe();
    api.styles().subscribe();

    expect(http.expectOne('/api/projects/p1/renders').request.body).toEqual({ ratio: '1:1' });
    http.expectOne('/api/renders/r1');
    expect(http.expectOne('/api/renders/r1/regenerate').request.method).toBe('POST');
    expect(http.expectOne('/api/renders/r1/cancel').request.method).toBe('POST');
    http.expectOne('/api/styles');
    expect(api.previewUrl('r1')).toBe('/api/renders/r1/preview');
    expect(api.downloadUrl('r1')).toBe('/api/renders/r1/download');
  });

  it('reads the system status', () => {
    TestBed.inject(SystemApi).status().subscribe();

    http.expectOne('/api/system');
  });
});
