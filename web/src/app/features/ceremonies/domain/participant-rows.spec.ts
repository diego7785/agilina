import { aDailyParticipant, aPresence } from '@testing/room';

import { participantRows } from './participant-rows';

describe('participantRows', () => {
  const eva = aDailyParticipant('user-eva', 'Eva Prueba');
  const ana = aDailyParticipant('user-ana', 'Ana Gil');
  const luis = aDailyParticipant('user-luis', 'Luis Mora');

  it('lists every invited person in turn order, connected or not', () => {
    const rows = participantRows([luis, eva, ana], [aPresence('user-eva', { local: true })]);

    expect(rows).toEqual([
      {
        identity: 'user-luis',
        name: 'Luis Mora',
        email: 'luis@example.test',
        connected: false,
        self: false,
      },
      {
        identity: 'user-eva',
        name: 'Eva Prueba',
        email: 'eva@example.test',
        connected: true,
        self: true,
      },
      {
        identity: 'user-ana',
        name: 'Ana Gil',
        email: 'ana@example.test',
        connected: false,
        self: false,
      },
    ]);
  });

  it('marks as connected whoever the room says is in it, whatever the order of arrival', () => {
    const rows = participantRows(
      [eva, ana, luis],
      [aPresence('user-luis'), aPresence('user-eva', { local: true })],
    );

    expect(rows.map((row) => [row.identity, row.connected, row.self])).toEqual([
      ['user-eva', true, true],
      ['user-ana', false, false],
      ['user-luis', true, false],
    ]);
  });

  it('never makes a row of Agilina, who is in the room as an agent', () => {
    const rows = participantRows(
      [eva],
      [aPresence('user-eva', { local: true }), aPresence('agilina', { agent: true })],
    );

    expect(rows.map((row) => row.identity)).toEqual(['user-eva']);
    expect(participantRows([], [aPresence('agilina', { agent: true })])).toEqual([]);
  });

  it('adds whoever is in the room without being invited, after the invited and with no name', () => {
    const rows = participantRows(
      [eva],
      [aPresence('user-eva', { local: true }), aPresence('guest-1'), aPresence('guest-2')],
    );

    expect(rows.slice(1)).toEqual([
      { identity: 'guest-1', name: '', email: null, connected: true, self: false },
      { identity: 'guest-2', name: '', email: null, connected: true, self: false },
    ]);
  });

  it('lists only who is in the room while the invited are unknown', () => {
    const rows = participantRows(
      [],
      [aPresence('user-eva', { local: true }), aPresence('user-ana')],
    );

    expect(rows).toEqual([
      { identity: 'user-eva', name: '', email: null, connected: true, self: true },
      { identity: 'user-ana', name: '', email: null, connected: true, self: false },
    ]);
  });

  it('shows every invited person disconnected when nobody is in the room', () => {
    const rows = participantRows([eva, ana], []);

    expect(rows.every((row) => !row.connected && !row.self)).toBeTrue();
    expect(rows.length).toBe(2);
  });
});
