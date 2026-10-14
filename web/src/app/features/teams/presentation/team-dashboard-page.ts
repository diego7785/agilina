import { Component, computed, inject, input, type OnInit } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Button } from '@shared/ui/button';
import {
  formatCalendarDate,
  formatLocalTime,
  formatShortLocalDate,
} from '@shared/utils/local-date-time';

import { problemMessageKey } from './problem-message';
import { TeamDashboardFacade } from '../application/team-dashboard.facade';
import { TeamShellFacade } from '../application/team-shell.facade';

/**
 * Dashboard of a team: the day of its active sprint, its next ceremony, the mode Agilina works
 * in (read only) and the way into the room, which is open only in the window of the ceremony.
 * It is the same for both roles; the settings entry lives in the top bar and is drawn only for
 * an admin. Without an active sprint it says so and offers no room. The API computes the day and
 * the schedule; this page only shows them in the browser's time zone.
 */
@Component({
  selector: 'agl-team-dashboard-page',
  imports: [TranslocoDirective, Button],
  providers: [TeamDashboardFacade, TeamShellFacade],
  templateUrl: './team-dashboard-page.html',
})
export class TeamDashboardPage implements OnInit {
  /** The :teamId of the route, bound by the router (withComponentInputBinding). */
  readonly teamId = input.required<string>();

  private readonly facade = inject(TeamDashboardFacade);
  private readonly shell = inject(TeamShellFacade);

  protected readonly team = this.facade.team;
  protected readonly sprint = this.facade.sprint;
  protected readonly nextCeremony = this.facade.nextCeremony;
  protected readonly joinState = this.facade.joinState;
  protected readonly loading = this.facade.loading;
  protected readonly problemMessage = computed(() => problemMessageKey(this.facade.problem()));

  ngOnInit(): void {
    this.facade.follow(this.teamId);
    this.shell.follow(this.teamId);
  }

  /** A calendar date, as the person reads it in the active language. */
  protected formatDate(date: string, language: string): string {
    return formatCalendarDate(date, language);
  }

  /** The time of an instant in the browser's time zone. */
  protected formatTime(iso: string, language: string): string {
    return formatLocalTime(iso, language);
  }

  /** The short day of an instant in the browser's time zone. */
  protected formatDay(iso: string, language: string): string {
    return formatShortLocalDate(iso, language);
  }
}
