import { temperatureTone } from './projects-page';

describe('temperatureTone', () => {
  it('turns bad at the pause temperature and active from the resume temperature', () => {
    expect(temperatureTone(60)).toBe('good');
    expect(temperatureTone(75)).toBe('active');
    expect(temperatureTone(82)).toBe('active');
    expect(temperatureTone(83)).toBe('bad');
  });
});
