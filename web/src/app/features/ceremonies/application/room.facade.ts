import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';

import { DailyParticipantsPort } from './daily-participants.port';
import { RoomAccessPort } from './room-access.port';
import { type RoomChange, RoomPort } from './room.port';
import { AGILINA_ARRIVAL_BUDGET_MS, agilinaStatusOf } from '../domain/agilina-status';
import { type ConnectionStatus } from '../domain/connection-status';
import { type DailyParticipant } from '../domain/daily-participant';
import { type MicrophoneState } from '../domain/microphone-state';
import { participantRows } from '../domain/participant-rows';
import { RECONNECT_BUDGET_MS } from '../domain/reconnect-budget';
import { type RoomAccess } from '../domain/room-access';
import { type RoomFailureKind, roomFailureKindOf } from '../domain/room-failure';
import { type RoomPresence } from '../domain/room-presence';

/**
 * State of the participant in the room of the daily (AGI-60): the connection, the microphone,
 * why it failed and whether the browser blocked the others' audio. Provided by the page, so it
 * lives and dies with it: leaving the page leaves the room.
 *
 * Joining asks the browser for the microphone first (the person answers it before anything
 * else, as the story tells), then asks the API for a new access, enters the room and publishes
 * the microphone: one that is denied, missing or busy does not keep anybody out, they stay as
 * listeners.
 * If LiveKit refuses the token (it expired, for example) it asks for a new one once. Once in,
 * LiveKit itself tries to get back when the network drops; if it is not back within
 * `RECONNECT_BUDGET_MS` the facade leaves the room (an attempt that hangs would otherwise keep
 * it reconnecting past the budget), and trying again asks for a new access as well. The adapters already logged what went wrong, so it is not logged
 * again here.
 * The list of participants (AGI-61) joins the invited, asked for on each connection once in, with
 * who the room says is in it; if the invited cannot be read, it lists only who is in the room.
 * It also follows who is speaking, as LiveKit tells it, and whether Agilina (the agent in the
 * room) is there and speaking. Her status is the state she published; if she has not told one
 * `AGILINA_ARRIVAL_BUDGET_MS` after the participant got in, she is unavailable until she does.
 */
@Injectable()
export class RoomFacade {
  private readonly accessPort = inject(RoomAccessPort);
  private readonly participantsPort = inject(DailyParticipantsPort);
  private readonly room = inject(RoomPort);
  private teamId: string | null = null;
  /** Increases with every attempt to join, so that a late answer of an old one is ignored. */
  private attempt = 0;
  private destroyed = false;
  /** Gives up on getting back once the budget to reconnect is spent. */
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  /** Marks Agilina unavailable if she has not told her state once the budget to arrive is spent. */
  private arrivalTimer: ReturnType<typeof setTimeout> | null = null;

  private readonly currentStatus = signal<ConnectionStatus>('connecting');
  private readonly currentMicrophone = signal<MicrophoneState>('pending');
  private readonly currentFailure = signal<RoomFailureKind | null>(null);
  private readonly currentAudioBlocked = signal(false);
  private readonly currentMuted = signal(false);
  private readonly invitees = signal<readonly DailyParticipant[]>([]);
  private readonly present = signal<readonly RoomPresence[]>([]);
  private readonly speaking = signal<readonly string[]>([]);
  private readonly arrivalExpired = signal(false);

  readonly status = this.currentStatus.asReadonly();
  readonly microphone = this.currentMicrophone.asReadonly();
  /** Why the participant is out of the room, while the status is `failed`. */
  readonly failure = this.currentFailure.asReadonly();
  readonly audioBlocked = this.currentAudioBlocked.asReadonly();
  /** Whether the participant silenced their microphone, which stays published (`on`). */
  readonly muted = this.currentMuted.asReadonly();
  /** The invited in turn order, connected or not, then whoever else is in the room. */
  readonly participants = computed(() =>
    participantRows(this.invitees(), this.present(), this.speaking()),
  );
  readonly agilinaPresent = computed(() => this.present().some((presence) => presence.agent));
  readonly agilinaStatus = computed(() => agilinaStatusOf(this.present(), this.arrivalExpired()));
  readonly agilinaSpeaking = computed(() =>
    this.present().some(
      (presence) => presence.agent && this.speaking().includes(presence.identity),
    ),
  );

  constructor() {
    this.room.changes.pipe(takeUntilDestroyed()).subscribe((change) => {
      this.apply(change);
    });
    inject(DestroyRef).onDestroy(() => {
      this.destroyed = true;
      this.attempt++;
      this.stopReconnectTimer();
      this.stopArrivalTimer();
      void this.room.disconnect();
    });
  }

  /** Enters the room of the daily of this team. */
  join(teamId: string): void {
    this.teamId = teamId;
    void this.connect();
  }

  /** Tries to enter again, with a new access, after it failed or the connection was lost. */
  retry(): void {
    void this.connect();
  }

