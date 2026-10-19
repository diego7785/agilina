import { type Observable, of, Subject, throwError } from 'rxjs';

import { RoomAccessPort } from '@features/ceremonies/application/room-access.port';
import { type RoomChange, RoomPort } from '@features/ceremonies/application/room.port';
import { type MicrophoneState } from '@features/ceremonies/domain/microphone-state';
import { type RoomAccess } from '@features/ceremonies/domain/room-access';

/** An access to the room of Atlas's daily; `n` tells one access from the next. */
export function anAccess(n = 1): RoomAccess {
  return {
    roomName: 'acme-3f2c9a1e-8d4b-4c7a-9e21-5b6f0d1a2c3e',
    token: `token-${n}`,
    expiresAt: '2026-10-08T16:00:00Z',
    serverUrl: 'wss://agilina.livekit.test',
  };
}

/** API double: it hands over a new access each time, or the failure the test sets. */
export class FakeRoomAccessPort extends RoomAccessPort {
  readonly requested: string[] = [];
  failure: unknown = null;

  requestAccess(teamId: string): Observable<RoomAccess> {
    this.requested.push(teamId);
    return this.failure === null
      ? of(anAccess(this.requested.length))
      : throwError(() => this.failure);
  }
}

/**
 * Room double: it enters at once (or fails with what the test queues in `connectFailures`),
 * answers the microphone with `microphoneAnswer` (asked before entering, `microphonePrompts`, and
 * published once in, `microphoneRequests`) and lets the test emit the room's changes. `calls` keeps
 * the order of what it was asked.
 */
export class FakeRoomPort extends RoomPort {
  private readonly stream = new Subject<RoomChange>();
  readonly changes = this.stream.asObservable();
  readonly connected: RoomAccess[] = [];
  readonly connectFailures: Error[] = [];
  microphoneAnswer: MicrophoneState = 'on';
  microphonePrompts = 0;
  microphoneRequests = 0;
  readonly calls: string[] = [];
  audioResumed = 0;
  disconnects = 0;

  connect(access: RoomAccess): Promise<void> {
    this.calls.push('connect');
    this.connected.push(access);
    const failure = this.connectFailures.shift();
    return failure === undefined ? Promise.resolve() : Promise.reject(failure);
  }

  requestMicrophone(): Promise<MicrophoneState> {
    this.calls.push('requestMicrophone');
    this.microphonePrompts++;
    return Promise.resolve(this.microphoneAnswer);
  }

  enableMicrophone(): Promise<MicrophoneState> {
    this.calls.push('enableMicrophone');
    this.microphoneRequests++;
    return Promise.resolve(this.microphoneAnswer);
  }

  resumeAudio(): Promise<void> {
    this.audioResumed++;
    return Promise.resolve();
  }

  disconnect(): Promise<void> {
    this.disconnects++;
    return Promise.resolve();
  }

  emit(change: RoomChange): void {
    this.stream.next(change);
  }
}
