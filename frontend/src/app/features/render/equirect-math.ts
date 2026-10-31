/** Pure maths for the draggable 360 preview. Spec: specs/08-osmo360.md#ui-additions */

export const MAX_PITCH_DEG = 85;

export interface TapPoint {
  /** 0 to 1 from the left edge of the equirectangular frame. */
  readonly x: number;
  /** 0 to 1 from the top edge of the equirectangular frame. */
  readonly y: number;
}

export function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/** Dragging right turns the view left, like grabbing the scene. Degrees per pixel scale with FOV. */
export function dragView(
  yawDeg: number,
  pitchDeg: number,
  dxPx: number,
  dyPx: number,
  fovDeg: number,
  heightPx: number,
): { yawDeg: number; pitchDeg: number } {
  const degPerPx = fovDeg / Math.max(1, heightPx);
  return {
    yawDeg: yawDeg - dxPx * degPerPx,
    pitchDeg: clamp(pitchDeg + dyPx * degPerPx, -MAX_PITCH_DEG, MAX_PITCH_DEG),
  };
}

/** The tap as the browser sends it: rounded, and never outside 0 to 1. */
export function roundTap(tap: TapPoint): TapPoint {
  const round = (value: number): number => Math.round(clamp(value, 0, 1) * 10000) / 10000;
  return { x: round(tap.x), y: round(tap.y) };
}

/** True when the pointer moved too little to count as a drag, so it is a tap. */
export function isTap(dxPx: number, dyPx: number, slopPx = 4): boolean {
  return Math.hypot(dxPx, dyPx) <= slopPx;
}