  /** Asks for the microphone again, once the person allowed it or plugged one in. */
  async retryMicrophone(): Promise<void> {
    this.currentMicrophone.set('pending');
    this.currentMuted.set(false);
    const state = await this.room.enableMicrophone();
    if (!this.destroyed) {
      this.currentMicrophone.set(state);
    }
  }

  /**
   * Silences the microphone or turns it on again. If it cannot be turned on again (the device was
   * unplugged, say), the person stays as a listener with «Reintentar micrófono».
   */
  async toggleMute(): Promise<void> {
    const muted = !this.currentMuted();
    try {
      await this.room.muteMicrophone(muted);
      this.currentMuted.set(muted);
    } catch {
      if (!this.destroyed) {
        this.currentMuted.set(false);
        this.currentMicrophone.set('unavailable');
      }
    }
  }

  /** Plays the others' audio again after the browser blocked it. */
  async resumeAudio(): Promise<void> {
    await this.room.resumeAudio();
    this.currentAudioBlocked.set(false);
  }

  private async connect(): Promise<void> {
    const teamId = this.teamId;
    if (teamId === null) {
      return;
    }
    const attempt = ++this.attempt;
    const current = (): boolean => attempt === this.attempt;
    this.stopReconnectTimer();
    this.stopArrivalTimer();
    this.currentStatus.set('connecting');
    this.currentFailure.set(null);
    this.currentMicrophone.set('pending');
    this.currentMuted.set(false);
    this.currentAudioBlocked.set(false);
    this.present.set([]);
    this.speaking.set([]);
    try {
      await this.room.disconnect();
      const asked = await this.room.requestMicrophone();
      if (!current()) {
        return;
      }
      await this.enter(teamId, current);
      if (!current()) {
        return;
      }
      this.currentStatus.set('connected');
      this.arrivalTimer = setTimeout(() => {
        this.arrivalTimer = null;
        this.arrivalExpired.set(true);
      }, AGILINA_ARRIVAL_BUDGET_MS);
      void this.loadInvitees(teamId, current);
      const microphone = asked === 'on' ? await this.room.enableMicrophone() : asked;
      if (current()) {
        this.currentMicrophone.set(microphone);
      }
    } catch (error: unknown) {
      if (current()) {
        this.currentStatus.set('failed');
        this.currentFailure.set(roomFailureKindOf(error));
      }
    }
  }

  /** Enters with a new access; if LiveKit refuses the token, with one more, and no more. */
  private async enter(teamId: string, current: () => boolean): Promise<void> {
    const access = await this.access(teamId);
    if (!current()) {
      return;
    }
    try {
      await this.room.connect(access);
    } catch (error: unknown) {
      if (roomFailureKindOf(error) !== 'token_rejected' || !current()) {
        throw error;
      }
      const renewed = await this.access(teamId);
      if (current()) {
        await this.room.connect(renewed);
      }
    }
  }

  private access(teamId: string): Promise<RoomAccess> {
    return firstValueFrom(this.accessPort.requestAccess(teamId));
  }

  /** Without the invited (the adapter logged why), the list keeps only who is in the room. */
  private async loadInvitees(teamId: string, current: () => boolean): Promise<void> {
    try {
      const invitees = await firstValueFrom(this.participantsPort.participantsOf(teamId));
      if (current()) {
        this.invitees.set(invitees);
      }
    } catch {
      // Nothing else to do: the list shows who is in the room.
    }
  }

  /** The connection did not come back in time: leave the room and let the person try again. */
  private giveUp(): void {
    this.reconnectTimer = null;
    if (this.currentStatus() !== 'reconnecting') {
      return;
    }
    this.attempt++;
    this.lose();
    void this.room.disconnect();
  }

  private lose(): void {
    this.stopArrivalTimer();
    this.currentStatus.set('failed');
    this.currentFailure.set('connection_lost');
    this.present.set([]);
    this.speaking.set([]);
  }

  private stopReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private stopArrivalTimer(): void {
    if (this.arrivalTimer !== null) {
      clearTimeout(this.arrivalTimer);
      this.arrivalTimer = null;
    }
    this.arrivalExpired.set(false);
  }

  private apply(change: RoomChange): void {
    switch (change.kind) {
      case 'reconnecting':
        if (this.currentStatus() === 'connected') {
          this.currentStatus.set('reconnecting');
          // Nobody is heard while the connection is down; LiveKit tells the speakers again after.
          this.speaking.set([]);
          this.reconnectTimer = setTimeout(() => {
            this.giveUp();
          }, RECONNECT_BUDGET_MS);
        }
        return;
      case 'reconnected':
        if (this.currentStatus() === 'reconnecting') {
          this.stopReconnectTimer();
          this.currentStatus.set('connected');
        }
        return;
      case 'lost':
        this.stopReconnectTimer();
        if (this.currentStatus() !== 'failed') {
          this.lose();
        }
        return;
      case 'audio_blocked':
        this.currentAudioBlocked.set(change.blocked);
        return;
      case 'presence':
        this.present.set(change.present);
        return;
      case 'speaking':
        this.speaking.set(change.identities);
        return;
    }
  }
}
