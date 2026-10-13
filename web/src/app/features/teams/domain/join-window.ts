import { type NextCeremony } from './team-dashboard';

/** Whether a participant may join the room of the next ceremony at a given instant. */
export type JoinState = 'none' | 'not_yet' | 'open';

/**
 * The window to join goes from `joinOpensAt` up to, and not including, `startsAt`. Once the
 * ceremony has started the dashboard moves on to the next one: the ceremony in progress is not
 * modelled yet.
 */
export function joinState(ceremony: NextCeremony | null, now: Date): JoinState {
  if (ceremony === null) {
    return 'none';
  }
  const instant = now.getTime();
  if (instant < new Date(ceremony.joinOpensAt).getTime()) {
    return 'not_yet';
  }
  return instant < new Date(ceremony.startsAt).getTime() ? 'open' : 'none';
}

/**
 * The next instant at which the state of the window changes (it opens, then the ceremony
 * starts), or null when it will not change again.
 */
export function nextJoinChange(ceremony: NextCeremony | null, now: Date): Date | null {
  if (ceremony === null) {
    return null;
  }
  const instant = now.getTime();
  const changes = [ceremony.joinOpensAt, ceremony.startsAt]
    .map((iso) => new Date(iso))
    .filter((change) => change.getTime() > instant);
  return changes[0] ?? null;
}
