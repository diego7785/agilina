import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { NEVER, type Observable } from 'rxjs';

import { TenantContext } from '@core/tenant/tenant-context';
import { InvitationPort } from '@features/identity/application/invitation.port';
import { LoginRedirectPort } from '@features/identity/application/login-redirect.port';
import { HealthPort } from '@features/status/application/health.port';
import { SprintsPort } from '@features/teams/application/sprints.port';
import { TeamsPort } from '@features/teams/application/teams.port';
import { UsersPort } from '@features/teams/application/users.port';
import { type ActiveSprint } from '@features/teams/domain/active-sprint';
import { type Team } from '@features/teams/domain/team';
import { type TeamMembers } from '@features/teams/domain/team-member';
import { FakeAuthSession, provideFakeAuthSession } from '@testing/auth';
import { provideFakeLogger } from '@testing/fake-logger';
import { provideTestI18n } from '@testing/i18n';
import { provideFakeTenantPort } from '@testing/tenant';

import { routes } from './app.routes';

/** Port double that never answers: these tests only look at which screen opens. */
class SilentTeamsPort extends TeamsPort {
  readonly requested: string[] = [];

  listMine(): Observable<readonly Team[]> {
    return NEVER;
  }

  create(): Observable<string> {
    return NEVER;
  }

  get(teamId: string): Observable<Team> {
    this.requested.push(teamId);
    return NEVER;
  }
}

/** Members port double that never answers either. */
class SilentUsersPort extends UsersPort {
  readonly requested: string[] = [];

  list(teamId: string): Observable<TeamMembers> {
    this.requested.push(teamId);
    return NEVER;
  }

  get(): Observable<never> {
    return NEVER;
  }

  me(): Observable<never> {
    return NEVER;
  }

  invite(): Observable<never> {
    return NEVER;
  }

  changeRole(): Observable<never> {
    return NEVER;
  }

  remove(): Observable<never> {
    return NEVER;
  }
}

/** Sprints port double that never answers either. */
class SilentSprintsPort extends SprintsPort {
  readonly requested: string[] = [];

  active(teamId: string): Observable<ActiveSprint | null> {
    this.requested.push(teamId);
    return NEVER;
  }

  start(): Observable<never> {
    return NEVER;
  }

  reconfigure(): Observable<never> {
    return NEVER;
  }
}

