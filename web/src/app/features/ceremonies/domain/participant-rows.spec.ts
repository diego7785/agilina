import { aDailyParticipant, aPresence } from '@testing/room';

import { participantRows } from './participant-rows';

describe('participantRows', () => {
  const eva = aDailyParticipant('user-eva', 'Eva Prueba');
  const ana = aDailyParticipant('user-ana', 'Ana Gil');
  const luis = aDailyParticipant('user-luis', 'Luis Mora');

  it('lists every invited person in turn order, connected or not', () => {
    const rows = participantRows([luis, eva, ana], [aPresence('user-eva', { local: true })], []);

    expect(rows).toEqual([
      {
        identity: 'user-luis',
        name: 'Luis Mora',
        email: 'luis@example.test',
        connected: false,
        muted: false,
        speaking: false,
        self: false,
      },
      {
        identity: 'user-eva',
        name: 'Eva Prueba',
        email: 'eva@example.test',
        connected: true,
        muted: false,
        speaking: false,
        self: true,
      },
      {
        identity: 'user-ana',
        name: 'Ana Gil',
        email: 'ana@example.test',
        connected: false,
        muted: false,
        speaking: false,
        self: false,
      },
    ]);
  });

  it('marks as connected whoever the room says is in it, whatever the order of arrival', () => {
    const rows = participantRows(
      [eva, ana, luis],
      [aPresence('user-luis'), aPresence('user-eva', { local: true })],
      [],
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
      [],
    );

    expect(rows.map((row) => row.identity)).toEqual(['user-eva']);
    expect(participantRows([], [aPresence('agilina', { agent: true })], [])).toEqual([]);
  });

  it('adds whoever is in the room without being invited, after the invited and with no name', () => {
    const rows = participantRows(
      [eva],
      [aPresence('user-eva', { local: true }), aPresence('guest-1'), aPresence('guest-2')],
      [],
    );

    expect(rows.slice(1)).toEqual([
      {
        identity: 'guest-1',
        name: '',
        email: null,
        connected: true,
        muted: false,
        speaking: false,
        self: false,
      },
      {
        identity: 'guest-2',
        name: '',
        email: null,
        connected: true,
        muted: false,
        speaking: false,
        self: false,
      },
    ]);
  });

  it('lists only who is in the room while the invited are unknown', () => {
    const rows = participantRows(
      [],
      [aPresence('user-eva', { local: true }), aPresence('user-ana')],
      [],
    );

    expect(rows).toEqual([
      {
        identity: 'user-eva',
        name: '',
        email: null,
        connected: true,
        muted: false,
        speaking: false,
        self: true,
      },
      {
        identity: 'user-ana',
        name: '',
        email: null,
        connected: true,
        muted: false,
        speaking: false,
        self: false,
      },
    ]);
  });

  it('marks as muted whoever is in the room with the microphone off, and nobody who is out', () => {
    const rows = participantRows(
      [eva, ana, luis],
      [aPresence('user-eva', { local: true, muted: true }), aPresence('user-ana')],
      [],
    );

    expect(rows.map((row) => [row.identity, row.connected, row.muted])).toEqual([
      ['user-eva', true, true],
      ['user-ana', true, false],
      ['user-luis', false, false],
    ]);
  });

  it('marks as speaking only the rows whose identity is speaking, invited or not', () => {
    const rows = participantRows(
      [eva, ana],
      [aPresence('user-eva', { local: true }), aPresence('user-ana'), aPresence('guest-1')],
      ['user-ana', 'guest-1'],
    );

    expect(rows.map((row) => [row.identity, row.speaking])).toEqual([
      ['user-eva', false],
      ['user-ana', true],
      ['guest-1', true],
    ]);
  });

  it('never shows as speaking someone invited who is not in the room, nor Agilina as a row', () => {
    const rows = participantRows(
      [eva, ana],
      [aPresence('user-eva', { local: true }), aPresence('agilina', { agent: true })],
      ['user-ana', 'agilina'],
    );

    expect(rows.map((row) => [row.identity, row.connected, row.speaking])).toEqual([
      ['user-eva', true, false],
      ['user-ana', false, false],
    ]);
  });

  it('shows every invited person disconnected when nobody is in the room', () => {
    const rows = participantRows([eva, ana], [], []);

    expect(rows.every((row) => !row.connected && !row.self)).toBeTrue();
    expect(rows.length).toBe(2);
  });
});
