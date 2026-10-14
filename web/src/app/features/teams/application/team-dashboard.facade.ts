import { computed, effect, inject, Injectable, signal, type Signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';

import { NOW } from '@core/time/now';

import { TeamsPort } from './teams.port';
import { joinState, nextJoinChange } from '../domain/join-window';
import {
  type DashboardSprint,
  type DashboardTeam,
  type NextCeremony,
  type TeamDashboard,
} from '../domain/team-dashboard';
import { failureKindOf, type TeamFailureKind } from '../domain/team-failure';

/** The longest delay `setTimeout` accepts; a later change is reached by scheduling again. */
const MAX_TIMER_DELAY_MS = 2_147_483_647;

/**
 * State of a team's dashboard: the team, its sprint, its next ceremony and whether the room is
 * open to join, all from one read of the API. Provided by the page, so it lives and dies with it.
 *
 * The room opens and the ceremony starts at known instants, so a timer moves the state at those
 * moments without the person reloading: when the window opens the room becomes joinable, and
 * when the ceremony starts the dashboard asks again for the next one.
 *
 * A failed request (a team the user does not belong to, for example) becomes the `failed` state;
 * the HTTP interceptor has already logged it, so it is not logged again here.
 */
@Injectable()
export class TeamDashboardFacade {
  private readonly teamsPort = inject(TeamsPort);
  private readonly now = inject(NOW);
  private readonly teamId = signal<Signal<string> | null>(null);
  private readonly current = rxResource({
    params: () => this.teamId()?.(),
    stream: ({ params }) => this.teamsPort.dashboard(params),
  });
  /** The instant the state was last worked out at; the timer moves it. */
  private readonly instant = signal(this.now());

  private readonly dashboard = computed<TeamDashboard | null>(() =>
    this.current.hasValue() ? this.current.value() : null,
  );

  readonly team = computed<DashboardTeam | null>(() => this.dashboard()?.team ?? null);
  /** The active sprint, or null when the team has none (or the API has not answered). */
  readonly sprint = computed<DashboardSprint | null>(() => this.dashboard()?.sprint ?? null);
  readonly nextCeremony = computed<NextCeremony | null>(
    () => this.dashboard()?.nextCeremony ?? null,
  );
  /** Whether to draw the settings entry; the API still checks it on every settings route. */
  readonly canConfigure = computed(() => this.dashboard()?.canConfigure ?? false);
  /** Whether the API already answered: until then there is nothing to say about the sprint. */
  readonly known = computed(() => this.dashboard() !== null);
  readonly joinState = computed(() => joinState(this.nextCeremony(), this.instant()));

  readonly loading = this.current.isLoading;
  readonly failed = computed(() => this.current.status() === 'error');
  /** What went wrong, when the team could not be opened. */
  readonly problem = computed<TeamFailureKind | null>(() =>
    this.failed() ? failureKindOf(this.current.error()) : null,
  );

  constructor() {
    // A timer on the next change of the window; it is set again after each one it fires.
    effect((onCleanup) => {
      const change = nextJoinChange(this.nextCeremony(), this.instant());
      if (change === null) {
        return;
      }
      const delay = Math.min(change.getTime() - this.now().getTime(), MAX_TIMER_DELAY_MS);
      const timer = setTimeout(
        () => {
          this.advance();
        },
        Math.max(delay, 0),
      );
      onCleanup(() => {
        clearTimeout(timer);
      });
    });
  }

  /** Loads the dashboard of the team of this id, and loads it again whenever the id changes. */
  follow(teamId: Signal<string>): void {
    this.teamId.set(teamId);
  }

  private advance(): void {
    this.instant.set(this.now());
    const ceremony = this.nextCeremony();
    // Once it has started, the one that comes next is the API's to say.
    if (ceremony !== null && this.instant().getTime() >= new Date(ceremony.startsAt).getTime()) {
      this.current.reload();
    }
  }
}
