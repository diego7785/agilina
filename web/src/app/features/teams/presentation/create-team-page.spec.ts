import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { NEVER, of, Subject, type Observable } from 'rxjs';

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
import { TeamFailure } from '../domain/team-failure';

/** Port double: create() waits until the test answers; get() returns what was created. */
class FakeTeamsPort extends TeamsPort {
  pending = new Subject<string>();
  readonly names: string[] = [];
  readonly created: Team[] = [];
  readonly dashboardsRead: string[] = [];

  /** The dashboard of a team that was created: an empty one, with no sprint yet. */
  dashboard(teamId: string): Observable<TeamDashboard> {
    this.dashboardsRead.push(teamId);
    const team = this.created.find((candidate) => candidate.id === teamId);
    return team === undefined
      ? NEVER
      : of(
          aDashboard({
            team: { id: team.id, name: team.name, mode: team.mode, label: team.label },
            sprint: null,
            nextCeremony: null,
          }),
        );
  }

  listMine(): Observable<readonly Team[]> {
    return of(this.created);
  }

  create(name: string): Observable<string> {
    this.names.push(name);
    this.pending = new Subject<string>();
    return this.pending;
  }

  get(teamId: string): Observable<Team> {
    const team = this.created.find((candidate) => candidate.id === teamId);
    return team === undefined ? NEVER : of(team);
  }

  /** The API creates the team with this id. */
  accept(id: string): void {
    this.created.push(aTeam(id, this.names.at(-1)!.trim()));
    this.pending.next(id);
    this.pending.complete();
  }

  refuse(failure: Error = new Error('503')): void {
    this.pending.error(failure);
  }
}

describe('CreateTeamPage', () => {
  let port: FakeTeamsPort;
  let harness: RouterTestingHarness;
  let page: HTMLElement;

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
    harness = await RouterTestingHarness.create('/acme/teams/new');
    await harness.fixture.whenStable();
    page = harness.routeNativeElement!;
  });

  function input(): HTMLInputElement {
    return page.querySelector<HTMLInputElement>('input#team-name')!;
  }

  function saveButton(): HTMLButtonElement {
    return page.querySelector<HTMLButtonElement>('button[type="submit"]')!;
  }

  function problem(): string {
    return page.querySelector('#team-name-problem')!.textContent.trim();
  }

  async function type(name: string): Promise<void> {
    input().value = name;
    input().dispatchEvent(new Event('input'));
    await harness.fixture.whenStable();
  }

  /** Submits the form; resolves once the facade has asked the port, still unanswered. */
  async function save(): Promise<void> {
    saveButton().click();
    harness.detectChanges();
    await Promise.resolve();
  }

  /**
   * Lets the page react to the answer: the facade resolves its promise and the page
   * navigates in later microtasks that nothing registers as pending, so a macrotask
   * goes by before waiting for the router and the rendering.
   */
  async function settled(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    await harness.fixture.whenStable();
    page = harness.routeNativeElement!;
  }

  it('asks for the name of the team with a label tied to its field', () => {
    const label = page.querySelector('label');

    expect(page.querySelector('h1')?.textContent).toBe('Crear equipo');
    expect(label?.getAttribute('for')).toBe('team-name');
    expect(label?.textContent).toBe('Nombre del equipo');
    expect(input()).not.toBeNull();
    expect(page.textContent).toContain('Máximo 80 caracteres.');
  });

  it('says the team starts in support mode and English, with the user as its admin', () => {
    expect(page.textContent).toContain(
      'El equipo se creará en modo soporte y con idioma inglés. Tú quedarás como su Scrum Master.',
    );
  });

  it('does not let an empty form be saved, and shows no error before the user types', () => {
    expect(saveButton().disabled).toBeTrue();
    expect(problem()).toBe('');
    expect(input().getAttribute('aria-invalid')).toBe('false');
  });

  it('does not let a name of only spaces be saved', async () => {
    await type('    ');

    expect(saveButton().disabled).toBeTrue();
    expect(problem()).toBe('Escribe el nombre del equipo.');
    expect(input().getAttribute('aria-invalid')).toBe('true');
  });

  it('does not let a name longer than 80 characters be saved', async () => {
    await type('x'.repeat(81));

    expect(saveButton().disabled).toBeTrue();
    expect(problem()).toBe('El nombre no puede pasar de 80 caracteres.');
  });

  it('warns again when the name is erased', async () => {
    await type('Atlas');
    await type('');

    expect(saveButton().disabled).toBeTrue();
    expect(problem()).toBe('Escribe el nombre del equipo.');
  });

  it('lets a valid name be saved', async () => {
    await type('x'.repeat(80));

    expect(saveButton().disabled).toBeFalse();
    expect(problem()).toBe('');
    expect(input().getAttribute('aria-invalid')).toBe('false');
  });

  it('creates the team and enters its dashboard', async () => {
    await type('  Atlas  ');

    await save();
    port.accept('new-id');
    await settled();

    expect(port.names).toEqual(['  Atlas  ']);
    expect(TestBed.inject(Router).url).toBe('/acme/teams/new-id');
    expect(port.dashboardsRead).toContain('new-id');
    expect(page.querySelector('h1')?.textContent.trim()).toBe('Dashboard');
    expect(page.querySelector('[data-testid=sprint-day]')?.textContent.trim()).toBe(
      'Sin sprint activo',
    );
  });

  it('cannot be sent twice while it is saving', async () => {
    await type('Atlas');

    await save();

    expect(saveButton().disabled).toBeTrue();
    expect(saveButton().textContent.trim()).toBe('Creando…');
    saveButton().click();
    expect(port.names).toEqual(['Atlas']);
  });

  it('shows a translated message and stays on the form when the API fails', async () => {
    await type('Atlas');

    await save();
    port.refuse();
    await settled();

    expect(TestBed.inject(Router).url).toBe('/acme/teams/new');
    expect(page.querySelector('[role="alert"]')?.textContent).toBe(
      'No se pudo crear el equipo. Inténtalo de nuevo.',
    );
    expect(saveButton().disabled).toBeFalse();
    expect(input().value).toBe('Atlas');
  });

  it('asks to sign in again when the API does not recognize the session', async () => {
    await type('Atlas');

    await save();
    port.refuse(new TeamFailure('not_authenticated'));
    await settled();

    expect(TestBed.inject(Router).url).toBe('/acme/teams/new');
    expect(page.querySelector('[role="alert"]')?.textContent).toBe(
      'Tu sesión no es válida o expiró. Inicia sesión de nuevo.',
    );
  });

  it('goes back to the team selector on cancel', async () => {
    page.querySelector<HTMLAnchorElement>('a[href="/acme/teams"]')!.click();
    await settled();

    expect(TestBed.inject(Router).url).toBe('/acme/teams');
    expect(port.names).toEqual([]);
  });
});
