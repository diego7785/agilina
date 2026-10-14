import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { NEVER, of, Subject, throwError, type Observable } from 'rxjs';

import { aDashboard } from '@testing/dashboard';
import { provideTestI18n } from '@testing/i18n';
import { TestClock } from '@testing/now';
import { aTeam } from '@testing/team';
import { provideTestTenant } from '@testing/tenant';
import { provideStubUsersPort } from '@testing/users';

import { CreateTeamPage } from './create-team-page';
import { TeamDashboardPage } from './team-dashboard-page';
import { TeamSelectorPage } from './team-selector-page';
import { TeamsPort } from '../application/teams.port';
import { type Team } from '../domain/team';
import { type TeamDashboard } from '../domain/team-dashboard';

/** Port double: listMine() answers what the test chose; get() finds the team by id. */
class FakeTeamsPort extends TeamsPort {
  mine: Observable<readonly Team[]> = of([]);
  known: readonly Team[] = [];

  listMine(): Observable<readonly Team[]> {
    return this.mine;
  }

  create(): Observable<string> {
    return NEVER;
  }

  get(teamId: string): Observable<Team> {
    const team = this.known.find((candidate) => candidate.id === teamId);
    return team === undefined ? throwError(() => new Error('403')) : of(team);
  }

  dashboard(teamId: string): Observable<TeamDashboard> {
    const team = this.known.find((candidate) => candidate.id === teamId);
    return team === undefined
      ? throwError(() => new Error('403'))
      : of(
          aDashboard({
            team: { id: team.id, name: team.name, mode: team.mode, label: team.label },
          }),
        );
  }
}

