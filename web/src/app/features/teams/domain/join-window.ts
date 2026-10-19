import { type NextCeremony } from './team-dashboard';

/**
 * Whether a participant may join the room of the ceremony at a given instant: not yet, open
 * before it starts, open although it already started (whoever arrives late), or not at all.
 */
export type JoinState = 'none' | 'not_yet' | 'open' | 'started';

/**
 * The window to join goes from `joinOpensAt` up to, and not including, `joinClosesAt`, a while
 * after `startsAt` (AGI-60). Once it closes the dashboard moves on to the next ceremony, which
 * is the API's to say.
 */
export function joinState(ceremony: NextCeremony | null, now: Date): JoinState {
  if (ceremony === null) {
    return 'none';
  }
  const instant = now.getTime();
  if (instant < new Date(ceremony.joinOpensAt).getTime()) {
    return 'not_yet';
  }
  if (instant < new Date(ceremony.startsAt).getTime()) {
    return 'open';
  }
  return instant < new Date(ceremony.joinClosesAt).getTime() ? 'started' : 'none';
}

/** Whether the room may be joined in this state. */
export function canJoin(state: JoinState): boolean {
  return state === 'open' || state === 'started';
}

/**
 * The next instant at which the state of the window changes (it opens, the ceremony starts,
 * the window closes), or null when it will not change again.
 */
export function nextJoinChange(ceremony: NextCeremony | null, now: Date): Date | null {
  if (ceremony === null) {
    return null;
  }
  const instant = now.getTime();
  const changes = [ceremony.joinOpensAt, ceremony.startsAt, ceremony.joinClosesAt]
    .map((iso) => new Date(iso))
    .filter((change) => change.getTime() > instant);
  return changes[0] ?? null;
}
