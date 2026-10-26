import { ApplicationRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of, Subject } from 'rxjs';

import {
  aDailyParticipant,
  aPresence,
  FakeDailyParticipantsPort,
  FakeRoomAccessPort,
  FakeRoomPort,
} from '@testing/room';

import { DailyParticipantsPort } from './daily-participants.port';
import { RoomAccessPort } from './room-access.port';
import { RoomFacade } from './room.facade';
import { RoomPort } from './room.port';
import { AGILINA_ARRIVAL_BUDGET_MS } from '../domain/agilina-status';
import { type DailyParticipant } from '../domain/daily-participant';
import { RoomFailure } from '../domain/room-failure';

describe('RoomFacade', () => {
  let access: FakeRoomAccessPort;
  let room: FakeRoomPort;
  let invited: FakeDailyParticipantsPort;
  let facade: RoomFacade;

  beforeEach(() => {
    access = new FakeRoomAccessPort();
    room = new FakeRoomPort();
    invited = new FakeDailyParticipantsPort();
    TestBed.configureTestingModule({
      providers: [
        RoomFacade,
        { provide: DailyParticipantsPort, useValue: invited },
        { provide: RoomAccessPort, useValue: access },
        { provide: RoomPort, useValue: room },
      ],
    });
    facade = TestBed.inject(RoomFacade);
  });

  /** Lets the chain of promises of joining run to its end. */
  async function settle(): Promise<void> {
    for (let round = 0; round < 10; round++) {
      await Promise.resolve();
    }
    await TestBed.inject(ApplicationRef).whenStable();
  }

  describe('joining (criteria 1 and 2)', () => {
    it('is connecting until the room answers', () => {
      expect(facade.status()).toBe('connecting');
      expect(facade.microphone()).toBe('pending');
      expect(facade.failure()).toBeNull();
    });

    it('asks for the microphone first, then enters with a new access and publishes it', async () => {
      facade.join('atlas');
      await settle();

      expect(room.calls).toEqual(['requestMicrophone', 'connect', 'enableMicrophone']);
      expect(access.requested).toEqual(['atlas']);
      expect(room.connected.map((a) => a.token)).toEqual(['token-1']);
      expect(room.microphoneRequests).toBe(1);
      expect(facade.status()).toBe('connected');
      expect(facade.microphone()).toBe('on');
    });

    it('waits for the person to answer the browser before asking for the access', async () => {
      room.requestMicrophone = () => new Promise(() => undefined);

      facade.join('atlas');
      await settle();

      expect(access.requested).toEqual([]);
      expect(facade.status()).toBe('connecting');
    });

    it('does not enter when the API refuses the access, and says why', async () => {
      access.failure = new RoomFailure('no_access');

      facade.join('atlas');
      await settle();

      expect(room.connected).toEqual([]);
      expect(facade.status()).toBe('failed');
      expect(facade.failure()).toBe('no_access');
    });

    it('reads an unknown error as unexpected', async () => {
      access.failure = new Error('boom');

      facade.join('atlas');
      await settle();

      expect(facade.failure()).toBe('unexpected');
    });

    it('asks for a new access once when LiveKit refuses the token', async () => {
      room.connectFailures.push(new RoomFailure('token_rejected'));

      facade.join('atlas');
      await settle();

      expect(access.requested).toEqual(['atlas', 'atlas']);
      expect(room.connected.map((a) => a.token)).toEqual(['token-1', 'token-2']);
      expect(facade.status()).toBe('connected');
    });

    it('gives up when LiveKit refuses the new token too', async () => {
      room.connectFailures.push(
        new RoomFailure('token_rejected'),
        new RoomFailure('token_rejected'),
      );

      facade.join('atlas');
      await settle();

      expect(access.requested.length).toBe(2);
      expect(facade.status()).toBe('failed');
      expect(facade.failure()).toBe('token_rejected');
    });

    it('does not ask for a new token when the room service is down', async () => {
      room.connectFailures.push(new RoomFailure('service_unavailable'));

      facade.join('atlas');
      await settle();

      expect(access.requested.length).toBe(1);
      expect(facade.failure()).toBe('service_unavailable');
    });

    it('does nothing when retried before knowing the team', async () => {
      facade.retry();
      await settle();

      expect(access.requested).toEqual([]);
    });
  });

  describe('the microphone (criterion 4)', () => {
    for (const answer of ['denied', 'not_found', 'unavailable', 'insecure_context'] as const) {
      it(`keeps the participant in the room as a listener when it is ${answer}`, async () => {
        room.microphoneAnswer = answer;

        facade.join('atlas');
        await settle();

        expect(facade.status()).toBe('connected');
        expect(facade.microphone()).toBe(answer);
        expect(facade.failure()).toBeNull();
        expect(room.microphoneRequests).toBe(0);
      });
    }

    it('asks for it again on demand, and turns it on once allowed', async () => {
      room.microphoneAnswer = 'denied';
      facade.join('atlas');
      await settle();

      room.microphoneAnswer = 'on';
      const retried = facade.retryMicrophone();
      expect(facade.microphone()).toBe('pending');
      await retried;

      expect(room.microphoneRequests).toBe(1);
      expect(facade.microphone()).toBe('on');
    });

    it('silences the microphone and turns it on again (AGI-61)', async () => {
      facade.join('atlas');
      await settle();
      expect(facade.muted()).toBeFalse();

      await facade.toggleMute();
      expect(facade.muted()).toBeTrue();
      expect(facade.microphone()).toBe('on');

      await facade.toggleMute();
      expect(facade.muted()).toBeFalse();
      expect(room.calls.filter((call) => call.endsWith('mute'))).toEqual(['mute', 'unmute']);
    });

    it('leaves the participant as a listener when the microphone cannot be turned on again', async () => {
      facade.join('atlas');
      await settle();
      await facade.toggleMute();

      room.muteFailure = new Error('the device is gone');
      await facade.toggleMute();

      expect(facade.muted()).toBeFalse();
      expect(facade.microphone()).toBe('unavailable');
    });

    it('enters again with the microphone on, not silenced', async () => {
      facade.join('atlas');
      await settle();
      await facade.toggleMute();

      facade.retry();
      await settle();

      expect(facade.muted()).toBeFalse();
    });
  });

  describe('the connection (criterion 5)', () => {
    beforeEach(async () => {
      facade.join('atlas');
      await settle();
    });

    it('says it is reconnecting when the network drops, and connected when it is back', () => {
      room.emit({ kind: 'reconnecting' });
      expect(facade.status()).toBe('reconnecting');

      room.emit({ kind: 'reconnected' });
      expect(facade.status()).toBe('connected');
    });

    it('fails with the connection lost when it could not get back', () => {
      room.emit({ kind: 'reconnecting' });
      room.emit({ kind: 'lost' });

      expect(facade.status()).toBe('failed');
      expect(facade.failure()).toBe('connection_lost');
    });

    it('does not move a failed room back', () => {
      room.emit({ kind: 'lost' });
      room.emit({ kind: 'reconnected' });
      room.emit({ kind: 'reconnecting' });
      room.emit({ kind: 'lost' });

      expect(facade.status()).toBe('failed');
    });

    describe('when it hangs while reconnecting', () => {
      beforeEach(() => {
        jasmine.clock().install();
      });

      afterEach(() => {
        jasmine.clock().uninstall();
      });

      it('gives up after thirty seconds and leaves the room', () => {
        const before = room.disconnects;
        room.emit({ kind: 'reconnecting' });

        jasmine.clock().tick(29_999);
        expect(facade.status()).toBe('reconnecting');

        jasmine.clock().tick(1);
        expect(facade.status()).toBe('failed');
        expect(facade.failure()).toBe('connection_lost');
        expect(room.disconnects).toBe(before + 1);
      });

      it('does not give up when it got back in time', () => {
        room.emit({ kind: 'reconnecting' });
        jasmine.clock().tick(10_000);
        room.emit({ kind: 'reconnected' });

        jasmine.clock().tick(60_000);

        expect(facade.status()).toBe('connected');
      });

      it('does not give up twice when LiveKit already did', () => {
        const before = room.disconnects;
        room.emit({ kind: 'reconnecting' });
        room.emit({ kind: 'lost' });

        jasmine.clock().tick(60_000);

        expect(room.disconnects).toBe(before);
      });

      it('stops counting when the page goes away', () => {
        room.emit({ kind: 'reconnecting' });
        TestBed.resetTestingModule();
        const after = room.disconnects;

        jasmine.clock().tick(60_000);

        expect(room.disconnects).toBe(after);
      });
    });

    it('enters again with a new access when retried', async () => {
      room.emit({ kind: 'lost' });

      facade.retry();
      expect(facade.status()).toBe('connecting');
      expect(facade.failure()).toBeNull();
      await settle();

      expect(access.requested).toEqual(['atlas', 'atlas']);
      expect(room.connected.map((a) => a.token)).toEqual(['token-1', 'token-2']);
      expect(facade.status()).toBe('connected');
      expect(facade.microphone()).toBe('on');
    });
  });

  describe('the participants (AGI-61)', () => {
    const eva = aDailyParticipant('user-eva', 'Eva Prueba');
    const ana = aDailyParticipant('user-ana', 'Ana Gil');

    /** Identity, connected and self of each row, in order. */
    function rows(): [string, boolean, boolean][] {
      return facade.participants().map((row) => [row.identity, row.connected, row.self]);
    }

    beforeEach(() => {
      invited.participants = [eva, ana];
    });

    it('lists nobody before entering', () => {
      expect(facade.participants()).toEqual([]);
    });

    it('asks for the invited of the team once in, and lists them all', async () => {
      facade.join('atlas');
      await settle();

      expect(invited.requested).toEqual(['atlas']);
      expect(rows()).toEqual([
        ['user-eva', false, false],
        ['user-ana', false, false],
      ]);
      expect(facade.participants()[0]!.name).toBe('Eva Prueba');
    });

    it('follows who arrives and who leaves', async () => {
      facade.join('atlas');
      await settle();

      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });
      expect(rows()).toEqual([
        ['user-eva', true, true],
        ['user-ana', false, false],
      ]);

      room.emit({
        kind: 'presence',
        present: [
          aPresence('user-eva', { local: true }),
          aPresence('user-ana'),
          aPresence('agilina', { agent: true }),
        ],
      });
      expect(rows()).toEqual([
        ['user-eva', true, true],
        ['user-ana', true, false],
      ]);

      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });
      expect(rows()).toEqual([
        ['user-eva', true, true],
        ['user-ana', false, false],
      ]);
    });

    it('does not ask for the invited when it could not enter', async () => {
      access.failure = new RoomFailure('no_access');

      facade.join('atlas');
      await settle();

      expect(invited.requested).toEqual([]);
    });

    it('lists only who is in the room when the invited cannot be read', async () => {
      invited.failure = new Error('403');
      facade.join('atlas');
      await settle();

      room.emit({
        kind: 'presence',
        present: [aPresence('user-eva', { local: true }), aPresence('agilina', { agent: true })],
      });

      expect(facade.status()).toBe('connected');
      expect(facade.participants()).toEqual([
        {
          identity: 'user-eva',
          name: '',
          email: null,
          connected: true,
          muted: false,
          speaking: false,
          self: true,
        },
      ]);
    });

    it('shows everyone disconnected once the connection is lost', async () => {
      facade.join('atlas');
      await settle();
      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });

      room.emit({ kind: 'lost' });

      expect(rows()).toEqual([
        ['user-eva', false, false],
        ['user-ana', false, false],
      ]);
    });

    it('shows everyone disconnected when it gives up reconnecting', async () => {
      facade.join('atlas');
      await settle();
      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });
      jasmine.clock().install();
      try {
        room.emit({ kind: 'reconnecting' });
        jasmine.clock().tick(30_000);
      } finally {
        jasmine.clock().uninstall();
      }

      expect(facade.status()).toBe('failed');
      expect(rows().every(([, connected]) => !connected)).toBeTrue();
    });

    it('forgets who was in the room and asks for the invited again when retried', async () => {
      facade.join('atlas');
      await settle();
      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });
      room.emit({ kind: 'lost' });
      invited.participants = [ana];

      facade.retry();
      expect(rows().every(([, connected]) => !connected)).toBeTrue();
      await settle();

      expect(invited.requested).toEqual(['atlas', 'atlas']);
      expect(rows()).toEqual([['user-ana', false, false]]);
    });

    it('ignores the invited of an attempt that is no longer the current one', async () => {
      const late = new Subject<readonly DailyParticipant[]>();
      const answers = [late, of([ana])];
      invited.participantsOf = () => answers.shift()!;
      facade.join('atlas');
      await settle();
      room.emit({ kind: 'lost' });

      facade.retry();
      await settle();
      late.next([eva]);
      late.complete();
      await settle();

      expect(rows()).toEqual([['user-ana', false, false]]);
    });
  });

  describe('who is speaking and Agilina (AGI-61)', () => {
    const eva = aDailyParticipant('user-eva', 'Eva Prueba');
    const ana = aDailyParticipant('user-ana', 'Ana Gil');
    const everyone = [
      aPresence('user-eva', { local: true }),
      aPresence('user-ana'),
      aPresence('agilina', { agent: true }),
    ];

    /** The identities of the rows that are speaking. */
    function speakers(): string[] {
      return facade
        .participants()
        .filter((row) => row.speaking)
        .map((row) => row.identity);
    }

    beforeEach(async () => {
      invited.participants = [eva, ana];
      facade.join('atlas');
      await settle();
    });

    it('says Agilina is not in the room until an agent is', () => {
      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });

      expect(facade.agilinaPresent()).toBeFalse();
      expect(facade.agilinaSpeaking()).toBeFalse();

      room.emit({ kind: 'presence', present: everyone });

      expect(facade.agilinaPresent()).toBeTrue();
      expect(facade.agilinaSpeaking()).toBeFalse();
    });

    it('follows who is speaking, the participant and Agilina included', () => {
      room.emit({ kind: 'presence', present: everyone });

      room.emit({ kind: 'speaking', identities: ['user-ana'] });
      expect(speakers()).toEqual(['user-ana']);
      expect(facade.agilinaSpeaking()).toBeFalse();

      room.emit({ kind: 'speaking', identities: ['user-eva', 'agilina'] });
      expect(speakers()).toEqual(['user-eva']);
      expect(facade.agilinaSpeaking()).toBeTrue();

      room.emit({ kind: 'speaking', identities: [] });
      expect(speakers()).toEqual([]);
      expect(facade.agilinaSpeaking()).toBeFalse();
    });

    it('does not say Agilina speaks once she left the room', () => {
      room.emit({ kind: 'presence', present: everyone });
      room.emit({ kind: 'speaking', identities: ['agilina'] });

      room.emit({ kind: 'presence', present: everyone.slice(0, 2) });

      expect(facade.agilinaPresent()).toBeFalse();
      expect(facade.agilinaSpeaking()).toBeFalse();
    });

    it('forgets who was speaking once the connection is lost', () => {
      room.emit({ kind: 'presence', present: everyone });
      room.emit({ kind: 'speaking', identities: ['user-ana', 'agilina'] });

      room.emit({ kind: 'lost' });
      // Whoever is in the room again, nobody speaks until the room says so.
      room.emit({ kind: 'presence', present: everyone });

      expect(speakers()).toEqual([]);
      expect(facade.agilinaSpeaking()).toBeFalse();
    });

    it('forgets who was speaking while it reconnects', () => {
      room.emit({ kind: 'presence', present: everyone });
      room.emit({ kind: 'speaking', identities: ['user-ana', 'agilina'] });

      room.emit({ kind: 'reconnecting' });

      expect(speakers()).toEqual([]);
      expect(facade.agilinaSpeaking()).toBeFalse();
    });

    it('forgets who was speaking when it enters again', async () => {
      room.emit({ kind: 'presence', present: everyone });
      room.emit({ kind: 'speaking', identities: ['user-ana', 'agilina'] });

      facade.retry();
      await settle();
      room.emit({ kind: 'presence', present: everyone });

      expect(facade.status()).toBe('connected');
      expect(speakers()).toEqual([]);
      expect(facade.agilinaPresent()).toBeTrue();
      expect(facade.agilinaSpeaking()).toBeFalse();
    });
  });

  describe('the status of Agilina (AGI-62)', () => {
    const eva = aPresence('user-eva', { local: true });

    beforeEach(async () => {
      jasmine.clock().install();
      facade.join('atlas');
      await settle();
    });

    afterEach(() => {
      jasmine.clock().uninstall();
    });

    it('is arriving, then unavailable once the budget runs out without her', () => {
      room.emit({ kind: 'presence', present: [eva] });
      expect(facade.agilinaStatus()).toBe('arriving');

      jasmine.clock().tick(AGILINA_ARRIVAL_BUDGET_MS - 1);
      expect(facade.agilinaStatus()).toBe('arriving');

      jasmine.clock().tick(1);
      expect(facade.agilinaStatus()).toBe('unavailable');
    });

    it('is the state she published, before the budget or after it', () => {
      room.emit({
        kind: 'presence',
        present: [eva, aPresence('agilina', { agent: true, agentState: 'standby' })],
      });
      jasmine.clock().tick(AGILINA_ARRIVAL_BUDGET_MS);
      expect(facade.agilinaStatus()).toBe('standby');

      room.emit({ kind: 'presence', present: [eva] });
      expect(facade.agilinaStatus()).toBe('unavailable');

      room.emit({
        kind: 'presence',
        present: [eva, aPresence('agilina', { agent: true, agentState: 'no_facilitation' })],
      });
      expect(facade.agilinaStatus()).toBe('no_facilitation');
    });

    it('gives her the whole budget again when it enters again', async () => {
      jasmine.clock().tick(AGILINA_ARRIVAL_BUDGET_MS);
      expect(facade.agilinaStatus()).toBe('unavailable');

      facade.retry();
      await settle();

      expect(facade.agilinaStatus()).toBe('arriving');
      jasmine.clock().tick(AGILINA_ARRIVAL_BUDGET_MS - 1);
      expect(facade.agilinaStatus()).toBe('arriving');
    });

    it('stops counting when the connection is lost', () => {
      room.emit({ kind: 'lost' });

      jasmine.clock().tick(AGILINA_ARRIVAL_BUDGET_MS);

      expect(facade.agilinaStatus()).toBe('arriving');
    });

    it('stops counting when the page goes away', () => {
      TestBed.resetTestingModule();

      jasmine.clock().tick(AGILINA_ARRIVAL_BUDGET_MS);

      expect(facade.agilinaStatus()).toBe('arriving');
    });
  });

  describe('the audio of the others', () => {
    it('tells when the browser blocks it, and plays it again on demand', async () => {
      facade.join('atlas');
      await settle();

      room.emit({ kind: 'audio_blocked', blocked: true });
      expect(facade.audioBlocked()).toBeTrue();

      await facade.resumeAudio();

      expect(room.audioResumed).toBe(1);
      expect(facade.audioBlocked()).toBeFalse();
    });
  });

  describe('leaving', () => {
    it('leaves the room when the page goes away', async () => {
      facade.join('atlas');
      await settle();
      const before = room.disconnects;

      TestBed.resetTestingModule();

      expect(room.disconnects).toBe(before + 1);
    });

    it('ignores an answer that arrives after the page went away', async () => {
      facade.join('atlas');
      TestBed.resetTestingModule();
      await settle();

      expect(facade.status()).toBe('connecting');
      expect(room.connected).toEqual([]);
      expect(room.microphoneRequests).toBe(0);
    });
  });
});
