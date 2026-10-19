import { nextRetryDelay, RECONNECT_BUDGET_MS, RETRY_DELAYS_MS } from './reconnect-budget';

describe('reconnect budget', () => {
  it('lasts thirty seconds', () => {
    expect(RECONNECT_BUDGET_MS).toBe(30_000);
  });

  it('tries again at once, then waits longer each time', () => {
    expect(nextRetryDelay(0, 0)).toBe(0);
    expect(nextRetryDelay(1, 10)).toBe(300);
    expect(nextRetryDelay(2, 400)).toBe(1_200);
  });

  it('keeps waiting the longest delay once the list runs out', () => {
    const longest = RETRY_DELAYS_MS[RETRY_DELAYS_MS.length - 1];

    expect(nextRetryDelay(9, 15_000)).toBe(longest!);
  });

  it('gives up when the next attempt would start after the budget', () => {
    expect(nextRetryDelay(6, 22_999)).toBe(7_000);
    expect(nextRetryDelay(6, 23_000)).toBeNull();
    expect(nextRetryDelay(0, RECONNECT_BUDGET_MS)).toBeNull();
  });
});
