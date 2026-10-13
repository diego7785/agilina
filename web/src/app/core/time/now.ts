import { InjectionToken } from '@angular/core';

/**
 * The current instant. A token, so that a test can fix the clock instead of depending on the
 * machine that runs it (the dashboard decides from it whether the room is open).
 */
export const NOW = new InjectionToken<() => Date>('NOW', {
  providedIn: 'root',
  factory: () => () => new Date(),
});
