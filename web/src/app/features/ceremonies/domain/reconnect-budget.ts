/** How long the room keeps trying to get back after the connection drops (AGI-60). */
export const RECONNECT_BUDGET_MS = 30_000;

/**
 * The waits between attempts, in milliseconds: quick at first, then every seven seconds. They
 * are the ones LiveKit uses by default; the budget is what cuts them.
 */
export const RETRY_DELAYS_MS: readonly number[] = [0, 300, 1_200, 2_700, 4_800, 7_000];

/**
 * How long to wait before the next attempt to reconnect, or `null` to give up: once the next
 * attempt would start after the budget, the participant is told and may try again by hand.
 *
 * @param retryCount attempts that already failed (0 before the first one).
 * @param elapsedMs time since the connection dropped.
 */
export function nextRetryDelay(retryCount: number, elapsedMs: number): number | null {
  const delays = RETRY_DELAYS_MS;
  const delay = delays[Math.min(retryCount, delays.length - 1)] ?? 0;
  return elapsedMs + delay < RECONNECT_BUDGET_MS ? delay : null;
}
