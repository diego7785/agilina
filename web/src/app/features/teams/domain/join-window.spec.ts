import { joinState, nextJoinChange } from './join-window';
import { type NextCeremony } from './team-dashboard';

/** The daily at 14:00 UTC; the room opens ten minutes before. */
const DAILY: NextCeremony = {
  type: 'daily',
  startsAt: '2026-10-12T14:00:00Z',
  joinOpensAt: '2026-10-12T13:50:00Z',
};

function at(time: string): Date {
  return new Date(`2026-10-12T${time}Z`);
}

describe('join window', () => {
  describe('joinState', () => {
    it('is none when there is no ceremony', () => {
      expect(joinState(null, at('13:55:00'))).toBe('none');
    });

    it('is not yet before the room opens', () => {
      expect(joinState(DAILY, at('13:49:59'))).toBe('not_yet');
    });

    it('is open from the very instant the room opens', () => {
      expect(joinState(DAILY, at('13:50:00'))).toBe('open');
    });

    it('stays open until the ceremony starts', () => {
      expect(joinState(DAILY, at('13:59:59'))).toBe('open');
    });

    it('is none once the ceremony has started: the next one is for the API to say', () => {
      expect(joinState(DAILY, at('14:00:00'))).toBe('none');
      expect(joinState(DAILY, at('14:05:00'))).toBe('none');
    });
  });

  describe('nextJoinChange', () => {
    it('is the opening of the room while it is closed', () => {
      expect(nextJoinChange(DAILY, at('13:00:00'))).toEqual(at('13:50:00'));
    });

    it('is the start of the ceremony once the room is open', () => {
      expect(nextJoinChange(DAILY, at('13:50:00'))).toEqual(at('14:00:00'));
    });

    it('is nothing once the ceremony has started', () => {
      expect(nextJoinChange(DAILY, at('14:00:00'))).toBeNull();
    });

    it('is nothing when there is no ceremony', () => {
      expect(nextJoinChange(null, at('13:00:00'))).toBeNull();
    });
  });
});