describe('TeamSelectorPage', () => {
  let port: FakeTeamsPort;
  let harness: RouterTestingHarness;

  beforeEach(async () => {
    port = new FakeTeamsPort();
    TestBed.configureTestingModule({
      providers: [
        provideTestI18n(),
        provideTestTenant(),
        provideRouter(
          [
            { path: ':tenant/teams', component: TeamSelectorPage },
            { path: ':tenant/teams/new', component: CreateTeamPage },
            { path: ':tenant/teams/:teamId', component: TeamDashboardPage },
          ],
          withComponentInputBinding(),
        ),
        { provide: TeamsPort, useValue: port },
        provideStubUsersPort(),
        new TestClock('2026-10-08T12:00:00Z').provide(),
      ],
    });
    harness = await RouterTestingHarness.create();
  });

  async function open(teams: Observable<readonly Team[]>): Promise<HTMLElement> {
    port.mine = teams;
    await harness.navigateByUrl('/acme/teams');
    await harness.fixture.whenStable();
    return harness.routeNativeElement!;
  }

  function links(page: HTMLElement): { text: string; href: string | null }[] {
    return Array.from(page.querySelectorAll('ul a')).map((link) => ({
      text: link.querySelector('[data-testid=team-option-name]')?.textContent.trim() ?? '',
      href: link.getAttribute('href'),
    }));
  }

  it('shows the name of each team of the user with a link to its dashboard', async () => {
    const page = await open(of([aTeam('a', 'Atlas', 'admin'), aTeam('b', 'Boreal', 'admin')]));

    expect(page.querySelector('h1')?.textContent).toBe('Selecciona tu equipo');
    expect(links(page)).toEqual([
      { text: 'Atlas', href: '/acme/teams/a' },
      { text: 'Boreal', href: '/acme/teams/b' },
    ]);
    expect(page.textContent).not.toContain('Todavía no perteneces');
  });

  it('enters the dashboard of the team the user clicks', async () => {
    port.known = [aTeam('b', 'Boreal', 'admin')];
    const page = await open(of([aTeam('a', 'Atlas', 'admin'), aTeam('b', 'Boreal', 'admin')]));

    page.querySelectorAll<HTMLAnchorElement>('ul a')[1]!.click();
    await harness.fixture.whenStable();

    expect(TestBed.inject(Router).url).toBe('/acme/teams/b');
    expect(harness.routeNativeElement?.querySelector('h1')?.textContent.trim()).toBe('Dashboard');
    expect(harness.routeNativeElement?.querySelector('[data-testid=team-mode]')).not.toBeNull();
  });

  it('with no team shows the empty list and the button to create one', async () => {
    const page = await open(of([]));

    expect(links(page)).toEqual([]);
    expect(page.textContent).toContain('Todavía no perteneces a ningún equipo.');
    const create = page.querySelector('a[href="/acme/teams/new"]');
    expect(create?.textContent.trim()).toBe('Crear equipo nuevo');
    expect(create?.getAttribute('href')).toBe('/acme/teams/new');
  });

  it('goes straight into the only team: there is nothing to choose', async () => {
    port.known = [aTeam('a', 'Atlas', 'admin')];

    await open(of([aTeam('a', 'Atlas', 'admin')]));

    expect(TestBed.inject(Router).url).toBe('/acme/teams/a');
    expect(harness.routeNativeElement?.querySelector('h1')?.textContent.trim()).toBe('Dashboard');
  });

  it('shows the only team and the way to create another when the person asks to choose', async () => {
    port.known = [aTeam('a', 'Atlas', 'admin')];
    port.mine = of([aTeam('a', 'Atlas', 'admin')]);

    await TestBed.inject(Router).navigateByUrl('/acme/teams', { state: { choose: true } });
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement!;

    expect(TestBed.inject(Router).url).toBe('/acme/teams');
    expect(links(page)).toEqual([{ text: 'Atlas', href: '/acme/teams/a' }]);
    expect(page.querySelector('a[href="/acme/teams/new"]')?.textContent.trim()).toBe(
      'Crear equipo nuevo',
    );
  });

  it('still enters the team it is shown when the person clicks it', async () => {
    port.known = [aTeam('a', 'Atlas', 'admin')];
    port.mine = of([aTeam('a', 'Atlas', 'admin')]);
    await TestBed.inject(Router).navigateByUrl('/acme/teams', { state: { choose: true } });
    await harness.fixture.whenStable();

    harness.routeNativeElement!.querySelector<HTMLAnchorElement>('ul a')!.click();
    await harness.fixture.whenStable();

    expect(TestBed.inject(Router).url).toBe('/acme/teams/a');
  });

  it('always offers to create a team', async () => {
    const page = await open(of([aTeam('a', 'Atlas', 'admin'), aTeam('b', 'Boreal', 'member')]));

    expect(page.querySelector('a[href="/acme/teams/new"]')?.getAttribute('href')).toBe(
      '/acme/teams/new',
    );
  });

  it('takes the user to the creation form', async () => {
    const page = await open(of([]));

    page.querySelector<HTMLAnchorElement>('a[href="/acme/teams/new"]')!.click();
    await harness.fixture.whenStable();

    expect(TestBed.inject(Router).url).toBe('/acme/teams/new');
    expect(harness.routeNativeElement?.querySelector('form')).not.toBeNull();
  });

  it('shows the mode of each team and how the user is called in it', async () => {
    const page = await open(
      of([
        aTeam('a', 'Atlas', 'admin'),
        aTeam('b', 'Boreal', 'member'),
        { ...aTeam('c', 'Cielo', 'admin'), mode: 'autonomous', label: 'admin' },
      ]),
    );

    const rows = Array.from(page.querySelectorAll('ul a')).map((link) => [
      link.querySelector('[data-testid=team-mode]')?.textContent.trim(),
      link.querySelector('[data-testid=team-label]')?.textContent.trim(),
    ]);
    expect(rows).toEqual([
      ['Soporte', 'Scrum Master'],
      ['Soporte', 'Miembro'],
      ['Autónomo', 'Administrador'],
    ]);
  });

  it('says it is loading while the API has not answered', async () => {
    port.mine = new Subject<readonly Team[]>();
    // Not whenStable: the request stays pending, so the page never settles.
    await harness.navigateByUrl('/acme/teams');
    TestBed.tick();
    const page = harness.routeNativeElement!;

    expect(page.textContent).toContain('Cargando tus equipos…');
    expect(links(page)).toEqual([]);
  });

  it('shows a translated message when the teams cannot be loaded', async () => {
    const page = await open(throwError(() => new Error('503')));

    expect(page.querySelector('[role="alert"]')?.textContent).toBe(
      'No se pudieron cargar tus equipos. Inténtalo de nuevo más tarde.',
    );
    expect(page.querySelector('a[href="/acme/teams/new"]')?.getAttribute('href')).toBe(
      '/acme/teams/new',
    );
  });
});
