/**
 * Where today falls relative to the sprint's period, in the calendar of the daily's capture
 * time zone (AD-31). The API computes it: an active sprint may not have started yet or may be
 * over already.
 */
export type SprintPhase = 'not_started' | 'in_progress' | 'finished';

/**
 * Day N of M of the sprint: M (`total`) counts every calendar day of the period, both ends
 * included; N (`number`) is 0 before the start, 1 to M during the sprint and M after the end.
 */
export interface SprintDay {
  readonly number: number;
  readonly total: number;
  readonly phase: SprintPhase;
}

/**
 * The active sprint of a team, as the API answers it. Dates are calendar dates (`YYYY-MM-DD`)
 * and instants are ISO 8601 in UTC; the screens show them in the browser's time zone.
 */
export interface ActiveSprint {
  readonly id: string;
  /** The sprint's number in its team (the 12 of "Sprint 12"), assigned by the API. */
  readonly number: number;
  /** First day of the sprint, `YYYY-MM-DD`. */
  readonly startDate: string;
  /** Last day of the sprint, included, `YYYY-MM-DD`. */
  readonly endDate: string;
  /** The daily's anchor instant, in UTC: its wall-clock time in `timeZone` is the daily's time. */
  readonly dailyTime: string;
  /** The IANA time zone the daily's time was captured in, the one that fixes its calendar. */
  readonly timeZone: string;
  /** The next daily, in UTC, as the API computed it; null once the last one has started. */
  readonly nextDailyAt: string | null;
  /** The `userId` of the daily's participants, in turn order: the first one speaks first. */
  readonly participants: readonly string[];
  readonly day: SprintDay;
}
