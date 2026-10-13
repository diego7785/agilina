import { Location } from '@angular/common';
import { Component, computed, effect, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoPipe } from '@jsverse/transloco';

import { TenantContext } from '@core/tenant/tenant-context';
import { Button } from '@shared/ui/button';

import { problemMessageKey } from './problem-message';
import { TeamSelectorFacade } from '../application/team-selector.facade';

/**
 * Team selector: the teams of the user, to enter one, and the way to create a new one. With a
 * single team it goes straight in, unless the person asked to choose (the top bar's "switch
 * team" link): then they see the list and the way to create another.
 */
@Component({
  selector: 'agl-team-selector-page',
  imports: [RouterLink, TranslocoDirective, TranslocoPipe, Button],
  providers: [TeamSelectorFacade],
  templateUrl: './team-selector-page.html',
})
export class TeamSelectorPage {
  private readonly facade = inject(TeamSelectorFacade);
  private readonly router = inject(Router);
  protected readonly tenant = inject(TenantContext);

  protected readonly teams = this.facade.teams;
  protected readonly loading = this.facade.loading;
  protected readonly problemMessage = computed(() => problemMessageKey(this.facade.problem()));

  /**
   * Whether the person came asking to choose, which the "switch team" link says in the state of
   * the navigation. It is read from the history entry, not from the router's current navigation:
   * this page hangs from a layout with its own outlet and is created once the navigation is
   * over. The state stays with the entry, so a reload or "back" to it still shows the list.
   */
  private readonly wantsToChoose =
    (inject(Location).getState() as { choose?: unknown } | null)?.choose === true;

  /** With a single team there is nothing to choose: go in, replacing this page in the history
   * so that "back" does not bring the person here just to be sent on again. */
  private readonly enterTheOnlyTeam = effect(() => {
    const team = this.facade.onlyTeam();
    if (team !== null && !this.wantsToChoose) {
      void this.router.navigate(this.tenant.path('teams', team.id), { replaceUrl: true });
    }
  });
}