describe('routes', () => {
  let port: SilentTeamsPort;
  let members: SilentUsersPort;
  let sprints: SilentSprintsPort;
  let session: FakeAuthSession;
  let harness: RouterTestingHarness;

  async function start(signedIn: boolean): Promise<void> {
    TestBed.resetTestingModule();
    port = new SilentTeamsPort();
    members = new SilentUsersPort();
    sprints = new SilentSprintsPort();
    session = new FakeAuthSession(signedIn);
    TestBed.configureTestingModule({
      providers: [
        provideTestI18n(),
        provideFakeLogger(),
        provideRouter(routes, withComponentInputBinding()),
        { provide: TeamsPort, useValue: port },
        { provide: UsersPort, useValue: members },
        { provide: SprintsPort, useValue: sprints },
        { provide: InvitationPort, useValue: { status: () => NEVER } },
        { provide: LoginRedirectPort, useValue: {} },
        { provide: HealthPort, useValue: { check: () => NEVER } },
        provideFakeAuthSession(session),
        provideFakeTenantPort(),
      ],
    });
    harness = await RouterTestingHarness.create();
  }

  /** The layout the route opens and the screen inside it. */
  async function screenAt(url: string): Promise<string | undefined> {
    await harness.navigateByUrl(url);
    const layout = harness.routeNativeElement;
    const screen = layout?.querySelector('router-outlet + *');
    return `${layout?.tagName.toLowerCase()} > ${screen?.tagName.toLowerCase()}`;
  }

  describe('the screens of a tenant', () => {
    beforeEach(() => start(true));

    it('opens the team selector at /:tenant/teams', async () => {
      expect(await screenAt('/acme/teams')).toBe('agl-centered-layout > agl-team-selector-page');
    });

    it('opens the page of an account that is not active at /:tenant/account-not-active', async () => {
      expect(await screenAt('/acme/account-not-active')).toBe(
        'agl-centered-layout > agl-account-not-active-page',
      );
      expect(session.ensured).toEqual(['/acme/account-not-active']);
    });

    it('opens the creation form at /:tenant/teams/new, not a team called "new"', async () => {
      expect(await screenAt('/acme/teams/new')).toBe('agl-centered-layout > agl-create-team-page');
      expect(port.requested).toEqual([]);
    });

    it('opens the dashboard of the team at /:tenant/teams/:teamId with that id', async () => {
      expect(await screenAt('/acme/teams/team-1')).toBe('agl-app-shell > agl-team-dashboard-page');
      TestBed.tick();

      expect(new Set(port.requested)).toEqual(new Set(['team-1']));
      expect(TestBed.inject(Router).url).toBe('/acme/teams/team-1');
    });

    it('opens the settings of the team at /:tenant/teams/:teamId/settings, with no guard on the role', async () => {
      expect(await screenAt('/acme/teams/team-1/settings')).toBe(
        'agl-app-shell > agl-team-settings-page',
      );
      TestBed.tick();

      expect(members.requested).toEqual(['team-1']);
      // The settings also read the team, for the name and the role label in the top bar.
      expect(port.requested).toEqual(['team-1']);
      expect(TestBed.inject(Router).url).toBe('/acme/teams/team-1/settings');
    });

    it('opens the sprint settings of the team at /:tenant/teams/:teamId/settings/sprint, with no guard on the role', async () => {
      expect(await screenAt('/acme/teams/team-1/settings/sprint')).toBe(
        'agl-app-shell > agl-team-sprint-settings-page',
      );
      TestBed.tick();

      expect(sprints.requested).toEqual(['team-1']);
      expect(members.requested).toEqual(['team-1']);
      // The top bar reads the team too, for its name and the user's label in it.
      expect(port.requested).toEqual(['team-1']);
      expect(TestBed.inject(Router).url).toBe('/acme/teams/team-1/settings/sprint');
    });

    it('reads the sprint of the team on its dashboard', async () => {
      await screenAt('/acme/teams/team-1');
      TestBed.tick();

      expect(sprints.requested).toEqual(['team-1']);
    });

    it('records the tenant of the address, whichever it is', async () => {
      await harness.navigateByUrl('/acme/teams/team-1');
      expect(TestBed.inject(TenantContext).current()).toBe('acme');

      await harness.navigateByUrl('/ecomoda/teams/team-1');
      expect(TestBed.inject(TenantContext).current()).toBe('ecomoda');
    });

    it('sends a signed-in person from the entrance of the tenant to their teams', async () => {
      await harness.navigateByUrl('/ecomoda');

      expect(TestBed.inject(Router).url).toBe('/ecomoda/teams');
    });
  });

  describe('the session', () => {
    beforeEach(() => start(false));

    it('asks a person who is not signed in to sign in at the entrance, to land on their teams', async () => {
      await harness.navigateByUrl('/acme');

      expect(session.ensured).toEqual(['/acme/teams']);
      expect(TestBed.inject(Router).url).not.toBe('/acme/teams');
    });

    it('asks the routes of the teams for a session, and remembers the page asked for', async () => {
      await harness.navigateByUrl('/acme/teams/team-9');

      expect(session.ensured).toEqual(['/acme/teams/team-9']);
      expect(port.requested).toEqual([]);
    });

    it('asks the settings of a team for a session too', async () => {
      await harness.navigateByUrl('/acme/teams/team-9/settings');

      expect(session.ensured).toEqual(['/acme/teams/team-9/settings']);
      expect(members.requested).toEqual([]);
    });

    it('asks the sprint settings of a team for a session too', async () => {
      await harness.navigateByUrl('/acme/teams/team-9/settings/sprint');

      expect(session.ensured).toEqual(['/acme/teams/team-9/settings/sprint']);
      expect(sprints.requested).toEqual([]);
      expect(members.requested).toEqual([]);
    });

    it('keeps the activation and the status public: they never ask for a session', async () => {
      await harness.navigateByUrl('/acme/activate');
      await harness.navigateByUrl('/acme/status');

      expect(session.ensured).toEqual([]);
    });
  });

  describe('an address that names no organization', () => {
    beforeEach(() => start(true));

    const notFoundScreen = 'agl-centered-layout > agl-not-found-page';

    it('is not found at /', async () => {
      expect(await screenAt('/')).toBe(notFoundScreen);
      expect(TestBed.inject(Router).url).toBe('/not-found');
    });

    ['/Acme/teams', '/ac-me', '/platform', '/a'].forEach((url) => {
      it(`is not found at ${url}: it cannot be a tenant`, async () => {
        expect(await screenAt(url)).toBe(notFoundScreen);
        expect(session.ensured).toEqual([]);
      });
    });

    it('is not found at /nobody: it looks like a tenant but there is none, so nobody is sent to sign in', async () => {
      expect(await screenAt('/nobody/teams')).toBe(notFoundScreen);
      expect(session.ensured).toEqual([]);
    });

    it('is not found for a screen that does not exist in the tenant', async () => {
      expect(await screenAt('/acme/nothing/here')).toBe(notFoundScreen);
    });

    it('opens the page that is not found at /not-found itself', async () => {
      expect(await screenAt('/not-found')).toBe(notFoundScreen);
    });
  });
});
