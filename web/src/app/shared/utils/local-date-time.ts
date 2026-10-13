/**
 * Dates and times between the API and the person, in the browser's time zone. The API sends
 * and receives instants in UTC (ISO 8601 with `Z`) and calendar dates as `YYYY-MM-DD`; what
 * the person reads and types is in the browser's time zone and the active language. None of
 * these functions takes a time zone: the browser's is always the one used.
 */

/**
 * The instant of a wall-clock time (`HH:MM`) on a calendar date (`YYYY-MM-DD`) in the
 * browser's time zone, as ISO 8601 in UTC.
 */
export function localDateTimeToIso(date: string, time: string): string {
  const [year = 0, month = 1, day = 1] = date.split('-').map(Number);
  const [hours = 0, minutes = 0] = time.split(':').map(Number);
  return new Date(year, month - 1, day, hours, minutes).toISOString();
}

/** The wall-clock time (`HH:MM`, 24 hours) of an instant in the browser's time zone. */
export function localTimeOf(iso: string): string {
  const instant = new Date(iso);
  return `${twoDigits(instant.getHours())}:${twoDigits(instant.getMinutes())}`;
}

/** An instant, with its date and time, as the person reads it in the browser's time zone. */
export function formatLocalDateTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'full', timeStyle: 'short' }).format(
    new Date(iso),
  );
}

/** The time of an instant (`02:15 p. m.`) in the browser's time zone and the active language. */
export function formatLocalTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { timeStyle: 'short' }).format(new Date(iso));
}

/** The day of an instant, short (`jue, 17 de sept`), in the browser's time zone. */
export function formatShortLocalDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(new Date(iso));
}

/**
 * A calendar date (`YYYY-MM-DD`) as the person reads it. It is built at local midnight and
 * formatted in the same time zone, so it never shifts to the day before or after.
 */
export function formatCalendarDate(date: string, locale: string): string {
  const [year = 0, month = 1, day = 1] = date.split('-').map(Number);
  return new Intl.DateTimeFormat(locale, { dateStyle: 'long' }).format(
    new Date(year, month - 1, day),
  );
}

function twoDigits(value: number): string {
  return String(value).padStart(2, '0');
}
