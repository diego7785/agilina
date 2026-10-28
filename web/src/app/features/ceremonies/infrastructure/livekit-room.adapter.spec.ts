import { TestBed } from '@angular/core/testing';
import { ConnectionError, DisconnectReason, type Room, RoomEvent, Track } from 'livekit-client';

import { Logger } from '@core/logging/logger';
import { FakeLogger } from '@testing/fake-logger';
import { anAccess } from '@testing/room';

import { LIVEKIT_MICROPHONE, LIVEKIT_ROOM_FACTORY, ROOM_OPTIONS } from './livekit-room-factory';
import { LiveKitRoomAdapter } from './livekit-room.adapter';
import { SECURE_CONTEXT } from './secure-context';
import { type RoomChange } from '../application/room.port';
import { RoomFailure } from '../domain/room-failure';

type Listener = (...args: unknown[]) => void;

/** Someone else in a LiveKit room, as the adapter reads them. */
interface FakeParticipant {
  identity: string;
  isAgent: boolean;
  isMicrophoneEnabled: boolean;
  attributes: Record<string, string>;
}

/** A LiveKit room without network: it records what it is asked and emits what the test says. */
class FakeRoom {
  readonly listeners = new Map<string, Listener[]>();
  readonly connections: { url: string; token: string; options: unknown }[] = [];
  connectFailure: Error | null = null;
  microphoneFailure: Error | null = null;
  microphoneEnabled = false;
  readonly published: unknown[] = [];
  canPlaybackAudio = true;
  audioStarts = 0;
  disconnects = 0;
  readonly remoteParticipants = new Map<string, FakeParticipant>();
  readonly localParticipant = {
    identity: 'eva',
    isAgent: false,
    isMicrophoneEnabled: false,
    attributes: {},
    setMicrophoneEnabled: (enabled: boolean): Promise<undefined> => {
      if (this.microphoneFailure !== null) {
        return Promise.reject(this.microphoneFailure);
      }
      this.microphoneEnabled = enabled;
      this.localParticipant.isMicrophoneEnabled = enabled;
      return Promise.resolve(undefined);
    },
    publishTrack: (track: unknown, options: unknown): Promise<undefined> => {
      if (this.microphoneFailure !== null) {
        return Promise.reject(this.microphoneFailure);
      }
      this.published.push({ track, options });
      return Promise.resolve(undefined);
    },
  };

  on(event: string, listener: Listener): this {
    this.listeners.set(event, [...(this.listeners.get(event) ?? []), listener]);
    return this;
  }

  /** Someone enters the room, as the SDK tells it: in the map first, then the event. */
  arrive(identity: string, isAgent = false, attributes: Record<string, string> = {}): void {
    const participant = { identity, isAgent, isMicrophoneEnabled: true, attributes };
    this.remoteParticipants.set(identity, participant);
    this.emit(RoomEvent.ParticipantConnected, participant);
  }

  emit(event: string, ...args: unknown[]): void {
    for (const listener of this.listeners.get(event) ?? []) {
      listener(...args);
    }
  }

  connect(url: string, token: string, options: unknown): Promise<void> {
    this.connections.push({ url, token, options });
    return this.connectFailure === null ? Promise.resolve() : Promise.reject(this.connectFailure);
  }

  startAudio(): Promise<void> {
    this.audioStarts++;
    return Promise.resolve();
  }

  disconnect(): Promise<void> {
    this.disconnects++;
    this.emit(RoomEvent.Disconnected, DisconnectReason.CLIENT_INITIATED);
    return Promise.resolve();
  }
}

/** A remote audio track: `attach` gives an `<audio>` that `detach` hands back. */
function anAudioTrack(): {
  kind: Track.Kind;
  attach: () => HTMLMediaElement;
  detach: () => HTMLMediaElement[];
} {
  const element = document.createElement('audio');
  return { kind: Track.Kind.Audio, attach: () => element, detach: () => [element] };
}

/** The microphone track the browser hands over; it knows whether it was stopped. */
class FakeMicrophone {
  stopped = false;
  readonly mediaStreamTrack = { kind: 'audio' };

  stop(): void {
    this.stopped = true;
  }
}

/** A DOMException as the browser raises it when asked for the microphone. */
function mediaError(name: string): DOMException {
  return new DOMException('media', name);
}

