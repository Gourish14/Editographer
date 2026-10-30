import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Asset } from '../../core/models/api.models';
import { AssetGrid } from './asset-grid';

function asset(overrides: Partial<Asset>): Asset {
  return {
    id: 'a1',
    projectId: 'p1',
    type: 'VIDEO',
    filename: 'clip.mp4',
    sizeBytes: 1,
    analysisStatus: 'DONE',
    durationSec: 1,
    width: 1,
    height: 1,
    fps: 30,
    cameraMode: 'FLAT',
    logProfile: null,
    createdAt: '',
    ...overrides,
  };
}

describe('AssetGrid', () => {
  let fixture: ComponentFixture<AssetGrid>;

  function show(assets: Asset[]): HTMLElement {
    fixture = TestBed.createComponent(AssetGrid);
    fixture.componentRef.setInput('assets', assets);
    fixture.componentRef.setInput('thumbnailUrl', (id: string) => `/thumb/${id}`);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows the thumbnail of a finished clip', () => {
    expect(show([asset({})]).querySelector('img')?.getAttribute('src')).toBe('/thumb/a1');
  });

  it('shows a placeholder for music and for clips still analyzing', () => {
    const element = show([
      asset({ id: 'm', type: 'MUSIC' }),
      asset({ id: 'v', analysisStatus: 'RUNNING' }),
    ]);

    expect(element.querySelector('img')).toBeNull();
    expect(element.textContent).toContain('Analyzing');
  });

  it('marks 360, slow-mo and D-Log clips', () => {
    const text = show([
      asset({ cameraMode: 'OSMO360_PANO_4K100', fps: 100, logProfile: 'DLOGM' }),
    ]).textContent;

    expect(text).toContain('360');
    expect(text).toContain('Slow-mo');
    expect(text).toContain('D-Log');
  });
});
