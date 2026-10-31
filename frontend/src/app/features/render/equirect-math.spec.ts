import { dragView, isTap, roundTap } from './equirect-math';

describe('equirect maths', () => {
  it('turns the view opposite to a rightward drag', () => {
    const view = dragView(0, 0, 100, 0, 90, 450);
    expect(view.yawDeg).toBeCloseTo(-20);
    expect(view.pitchDeg).toBe(0);
  });

  it('never lets pitch pass the poles', () => {
    expect(dragView(0, 80, 0, 10000, 90, 450).pitchDeg).toBe(85);
    expect(dragView(0, -80, 0, -10000, 90, 450).pitchDeg).toBe(-85);
  });

  it('rounds and clamps a tap', () => {
    expect(roundTap({ x: 0.123456, y: 1.5 })).toEqual({ x: 0.1235, y: 1 });
  });

  it('tells a tap from a drag', () => {
    expect(isTap(1, 2)).toBe(true);
    expect(isTap(10, 0)).toBe(false);
  });
});
