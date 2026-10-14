import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { ShellContext } from '@core/shell/shell-context';
import { TenantContext } from '@core/tenant/tenant-context';

/**
 * Top bar of every screen: the brand and, inside a team, the team's name and the label of
 * the user's role in it, a way to change team, the user's name on the right and the entries of
 * the team under them: the dashboard and, for an admin, the settings. Outside a team it says what
 * Agilina is.
 */
@Component({
  selector: 'agl-header',
  imports: [RouterLink, RouterLinkActive, TranslocoDirective],
  templateUrl: './header.html',
})
export class Header {
  /** The product name is a brand: it is not translated. */
  protected readonly brand = 'Agilina';
  protected readonly team = inject(ShellContext).team;
  protected readonly tenant = inject(TenantContext);
  /** Asks the team selector to list the teams even when the person has only one. */
  protected readonly chooseTeam = { choose: true };
  /** The first letters of the first two words of the name, in capitals. */
  protected readonly initials = computed(() =>
    (this.team()?.userName ?? '')
      .split(/\s+/)
      .filter((word) => word.length > 0)
      .slice(0, 2)
      .map((word) => word.charAt(0).toUpperCase())
      .join(''),
  );
}
