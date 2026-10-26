import { Component, computed, inject, input, type OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, translateSignal } from '@jsverse/transloco';

import { TenantContext } from '@core/tenant/tenant-context';
import { Button } from '@shared/ui/button';

import { ParticipantTile } from './participant-tile';
import { SpeakingIndicator } from './speaking-indicator';
import { RoomFacade } from '../application/room.facade';
import { isRetriable } from '../domain/room-failure';

/**
 * The room of the team's daily (AGI-60): entering it turns the microphone on, and the page says
 * how the connection is, what happened to the microphone and what to do about it. A participant
 * without a microphone stays as a listener. In the room it shows the status of Agilina, whose
 * turn it is, the participants and the actions (AGI-61), marks who is speaking and announces it
 * to a screen reader. Leaving the page leaves the room.
 */
@Component({
  selector: 'agl-room-page',
  imports: [RouterLink, TranslocoDirective, Button, ParticipantTile, SpeakingIndicator],
  providers: [RoomFacade],
  templateUrl: './room-page.html',
})
export class RoomPage implements OnInit {
  /** The :teamId of the route, bound by the router (withComponentInputBinding). */
  readonly teamId = input.required<string>();

  private readonly facade = inject(RoomFacade);
  private readonly tenant = inject(TenantContext);

  protected readonly status = this.facade.status;
  protected readonly microphone = this.facade.microphone;
  protected readonly failure = this.facade.failure;
  protected readonly audioBlocked = this.facade.audioBlocked;
  protected readonly muted = this.facade.muted;
  protected readonly participants = this.facade.participants;
  protected readonly agilinaPresent = this.facade.agilinaPresent;
  protected readonly agilinaSpeaking = this.facade.agilinaSpeaking;
  private readonly unknownName = translateSignal('ceremonies.room.participants.unknown');
  private readonly agilinaName = translateSignal('ceremonies.room.agilina.name');
  /** Who is speaking now, for a screen reader: the rows that speak, then Agilina; empty if nobody. */
  protected readonly speakingNames = computed(() => {
    const names = this.participants()
      .filter((row) => row.speaking)
      .map((row) => row.name || this.unknownName());
    if (this.agilinaSpeaking()) {
      names.push(this.agilinaName());
    }
    return names.join(', ');
  });
  protected readonly inRoom = computed(
    () => this.status() === 'connected' || this.status() === 'reconnecting',
  );
  protected readonly canRetry = computed(() => {
    const failure = this.failure();
    return failure !== null && isRetriable(failure);
  });
  protected readonly dashboardPath = computed(() => this.tenant.path('teams', this.teamId()));

  ngOnInit(): void {
    this.facade.join(this.teamId());
  }

  protected retry(): void {
    this.facade.retry();
  }

  protected retryMicrophone(): void {
    void this.facade.retryMicrophone();
  }

  protected toggleMute(): void {
    void this.facade.toggleMute();
  }

  protected resumeAudio(): void {
    void this.facade.resumeAudio();
  }
}
