import { Component, computed, inject, input, type OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { TenantContext } from '@core/tenant/tenant-context';
import { Button } from '@shared/ui/button';

import { RoomFacade } from '../application/room.facade';
import { isRetriable } from '../domain/room-failure';

/**
 * The room of the team's daily (AGI-60): entering it turns the microphone on, and the page says
 * how the connection is, what happened to the microphone and what to do about it. A participant
 * without a microphone stays as a listener. Who is in the room and who speaks arrive with
 * AGI-61, on this same page. Leaving the page leaves the room.
 */
@Component({
  selector: 'agl-room-page',
  imports: [RouterLink, TranslocoDirective, Button],
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

  protected resumeAudio(): void {
    void this.facade.resumeAudio();
  }
}
