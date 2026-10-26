import { type Observable, of, Subject, throwError } from 'rxjs';

import { DailyParticipantsPort } from '@features/ceremonies/application/daily-participants.port';
import { RoomAccessPort } from '@features/ceremonies/application/room-access.port';
import { type RoomChange, RoomPort } from '@features/ceremonies/application/room.port';
import { type DailyParticipant } from '@features/ceremonies/domain/daily-participant';
import { type MicrophoneState } from '@features/ceremonies/domain/microphone-state';
import { type RoomAccess } from '@features/ceremonies/domain/room-access';
import { type AgentState, type RoomPresence } from '@features/ceremonies/domain/room-presence';

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

/** A person invited to the daily, with an email made from the first word of their name. */
export function aDailyParticipant(identity: string, fullName: string): DailyParticipant {
  const first = fullName.split(' ')[0]!.toLowerCase();
  return { identity, fullName, email: `${first}@example.test` };
}

/** Someone in the room: a person seen by somebody else, unless the test says otherwise. */
export function aPresence(
  identity: string,
  {
    agent = false,
    local = false,
    muted = false,
    agentState = null,
  }: { agent?: boolean; local?: boolean; muted?: boolean; agentState?: AgentState | null } = {},
): RoomPresence {
  return { identity, agent, local, muted, agentState };
}

/** API double: it hands over `participants` each time, or the failure the test sets. */
export class FakeDailyParticipantsPort extends DailyParticipantsPort {
  readonly requested: string[] = [];
  participants: readonly DailyParticipant[] = [];
  failure: unknown = null;

  participantsOf(teamId: string): Observable<readonly DailyParticipant[]> {
    this.requested.push(teamId);
    return this.failure === null ? of(this.participants) : throwError(() => this.failure);
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
  /** What silencing or turning on the microphone fails with, if anything. */
  muteFailure: Error | null = null;
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

  muteMicrophone(muted: boolean): Promise<void> {
    this.calls.push(muted ? 'mute' : 'unmute');
    return this.muteFailure === null ? Promise.resolve() : Promise.reject(this.muteFailure);
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
