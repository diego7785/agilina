import { DOCUMENT, inject, Injectable } from '@angular/core';
import {
  ConnectionError,
  ConnectionErrorReason,
  DisconnectReason,
  type LocalAudioTrack,
  MediaDeviceFailure,
  type Participant,
  type RemoteParticipant,
  type RemoteTrack,
  type Room,
  RoomEvent,
  Track,
} from 'livekit-client';
import { type Observable, Subject } from 'rxjs';

import { Logger } from '@core/logging/logger';

import { LIVEKIT_MICROPHONE, LIVEKIT_ROOM_FACTORY } from './livekit-room-factory';
import { SECURE_CONTEXT } from './secure-context';
import { type RoomChange, type RoomPort } from '../application/room.port';
import { type MicrophoneState } from '../domain/microphone-state';
import { type RoomAccess } from '../domain/room-access';
import { RoomFailure, type RoomFailureKind } from '../domain/room-failure';

/**
 * LiveKit adapter of the room port: the only place that knows `livekit-client`. Each connection
 * is a new `Room`; the others' audio is played by `<audio>` elements in a hidden container of the
 * page, one per track, which go away with the track. The microphone is asked for before entering
 * (a track waiting to be published), which also lets the browser show its real addresses to
 * WebRTC. It logs what LiveKit reports, never the token.
 */
@Injectable()
export class LiveKitRoomAdapter implements RoomPort {
  private readonly createRoom = inject(LIVEKIT_ROOM_FACTORY);
  private readonly askMicrophone = inject(LIVEKIT_MICROPHONE);
  private readonly secureContext = inject(SECURE_CONTEXT);
  private readonly document = inject(DOCUMENT);
  private readonly logger = inject(Logger);
  private readonly changeStream = new Subject<RoomChange>();
  private room: Room | null = null;
  private audio: HTMLElement | null = null;
  /** The microphone asked for before entering, until it is published. */
  private microphone: LocalAudioTrack | null = null;

  readonly changes: Observable<RoomChange> = this.changeStream.asObservable();

  async connect(access: RoomAccess): Promise<void> {
    // Leaves the previous room, but keeps the microphone asked for to enter this one.
    await this.leave();
    const room = this.createRoom();
    this.room = room;
    this.listen(room);
    try {
      await room.connect(access.serverUrl, access.token, { autoSubscribe: true });
    } catch (error: unknown) {
      this.release(room);
      this.dropMicrophone();
      this.logger.error('Room connection failed', error);
      throw new RoomFailure(connectionFailureOf(error));
    }
    this.logger.info('Room joined');
    this.emitFor(room, { kind: 'audio_blocked', blocked: !room.canPlaybackAudio });
    this.emitFor(room, presenceOf(room));
  }

  async requestMicrophone(): Promise<MicrophoneState> {
    if (!this.secureContext) {
      return this.insecure();
    }
    this.dropMicrophone();
    try {
      this.microphone = await this.askMicrophone();
      return 'on';
    } catch (error: unknown) {
      return this.unavailable(error);
    }
  }

  async enableMicrophone(): Promise<MicrophoneState> {
    if (!this.secureContext) {
      return this.insecure();
    }
    const room = this.room;
    if (room === null) {
      return 'unavailable';
    }
    try {
      const prepared = this.microphone;
      this.microphone = null;
      if (prepared === null) {
        await room.localParticipant.setMicrophoneEnabled(true);
      } else {
        // The browser's own track: the SDK's types for its wrapper do not meet this project's
        // strict optional properties. Marked as the microphone, it is published like one.
        await room.localParticipant.publishTrack(prepared.mediaStreamTrack, {
          source: Track.Source.Microphone,
        });
      }
      return 'on';
    } catch (error: unknown) {
      return this.unavailable(error);
    }
  }

  async muteMicrophone(muted: boolean): Promise<void> {
    // The SDK mutes the published microphone track, so the others see it muted, not gone.
    await this.room?.localParticipant.setMicrophoneEnabled(!muted);
  }

  async resumeAudio(): Promise<void> {
    await this.room?.startAudio();
  }

  async disconnect(): Promise<void> {
    this.dropMicrophone();
    await this.leave();
  }

  private async leave(): Promise<void> {
    const room = this.room;
    if (room === null) {
      return;
    }
    this.release(room);
    await room.disconnect();
    this.logger.info('Room left');
  }

