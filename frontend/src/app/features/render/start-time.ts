/** "Render tonight" helpers. Spec: specs/09-local-setup.md (cool mode) */

const EVENING_HOUR = 22;

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

/** The next 22:00 as the value a datetime-local input takes (local time, no zone). */
export function nextEvening(now: Date): string {
  const evening = new Date(now);
  evening.setHours(EVENING_HOUR, 0, 0, 0);
  if (evening <= now) {
    evening.setDate(evening.getDate() + 1);
  }
  return (
    `${evening.getFullYear()}-${pad(evening.getMonth() + 1)}-${pad(evening.getDate())}` +
    `T${pad(evening.getHours())}:${pad(evening.getMinutes())}`
  );
}

/** A datetime-local value as the ISO instant the API takes, or null when empty or invalid. */
export function toInstant(localValue: string): string | null {
  if (!localValue) {
    return null;
  }
  const date = new Date(localValue);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}