describe('LiveKitRoomAdapter', () => {
  let rooms: FakeRoom[];
  let adapter: LiveKitRoomAdapter;
  let logger: FakeLogger;
  let changes: RoomChange[];
  let microphones: FakeMicrophone[];
  let microphoneFailure: Error | null;
  /** What the next room created fails with when it connects. */
  let nextConnectFailure: Error | null;
  /** Who is already in the next room created when the participant enters it. */
  let nextRemotes: FakeParticipant[];
  const microphoneProvider = {
    provide: LIVEKIT_MICROPHONE,
    useValue: () => {
      if (microphoneFailure !== null) {
        return Promise.reject(microphoneFailure);
      }
      const microphone = new FakeMicrophone();
      microphones.push(microphone);
      return Promise.resolve(microphone);
    },
  };

  function room(): FakeRoom {
    return rooms[rooms.length - 1]!;
  }

  beforeEach(() => {
    rooms = [];
    microphones = [];
    microphoneFailure = null;
    nextConnectFailure = null;
    nextRemotes = [];
    logger = new FakeLogger();
    TestBed.configureTestingModule({
      providers: [
        LiveKitRoomAdapter,
        { provide: Logger, useValue: logger },
        { provide: SECURE_CONTEXT, useValue: true },
        microphoneProvider,
        {
          provide: LIVEKIT_ROOM_FACTORY,
          useValue: () => {
            const created = new FakeRoom();
            created.connectFailure = nextConnectFailure;
            for (const remote of nextRemotes) {
              created.remoteParticipants.set(remote.identity, remote);
            }
            rooms.push(created);
            return created as unknown as Room;
          },
        },
      ],
    });
    adapter = TestBed.inject(LiveKitRoomAdapter);
    changes = [];
    adapter.changes.subscribe((change) => changes.push(change));
  });

  afterEach(async () => {
    await adapter.disconnect();
  });

  describe('connecting', () => {
    it('enters the server of the access with its token, subscribed to everyone', async () => {
      await adapter.connect(anAccess());

      expect(room().connections).toEqual([
        { url: 'wss://agilina.livekit.test', token: 'token-1', options: { autoSubscribe: true } },
      ]);
      expect(logger.entries.map((e) => e.message)).toContain('Room joined');
    });

    it('never logs the token', async () => {
      await adapter.connect(anAccess());

      expect(JSON.stringify(logger.entries)).not.toContain('token-1');
    });

    it('says at once whether the browser lets it play the others', async () => {
      await adapter.connect(anAccess());

      expect(changes[0]).toEqual({ kind: 'audio_blocked', blocked: false });
    });

    it('tells who is in the room once in, the participant first and Agilina as an agent', async () => {
      nextRemotes = [
        { identity: 'ana', isAgent: false, isMicrophoneEnabled: true, attributes: {} },
        {
          identity: 'agilina',
          isAgent: true,
          isMicrophoneEnabled: true,
          attributes: { 'agilina.state': 'standby' },
        },
      ];

      await adapter.connect(anAccess());

      expect(changes).toEqual([
        { kind: 'audio_blocked', blocked: false },
        {
          kind: 'presence',
          present: [
            {
              identity: 'eva',
              agent: false,
              local: true,
              muted: true,
              agentState: null,
              agentText: null,
            },
            {
              identity: 'ana',
              agent: false,
              local: false,
              muted: false,
              agentState: null,
              agentText: null,
            },
            {
              identity: 'agilina',
              agent: true,
              local: false,
              muted: false,
              agentState: 'standby',
              agentText: null,
            },
          ],
        },
      ]);
    });

    it('tells nobody is in the room when it could not enter', async () => {
      nextConnectFailure = ConnectionError.timeout('slow');

      await expectAsync(adapter.connect(anAccess())).toBeRejected();

      expect(changes).toEqual([]);
    });

    const connectionFailures: readonly [string, () => Error, string][] = [
      ['a refused token', () => ConnectionError.notAllowed('invalid token', 401), 'token_rejected'],
      [
        'an unreachable server',
        () => ConnectionError.serverUnreachable('down'),
        'service_unavailable',
      ],
      ['a timeout', () => ConnectionError.timeout('slow'), 'service_unavailable'],
      ['a broken websocket', () => ConnectionError.websocket('ws'), 'service_unavailable'],
      ['an internal error', () => ConnectionError.internal('500'), 'service_unavailable'],
      ['a cancelled connection', () => ConnectionError.cancelled('left'), 'unexpected'],
      ['any other error', () => new Error('boom'), 'unexpected'],
    ];
    for (const [what, failure, kind] of connectionFailures) {
      it(`fails with ${kind} on ${what}, and logs it`, async () => {
        const failing = new FakeRoom();
        failing.connectFailure = failure();
        TestBed.resetTestingModule();
        TestBed.configureTestingModule({
          providers: [
            LiveKitRoomAdapter,
            { provide: Logger, useValue: logger },
            { provide: SECURE_CONTEXT, useValue: true },
            { provide: LIVEKIT_ROOM_FACTORY, useValue: () => failing as unknown as Room },
          ],
        });
        adapter = TestBed.inject(LiveKitRoomAdapter);

        await expectAsync(adapter.connect(anAccess())).toBeRejectedWith(
          new RoomFailure(kind as RoomFailure['kind']),
        );
        expect(
          logger.entries.some((e) => e.level === 'error' && e.message === 'Room connection failed'),
        ).toBeTrue();
      });
    }

    it('leaves the previous room before entering a new one', async () => {
      await adapter.connect(anAccess(1));
      const first = room();

      await adapter.connect(anAccess(2));

      expect(first.disconnects).toBe(1);
      expect(rooms.length).toBe(2);
    });
  });

  describe('the microphone', () => {
    it('asks the browser before entering, and publishes that track once in', async () => {
      expect(await adapter.requestMicrophone()).toBe('on');
      await adapter.connect(anAccess());

      expect(await adapter.enableMicrophone()).toBe('on');
      expect(room().published).toEqual([
        { track: microphones[0]!.mediaStreamTrack, options: { source: Track.Source.Microphone } },
      ]);
      expect(room().microphoneEnabled).toBeFalse();
    });

    it('asks again when there is no track waiting, as when retrying', async () => {
      await adapter.connect(anAccess());

      expect(await adapter.enableMicrophone()).toBe('on');
      expect(room().microphoneEnabled).toBeTrue();
    });

    const answers: readonly [string, string][] = [
      ['NotAllowedError', 'denied'],
      ['NotFoundError', 'not_found'],
      ['NotReadableError', 'unavailable'],
      ['AbortError', 'unavailable'],
    ];
    for (const [name, state] of answers) {
      it(`reads ${name} as ${state} when asking before entering, and logs it`, async () => {
        microphoneFailure = mediaError(name);

        expect(await adapter.requestMicrophone()).toBe(state as never);
        expect(logger.entries).toContain(
          jasmine.objectContaining({
            level: 'warn',
            message: 'Microphone unavailable',
            context: { failure: state, errorName: name },
          }),
        );
      });

      it(`reads ${name} as ${state} when asking again in the room`, async () => {
        await adapter.connect(anAccess());
        room().microphoneFailure = mediaError(name);

        expect(await adapter.enableMicrophone()).toBe(state as never);
      });
    }

    it('keeps the track asked for when it enters, and lets it go when it leaves', async () => {
      await adapter.requestMicrophone();
      await adapter.connect(anAccess());
      expect(microphones[0]!.stopped).toBeFalse();

      await adapter.requestMicrophone();
      expect(microphones[0]!.stopped).toBeTrue();

      await adapter.disconnect();
      expect(microphones[1]!.stopped).toBeTrue();
    });

    it('lets the track go when it could not enter', async () => {
      await adapter.requestMicrophone();
      nextConnectFailure = ConnectionError.timeout('slow');

      await expectAsync(adapter.connect(anAccess())).toBeRejected();

      expect(microphones[0]!.stopped).toBeTrue();
    });

    it('does not ask the browser without a secure context', async () => {
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          LiveKitRoomAdapter,
          { provide: Logger, useValue: logger },
          { provide: SECURE_CONTEXT, useValue: false },
          microphoneProvider,
          { provide: LIVEKIT_ROOM_FACTORY, useValue: () => new FakeRoom() as unknown as Room },
        ],
      });
      const insecure = TestBed.inject(LiveKitRoomAdapter);

      expect(await insecure.requestMicrophone()).toBe('insecure_context');
      await insecure.connect(anAccess());
      expect(await insecure.enableMicrophone()).toBe('insecure_context');
      expect(microphones).toEqual([]);
      await insecure.disconnect();
    });

    it('is unavailable outside a room', async () => {
      expect(await adapter.enableMicrophone()).toBe('unavailable');
    });
  });

  describe('once in the room', () => {
    beforeEach(async () => {
      await adapter.connect(anAccess());
      changes = [];
    });

    it('tells when it is reconnecting and when it is back', () => {
      room().emit(RoomEvent.Reconnecting);
      room().emit(RoomEvent.Reconnected);

      expect(changes.slice(0, 2)).toEqual([{ kind: 'reconnecting' }, { kind: 'reconnected' }]);
      expect(logger.entries.map((e) => e.message)).toContain('Room reconnecting');
    });

    it('tells everyone in the room again when someone silences or turns on their microphone', async () => {
      room().arrive('ana');
      await adapter.muteMicrophone(false);
      changes = [];

      room().remoteParticipants.get('ana')!.isMicrophoneEnabled = false;
      room().emit(RoomEvent.TrackMuted);

      expect(changes).toEqual([
        {
          kind: 'presence',
          present: [
            {
              identity: 'eva',
              agent: false,
              local: true,
              muted: false,
              agentState: null,
              agentText: null,
            },
            {
              identity: 'ana',
              agent: false,
              local: false,
              muted: true,
              agentState: null,
              agentText: null,
            },
          ],
        },
      ]);
    });

    it('tells everyone in the room each time someone arrives', () => {
      room().arrive('ana');
      room().arrive('agilina', true);

      expect(changes).toEqual([
        {
          kind: 'presence',
          present: [
            {
              identity: 'eva',
              agent: false,
              local: true,
              muted: true,
              agentState: null,
              agentText: null,
            },
            {
              identity: 'ana',
              agent: false,
              local: false,
              muted: false,
              agentState: null,
              agentText: null,
            },
          ],
        },
        {
          kind: 'presence',
          present: [
            {
              identity: 'eva',
              agent: false,
              local: true,
              muted: true,
              agentState: null,
              agentText: null,
            },
            {
              identity: 'ana',
              agent: false,
              local: false,
              muted: false,
              agentState: null,
              agentText: null,
            },
            {
              identity: 'agilina',
              agent: true,
              local: false,
              muted: false,
              agentState: null,
              agentText: null,
            },
          ],
        },
      ]);
    });

    it('tells everyone in the room again when Agilina tells her state, and only a known one', () => {
      room().arrive('agilina', true);
      changes = [];

      room().remoteParticipants.get('agilina')!.attributes = { 'agilina.state': 'no_facilitation' };
      room().emit(RoomEvent.ParticipantAttributesChanged);
      room().remoteParticipants.get('agilina')!.attributes = { 'agilina.state': 'dancing' };
      room().emit(RoomEvent.ParticipantAttributesChanged);

      expect(
        changes.map((change) => change.kind === 'presence' && change.present[1]?.agentState),
      ).toEqual(['no_facilitation', null]);
    });

    it('leaves out the state that someone who is not an agent claims', () => {
      room().arrive('ana', false, { 'agilina.state': 'standby' });
      room().localParticipant.attributes = { 'agilina.state': 'no_facilitation' };
      changes = [];

      room().emit(RoomEvent.ParticipantAttributesChanged);

      expect(
        changes.map(
          (change) =>
            change.kind === 'presence' && change.present.map((presence) => presence.agentState),
        ),
      ).toEqual([[null, null]]);
    });

    it('tells what Agilina could not say out loud, and forgets it once she clears it', () => {
      room().arrive('agilina', true);
      changes = [];

      room().remoteParticipants.get('agilina')!.attributes = { 'agilina.text': 'Hola, equipo.' };
      room().emit(RoomEvent.ParticipantAttributesChanged);
      room().remoteParticipants.get('agilina')!.attributes = { 'agilina.text': '' };
      room().emit(RoomEvent.ParticipantAttributesChanged);

      expect(
        changes.map((change) => change.kind === 'presence' && change.present[1]?.agentText),
      ).toEqual(['Hola, equipo.', null]);
    });

    it('leaves out the text that someone who is not an agent writes as Agilina', () => {
      room().arrive('ana', false, { 'agilina.text': 'Soy Agilina' });
      room().localParticipant.attributes = { 'agilina.text': 'Yo también' };
      changes = [];

      room().emit(RoomEvent.ParticipantAttributesChanged);

      expect(
        changes.map(
          (change) =>
            change.kind === 'presence' && change.present.map((presence) => presence.agentText),
        ),
      ).toEqual([[null, null]]);
    });

    it('leaves out who leaves, even while the SDK still holds them', () => {
      room().arrive('ana');
      room().arrive('luis');
      changes = [];

      room().emit(RoomEvent.ParticipantDisconnected, { identity: 'ana', isAgent: false });

      expect(changes).toEqual([
        {
          kind: 'presence',
          present: [
            {
              identity: 'eva',
              agent: false,
              local: true,
              muted: true,
              agentState: null,
              agentText: null,
            },
            {
              identity: 'luis',
              agent: false,
              local: false,
              muted: false,
              agentState: null,
              agentText: null,
            },
          ],
        },
      ]);
    });

    it('tells everyone in the room again once it is back', () => {
      room().arrive('ana');
      changes = [];

      room().emit(RoomEvent.Reconnecting);
      room().emit(RoomEvent.Reconnected);

      expect(changes).toEqual([
        { kind: 'reconnecting' },
        { kind: 'reconnected' },
        {
          kind: 'presence',
          present: [
            {
              identity: 'eva',
              agent: false,
              local: true,
              muted: true,
              agentState: null,
              agentText: null,
            },
            {
              identity: 'ana',
              agent: false,
              local: false,
              muted: false,
              agentState: null,
              agentText: null,
            },
          ],
        },
      ]);
    });

    it('tells who is speaking, the participant and Agilina included, and when nobody is', () => {
      room().emit(RoomEvent.ActiveSpeakersChanged, [
        room().localParticipant,
        { identity: 'agilina', isAgent: true },
      ]);
      room().emit(RoomEvent.ActiveSpeakersChanged, []);

      expect(changes).toEqual([
        { kind: 'speaking', identities: ['eva', 'agilina'] },
        { kind: 'speaking', identities: [] },
      ]);
    });

    it('tells the connection is lost when the room drops it', () => {
      room().emit(RoomEvent.Disconnected, DisconnectReason.JOIN_FAILURE);

      expect(changes).toEqual([{ kind: 'lost' }]);
    });

    it('says nothing when it is the participant who leaves', async () => {
      await adapter.disconnect();

      expect(changes).toEqual([]);
      expect(logger.entries.map((e) => e.message)).toContain('Room left');
    });

    it('says nothing about a room it already left', async () => {
      const old = room();
      await adapter.connect(anAccess(2));
      changes = [];

      old.emit(RoomEvent.Reconnecting);
      old.emit(RoomEvent.Reconnected);
      old.arrive('ana');
      old.emit(RoomEvent.ParticipantDisconnected, { identity: 'ana', isAgent: false });
      old.emit(RoomEvent.ActiveSpeakersChanged, [{ identity: 'ana', isAgent: false }]);
      old.emit(RoomEvent.Disconnected, DisconnectReason.JOIN_FAILURE);

      expect(changes).toEqual([]);
    });

    it('plays the audio of each participant and takes it out when it goes', () => {
      const track = anAudioTrack();

      room().emit(RoomEvent.TrackSubscribed, track);
      expect(document.querySelectorAll('[data-testid="remote-audio"]').length).toBe(1);

      room().emit(RoomEvent.TrackUnsubscribed, track);
      expect(document.querySelectorAll('[data-testid="remote-audio"]').length).toBe(0);
    });

    it('ignores tracks that are not audio', () => {
      room().emit(RoomEvent.TrackSubscribed, { ...anAudioTrack(), kind: Track.Kind.Video });

      expect(document.querySelectorAll('[data-testid="remote-audio"]').length).toBe(0);
    });

    it('takes the audio out of the page when it leaves', async () => {
      room().emit(RoomEvent.TrackSubscribed, anAudioTrack());

      await adapter.disconnect();

      expect(document.querySelectorAll('[data-testid="remote-audio"]').length).toBe(0);
    });

    it('tells when the browser blocks the audio, and starts it on demand', async () => {
      room().canPlaybackAudio = false;
      room().emit(RoomEvent.AudioPlaybackStatusChanged);

      await adapter.resumeAudio();

      expect(changes).toEqual([{ kind: 'audio_blocked', blocked: true }]);
      expect(room().audioStarts).toBe(1);
    });

    it('silences the published microphone and turns it on again (AGI-61)', async () => {
      await adapter.muteMicrophone(false);
      expect(room().microphoneEnabled).toBeTrue();

      await adapter.muteMicrophone(true);
      expect(room().microphoneEnabled).toBeFalse();
    });
  });

  describe('the options of the room', () => {
    it('carries only audio and stops reconnecting after thirty seconds', () => {
      const policy = ROOM_OPTIONS.reconnectPolicy!;

      expect(ROOM_OPTIONS.adaptiveStream).toBeFalse();
      expect(ROOM_OPTIONS.dynacast).toBeFalse();
      expect(policy.nextRetryDelayInMs({ retryCount: 0, elapsedMs: 0 })).toBe(0);
      expect(policy.nextRetryDelayInMs({ retryCount: 6, elapsedMs: 29_000 })).toBeNull();
    });
  });
});
