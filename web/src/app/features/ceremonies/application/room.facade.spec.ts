import { ApplicationRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { FakeRoomAccessPort, FakeRoomPort } from '@testing/room';

import { RoomAccessPort } from './room-access.port';
import { RoomFacade } from './room.facade';
import { RoomPort } from './room.port';
import { RoomFailure } from '../domain/room-failure';

describe('RoomFacade', () => {
  let access: FakeRoomAccessPort;
  let room: FakeRoomPort;
  let facade: RoomFacade;

  beforeEach(() => {
    access = new FakeRoomAccessPort();
    room = new FakeRoomPort();
    TestBed.configureTestingModule({
      providers: [
        RoomFacade,
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
