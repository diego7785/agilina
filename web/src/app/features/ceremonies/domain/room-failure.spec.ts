import { isRetriable, RoomFailure, roomFailureKindOf } from './room-failure';

describe('room failure', () => {
  it('keeps its kind', () => {
    expect(roomFailureKindOf(new RoomFailure('no_access'))).toBe('no_access');
  });

  it('reads any other error as unexpected', () => {
    expect(roomFailureKindOf(new Error('boom'))).toBe('unexpected');
    expect(roomFailureKindOf('boom')).toBe('unexpected');
  });

  it('is not worth retrying without access, without a sprint or with the daily not open', () => {
    expect(isRetriable('no_access')).toBeFalse();
    expect(isRetriable('no_active_sprint')).toBeFalse();
    expect(isRetriable('daily_not_open')).toBeFalse();
  });

  it('is worth retrying when the service or the connection failed', () => {
    expect(isRetriable('service_unavailable')).toBeTrue();
    expect(isRetriable('token_rejected')).toBeTrue();
    expect(isRetriable('connection_lost')).toBeTrue();
    expect(isRetriable('unexpected')).toBeTrue();
  });
});
