import {
  formatCalendarDate,
  formatLocalDateTime,
  formatLocalTime,
  formatShortLocalDate,
  localDateTimeToIso,
  localTimeOf,
} from './local-date-time';

/*
 * These functions use the browser's time zone, whatever it is where the tests run. So the
 * expected values are computed with the same Date and Intl APIs in that zone, and the checks that
 * do not depend on the zone (the calendar date never shifts, the round trip) hold in any of them.
 */
describe('local date and time', () => {
  describe('localDateTimeToIso', () => {
    it('turns a wall-clock time on a date into the same instant in UTC', () => {
      expect(localDateTimeToIso('2026-10-05', '09:30')).toBe(
        new Date(2026, 9, 5, 9, 30).toISOString(),
      );
    });

    it('answers ISO 8601 in UTC, with Z', () => {
      expect(localDateTimeToIso('2026-10-05', '09:30')).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00\.000Z$/,
      );
    });

    it('keeps the wall-clock time on the date in the browser, at midnight too', () => {
      const instant = new Date(localDateTimeToIso('2027-01-01', '00:00'));

      expect([instant.getFullYear(), instant.getMonth(), instant.getDate()]).toEqual([2027, 0, 1]);
      expect([instant.getHours(), instant.getMinutes()]).toEqual([0, 0]);
    });
  });

  describe('localTimeOf', () => {
    it('reads the wall-clock time of an instant in the browser, in 24 hours', () => {
      const instant = new Date(2026, 9, 5, 17, 5);

      expect(localTimeOf(instant.toISOString())).toBe('17:05');
    });

    it('pads the hours and the minutes with zeros', () => {
      expect(localTimeOf(new Date(2026, 9, 5, 8, 0).toISOString())).toBe('08:00');
    });

    it('gives back the time localDateTimeToIso was given', () => {
      expect(localTimeOf(localDateTimeToIso('2026-10-05', '07:45'))).toBe('07:45');
    });
  });

  describe('formatLocalDateTime', () => {
    it('shows an instant with its date and time as Intl does in the browser and the language', () => {
      const iso = '2026-10-06T14:00:00Z';

      expect(formatLocalDateTime(iso, 'es')).toBe(
        new Intl.DateTimeFormat('es', { dateStyle: 'full', timeStyle: 'short' }).format(
          new Date(iso),
        ),
      );
      expect(formatLocalDateTime(iso, 'en')).toBe(
        new Intl.DateTimeFormat('en', { dateStyle: 'full', timeStyle: 'short' }).format(
          new Date(iso),
        ),
      );
    });

    it('shows the time in the browser, not in UTC', () => {
      const instant = new Date(2026, 9, 6, 9, 15);

      expect(formatLocalDateTime(instant.toISOString(), 'es')).toContain('9:15');
    });
  });

  describe('formatCalendarDate', () => {
    it('shows a calendar date in the active language', () => {
      expect(formatCalendarDate('2026-10-05', 'es')).toBe('5 de octubre de 2026');
      expect(formatCalendarDate('2026-10-05', 'en')).toBe('October 5, 2026');
    });

    it('never shifts the date to the day before or after, at the edges of a year either', () => {
      expect(formatCalendarDate('2027-01-01', 'en')).toBe('January 1, 2027');
      expect(formatCalendarDate('2026-12-31', 'en')).toBe('December 31, 2026');
    });
  });

  describe('formatLocalTime', () => {
    it('shows the time of an instant in the browser, in the active language', () => {
      const instant = new Date(2026, 8, 17, 14, 15);

      expect(formatLocalTime(instant.toISOString(), 'es')).toBe(
        new Intl.DateTimeFormat('es', { timeStyle: 'short' }).format(instant),
      );
      expect(formatLocalTime(instant.toISOString(), 'en')).toBe(
        new Intl.DateTimeFormat('en', { timeStyle: 'short' }).format(instant),
      );
    });
  });

  describe('formatShortLocalDate', () => {
    it('shows the weekday, day and month of an instant in the browser', () => {
      const instant = new Date(2026, 8, 17, 9, 15);

      expect(formatShortLocalDate(instant.toISOString(), 'es')).toBe(
        new Intl.DateTimeFormat('es', {
          weekday: 'short',
          day: 'numeric',
          month: 'short',
        }).format(instant),
      );
      expect(formatShortLocalDate(instant.toISOString(), 'es')).toContain('17');
    });
  });
});