  private listen(room: Room): void {
    room
      .on(RoomEvent.Reconnecting, () => {
        this.logger.warn('Room reconnecting');
        this.emitFor(room, { kind: 'reconnecting' });
      })
      .on(RoomEvent.Reconnected, () => {
        this.logger.info('Room reconnected');
        this.emitFor(room, { kind: 'reconnected' });
        this.emitFor(room, presenceOf(room));
      })
      .on(RoomEvent.ParticipantConnected, () => {
        this.emitFor(room, presenceOf(room));
      })
      // Someone's microphone was silenced, turned on, published or taken away.
      .on(RoomEvent.TrackMuted, () => {
        this.emitFor(room, presenceOf(room));
      })
      .on(RoomEvent.TrackUnmuted, () => {
        this.emitFor(room, presenceOf(room));
      })
      .on(RoomEvent.TrackPublished, () => {
        this.emitFor(room, presenceOf(room));
      })
      .on(RoomEvent.TrackUnpublished, () => {
        this.emitFor(room, presenceOf(room));
      })
      .on(RoomEvent.LocalTrackPublished, () => {
        this.emitFor(room, presenceOf(room));
      })
      .on(RoomEvent.LocalTrackUnpublished, () => {
        this.emitFor(room, presenceOf(room));
      })
      .on(RoomEvent.ParticipantDisconnected, (participant: RemoteParticipant) => {
        this.emitFor(room, presenceOf(room, participant.identity));
      })
      .on(RoomEvent.Disconnected, (reason?: DisconnectReason) => {
        if (this.room !== room || reason === DisconnectReason.CLIENT_INITIATED) {
          return;
        }
        this.logger.warn('Room connection lost', { reason: reason ?? 'unknown' });
        this.release(room);
        this.changeStream.next({ kind: 'lost' });
      })
      .on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio) {
          const element = track.attach();
          element.dataset['testid'] = 'remote-audio';
          this.audioContainer().append(element);
        }
      })
      .on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        for (const element of track.detach()) {
          element.remove();
        }
      })
      .on(RoomEvent.AudioPlaybackStatusChanged, () => {
        this.emitFor(room, { kind: 'audio_blocked', blocked: !room.canPlaybackAudio });
      })
      .on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
        this.emitFor(room, {
          kind: 'speaking',
          identities: speakers.map((speaker) => speaker.identity),
        });
      });
  }

  private insecure(): MicrophoneState {
    this.logger.warn('Microphone unavailable', { failure: 'insecure_context' });
    return 'insecure_context';
  }

  private unavailable(error: unknown): MicrophoneState {
    const state = microphoneStateOf(error);
    this.logger.warn('Microphone unavailable', { failure: state, errorName: nameOf(error) });
    return state;
  }

  /** Lets go of a microphone asked for and never published, so the browser stops using it. */
  private dropMicrophone(): void {
    this.microphone?.stop();
    this.microphone = null;
  }

  /** Only the room in use speaks: a late event of one already left says nothing. */
  private emitFor(room: Room, change: RoomChange): void {
    if (this.room === room) {
      this.changeStream.next(change);
    }
  }

  /** Forgets the room and takes the others' audio out of the page. */
  private release(room: Room): void {
    if (this.room === room) {
      this.room = null;
    }
    this.audio?.remove();
    this.audio = null;
  }

  private audioContainer(): HTMLElement {
    if (this.audio === null) {
      this.audio = this.document.createElement('div');
      this.audio.hidden = true;
      this.document.body.append(this.audio);
    }
    return this.audio;
  }
}

/**
 * Everyone in the room now, the participant first. The one who `leaving` names is left out, in
 * case the SDK still holds them while it tells they left.
 */
function presenceOf(room: Room, leaving?: string): RoomChange {
  const local = room.localParticipant;
  const remote = [...room.remoteParticipants.values()].filter(
    (participant) => participant.identity !== leaving,
  );
  return {
    kind: 'presence',
    present: [
      {
        identity: local.identity,
        agent: local.isAgent,
        local: true,
        muted: !local.isMicrophoneEnabled,
      },
      ...remote.map((participant) => ({
        identity: participant.identity,
        agent: participant.isAgent,
        local: false,
        muted: !participant.isMicrophoneEnabled,
      })),
    ],
  };
}

/** Why LiveKit did not let the participant in. */
function connectionFailureOf(error: unknown): RoomFailureKind {
  if (!(error instanceof ConnectionError)) {
    return 'unexpected';
  }
  switch (error.reason) {
    case ConnectionErrorReason.NotAllowed:
      return 'token_rejected';
    case ConnectionErrorReason.ServerUnreachable:
    case ConnectionErrorReason.Timeout:
    case ConnectionErrorReason.WebSocket:
    case ConnectionErrorReason.InternalError:
      return 'service_unavailable';
    default:
      return 'unexpected';
  }
}

/** The name of a browser error (`NotAllowedError`, `NotSupportedError`…), never its message. */
function nameOf(error: unknown): string {
  return error instanceof Error ? error.name : 'unknown';
}

/** What the browser's answer to the microphone means (`NotAllowedError`, `NotFoundError`…). */
function microphoneStateOf(error: unknown): MicrophoneState {
  switch (MediaDeviceFailure.getFailure(error)) {
    case MediaDeviceFailure.PermissionDenied:
      return 'denied';
    case MediaDeviceFailure.NotFound:
      return 'not_found';
    default:
      return 'unavailable';
  }
}
