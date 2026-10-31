import { nextEvening, toInstant } from './start-time';

describe('start time', () => {
  it('picks 22:00 today when it is still ahead', () => {
    expect(nextEvening(new Date(2026, 9, 30, 15, 30))).toBe('2026-10-30T22:00');
  });

  it('picks 22:00 tomorrow once tonight has started', () => {
    expect(nextEvening(new Date(2026, 9, 30, 22, 0))).toBe('2026-10-31T22:00');
    expect(nextEvening(new Date(2026, 11, 31, 23, 10))).toBe('2027-01-01T22:00');
  });

  it('turns a local value into an instant and ignores empty or broken input', () => {
    expect(toInstant('2026-10-30T22:00')).toBe(new Date(2026, 9, 30, 22, 0).toISOString());
    expect(toInstant('')).toBeNull();
    expect(toInstant('nonsense')).toBeNull();
  });
});
