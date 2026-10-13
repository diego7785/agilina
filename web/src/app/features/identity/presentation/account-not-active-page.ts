import { Component, inject, signal } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { AuthSession } from '@core/auth/auth-session';
import { Button } from '@shared/ui/button';

/**
 * Where a person lands when Keycloak knows them but this organization does not (they have no
 * active user in it). Signing in again cannot help, so the page says so and offers to end the
 * session, to come back with another account.
 */
@Component({
  selector: 'agl-account-not-active-page',
  imports: [TranslocoDirective, Button],
  templateUrl: './account-not-active-page.html',
})
export class AccountNotActivePage {
  private readonly session = inject(AuthSession);

  protected readonly leaving = signal(false);

  protected signOut(): void {
    if (this.leaving()) {
      return;
    }
    this.leaving.set(true);
    void this.session.signOut();
  }
}
