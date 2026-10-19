/**
 * Why the participant could not enter the room, or lost it, in the terms of the product.
 * The adapters translate the API's answers and LiveKit's errors into these.
 *
 * - `no_access`: the person is not a participant of the daily, or not a member of the team.
 * - `no_active_sprint`: the team has no active sprint, so there is no daily to join.
 * - `daily_not_open`: the daily's window to join is not open now (it opens ten minutes before
 *   the daily and closes fifteen minutes after it starts).
 * - `service_unavailable`: the room service (LiveKit) or the API does not answer.
 * - `token_rejected`: LiveKit refused the token, even after asking for a new one.
 * - `connection_lost`: the connection dropped and could not be recovered in time, or the room
 *   closed it.
 * - `unexpected`: anything else.
 */
export type RoomFailureKind =
  | 'no_access'
  | 'no_active_sprint'
  | 'daily_not_open'
  | 'service_unavailable'
  | 'token_rejected'
  | 'connection_lost'
  | 'unexpected';

export class RoomFailure extends Error {
  override readonly name = 'RoomFailure';

  constructor(readonly kind: RoomFailureKind) {
    super(`Room failure: ${kind}`);
  }
}

/** What went wrong, for any error that reached the room: anything unknown is `unexpected`. */
export function roomFailureKindOf(error: unknown): RoomFailureKind {
  return error instanceof RoomFailure ? error.kind : 'unexpected';
}

const FINAL: ReadonlySet<RoomFailureKind> = new Set([
  'no_access',
  'no_active_sprint',
  'daily_not_open',
]);

/** Whether trying again may help: without access, a sprint or an open daily, it would fail the
 * same way. */
export function isRetriable(kind: RoomFailureKind): boolean {
  return !FINAL.has(kind);
}
