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

import { TeamDashboardPage } from './team-dashboard-page';
import { TeamsPort } from '../application/teams.port';
import { type Team } from '../domain/team';
import { type TeamDashboard } from '../domain/team-dashboard';
import { TeamFailure } from '../domain/team-failure';

/** The daily of `aDashboard()` starts at 14:00 UTC of 2026-10-08; its room opens at 13:50. */
const DAILY_STARTS_AT = new Date('2026-10-08T14:00:00Z');

/**
 * Port double: dashboard() answers `dashboards[teamId]`, keeps 'slow' pending and refuses the
 * rest; get() is what the top bar reads.
 */
class FakeTeamsPort extends TeamsPort {
  readonly requested: string[] = [];
  dashboards: Record<string, Observable<TeamDashboard>> = {
    atlas: of(aDashboard()),
    boreal: of(
      aDashboard({
        team: { id: 'boreal', name: 'Boreal', mode: 'support', label: 'scrum_master' },
      }),
    ),
    cielo: of(
      aDashboard({
        team: { id: 'cielo', name: 'Cielo', mode: 'support', label: 'member' },
        canConfigure: false,
      }),
    ),
  };

  listMine(): Observable<readonly Team[]> {
    return NEVER;
  }

  create(): Observable<string> {
    return NEVER;
  }

  get(teamId: string): Observable<Team> {
    return of(aTeam(teamId, teamId));
  }

  dashboard(teamId: string): Observable<TeamDashboard> {
    this.requested.push(teamId);
    if (teamId === 'slow') {
      return new Subject<TeamDashboard>();
    }
    return this.dashboards[teamId] ?? throwError(() => new TeamFailure('not_a_member'));
  }
}

describe('TeamDashboardPage', () => {
  let port: FakeTeamsPort;
  let clock: TestClock;
  let harness: RouterTestingHarness;

  beforeEach(async () => {
    port = new FakeTeamsPort();
    clock = new TestClock('2026-10-08T12:00:00Z');
    TestBed.configureTestingModule({
      providers: [
        provideTestI18n(),
        provideTestTenant(),
        provideRouter(
          [{ path: ':tenant/teams/:teamId', component: TeamDashboardPage }],
          withComponentInputBinding(),
        ),
        { provide: TeamsPort, useValue: port },
        provideStubUsersPort(),
        clock.provide(),
      ],
    });
    harness = await RouterTestingHarness.create();
  });

  async function open(url: string): Promise<HTMLElement> {
    await harness.navigateByUrl(url);
    await harness.fixture.whenStable();
    return harness.routeNativeElement!;
  }

  function text(page: HTMLElement, testId: string): string | undefined {
    return page.querySelector(`[data-testid="${testId}"]`)?.textContent.replace(/\s+/g, ' ').trim();
  }

  function joinButton(page: HTMLElement): HTMLButtonElement | null {
    return page.querySelector<HTMLButtonElement>('[data-testid="join-room"]');
  }

  /** What the browser shows for the daily, in whatever zone the tests run. */
  const localTime = new Intl.DateTimeFormat('es', { timeStyle: 'short' }).format(DAILY_STARTS_AT);
  const localDay = new Intl.DateTimeFormat('es', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(DAILY_STARTS_AT);

  describe('loading the dashboard', () => {
    it('reads the dashboard of the :teamId, in one go, and titles the screen', async () => {
      const page = await open('/acme/teams/atlas');

      expect(port.requested).toContain('atlas');
      expect(text(page, 'dashboard-title')).toBe('Dashboard');
      expect(page.textContent).toContain(
        'Las horas se muestran en la zona horaria de tu navegador.',
      );
    });

    it('loads the other team when the :teamId changes', async () => {
      await open('/acme/teams/atlas');

      const page = await open('/acme/teams/boreal');

      expect(new Set(port.requested)).toEqual(new Set(['atlas', 'boreal']));
      expect(text(page, 'team-mode')).toBe('Soporte');
    });

    it('says it is loading while the API has not answered', async () => {
      // Not whenStable: the request stays pending, so the page never settles.
      await harness.navigateByUrl('/acme/teams/slow');
      TestBed.tick();
      const page = harness.routeNativeElement!;

      expect(page.textContent).toContain('Cargando el equipo…');
      expect(text(page, 'dashboard-title')).toBeUndefined();
    });

    it('shows a translated message when the API refuses the team', async () => {
      const page = await open('/acme/teams/someone-elses');

      expect(page.querySelector('[role="alert"]')?.textContent).toBe(
        'Este equipo no existe o no perteneces a él.',
      );
      expect(text(page, 'dashboard-title')).toBeUndefined();
    });

    it('shows a generic message when the dashboard cannot be read for another reason', async () => {
      port.dashboards['atlas'] = throwError(() => new TeamFailure('unavailable'));

      const page = await open('/acme/teams/atlas');

      expect(page.querySelector('[role="alert"]')?.textContent).toBe(
        'No se pudo abrir este equipo.',
      );
    });
  });

  // ---------------------------------------------------- criteria 1 and 6: the sprint --
  describe('the sprint card', () => {
    it('shows the day N of M of the sprint in progress, as the API computed it', async () => {
      const page = await open('/acme/teams/atlas');

      expect(text(page, 'sprint-day')).toBe('Día 3 de 10');
    });

    it('draws the progress of the sprint as a bar that reads day 3 of 10', async () => {
      const page = await open('/acme/teams/atlas');

      const bar = page.querySelector<HTMLProgressElement>(
        'progress[data-testid="sprint-progress"]',
      );
      expect(bar?.value).toBe(3);
      expect(bar?.max).toBe(10);
      expect(bar?.getAttribute('aria-label')).toBe('Avance del sprint');
    });

    it('says when a sprint that has not started yet begins, with no bar', async () => {
      port.dashboards['atlas'] = of(
        aDashboard({
          sprint: {
            number: 12,
            startDate: '2026-10-05',
            endDate: '2026-10-14',
            day: { number: 0, total: 10, phase: 'not_started' },
          },
        }),
      );

      const page = await open('/acme/teams/atlas');

      expect(text(page, 'sprint-day')).toBe('El sprint empieza el 5 de octubre de 2026');
      expect(page.querySelector('progress')).toBeNull();
    });

    it('says the sprint is over once its last day has passed, with no bar', async () => {
      port.dashboards['atlas'] = of(
        aDashboard({
          sprint: {
            number: 12,
            startDate: '2026-10-05',
            endDate: '2026-10-14',
            day: { number: 10, total: 10, phase: 'finished' },
          },
          nextCeremony: null,
        }),
      );

      const page = await open('/acme/teams/atlas');

      expect(text(page, 'sprint-day')).toBe('Sprint terminado');
      expect(page.querySelector('progress')).toBeNull();
    });

    it('says the team has no active sprint when the API answers none', async () => {
      port.dashboards['atlas'] = of(aDashboard({ sprint: null, nextCeremony: null }));

      const page = await open('/acme/teams/atlas');

      expect(text(page, 'sprint-day')).toBe('Sin sprint activo');
      expect(page.querySelector('progress')).toBeNull();
      expect(page.querySelector('[data-testid="sprint-number"]')).toBeNull();
    });

    it('names the sprint with its number in the team, under the day', async () => {
      const page = await open('/acme/teams/atlas');

      expect(text(page, 'sprint-number')).toBe('Sprint 12');
      const card = page.querySelector('[data-testid="sprint-card"]')!;
      const order = Array.from(card.querySelectorAll('[data-testid]')).map((element) =>
        element.getAttribute('data-testid'),
      );
      expect(order).toEqual(['sprint-day', 'sprint-number', 'sprint-progress']);
    });

    it('keeps the number when the sprint has not started or is over', async () => {
      port.dashboards['atlas'] = of(
        aDashboard({
          sprint: {
            number: 13,
            startDate: '2026-10-05',
            endDate: '2026-10-14',
            day: { number: 0, total: 10, phase: 'not_started' },
          },
        }),
      );
      expect(text(await open('/acme/teams/atlas'), 'sprint-number')).toBe('Sprint 13');

      port.dashboards['atlas'] = of(
        aDashboard({
          sprint: {
            number: 13,
            startDate: '2026-10-05',
            endDate: '2026-10-14',
            day: { number: 10, total: 10, phase: 'finished' },
          },
          nextCeremony: null,
        }),
      );
      expect(text(await open('/acme/teams/atlas'), 'sprint-number')).toBe('Sprint 13');
    });

    it('shows the same card to a member', async () => {
      const page = await open('/acme/teams/cielo');

      expect(text(page, 'sprint-day')).toBe('Día 3 de 10');
    });
  });

  // ------------------------------------------------- criterion 2: the next ceremony --
  describe('the next ceremony card', () => {
    it('shows the daily with its time and day in the zone of the browser', async () => {
      const page = await open('/acme/teams/atlas');

      expect(text(page, 'ceremony-time')).toBe(localTime);
      expect(text(page, 'ceremony-day')).toBe(`Daily · ${localDay}`);
    });

    it('says there are no ceremonies when there is none next', async () => {
      port.dashboards['atlas'] = of(aDashboard({ nextCeremony: null }));

      const page = await open('/acme/teams/atlas');

      expect(text(page, 'ceremony-none')).toBe('No hay ceremonias programadas');
      expect(page.querySelector('[data-testid="ceremony-time"]')).toBeNull();
    });
  });

  // ----------------------------------------------------------- criterion 4: the mode --
  describe('the mode card', () => {
    it('shows the mode of the team as a read only label', async () => {
      const page = await open('/acme/teams/atlas');

      expect(text(page, 'team-mode')).toBe('Soporte');
      expect(text(page, 'mode-card')).toContain('Solo lectura');
      const card = page.querySelector('[data-testid="mode-card"]')!;
      expect(card.querySelector('button, input, select, a')).toBeNull();
    });

    it('shows the autonomous mode too', async () => {
      port.dashboards['atlas'] = of(
        aDashboard({
          team: { id: 'atlas', name: 'Atlas', mode: 'autonomous', label: 'admin' },
        }),
      );

      const page = await open('/acme/teams/atlas');

      expect(text(page, 'team-mode')).toBe('Autónomo');
    });
  });

  // ----------------------------------------- criteria 3 and 6: the room and its window --
  describe('the room', () => {
    it('is disabled before the window, and says when it opens', async () => {
      const page = await open('/acme/teams/atlas');

      const opensAt = new Intl.DateTimeFormat('es', { timeStyle: 'short' }).format(
        new Date('2026-10-08T13:50:00Z'),
      );
      expect(joinButton(page)?.disabled).toBeTrue();
      expect(text(page, 'join-hint')).toBe(`Se habilita a las ${opensAt}`);
      expect(joinButton(page)?.getAttribute('aria-describedby')).toBe('room-hint');
      expect(page.querySelector('#room-hint')).not.toBeNull();
    });

    it('is enabled inside the window, with no hint', async () => {
      clock.now = new Date('2026-10-08T13:55:00Z');

      const page = await open('/acme/teams/atlas');

      expect(joinButton(page)?.disabled).toBeFalse();
      expect(joinButton(page)?.getAttribute('aria-describedby')).toBeNull();
      expect(page.querySelector('[data-testid="join-hint"]')).toBeNull();
    });

    it('does nothing yet when the button is pressed: joining arrives with its own story', async () => {
      clock.now = new Date('2026-10-08T13:55:00Z');
      const page = await open('/acme/teams/atlas');
      const url = TestBed.inject(Router).url;

      joinButton(page)!.click();
      await harness.fixture.whenStable();

      expect(TestBed.inject(Router).url).toBe(url);
      expect(joinButton(page)).not.toBeNull();
    });

    it('is disabled, with a hint, when the sprint has no ceremony left', async () => {
      port.dashboards['atlas'] = of(aDashboard({ nextCeremony: null }));

      const page = await open('/acme/teams/atlas');

      expect(joinButton(page)?.disabled).toBeTrue();
      expect(text(page, 'join-hint')).toBe('No hay ceremonias programadas.');
    });

    it('is not offered at all without an active sprint', async () => {
      port.dashboards['atlas'] = of(aDashboard({ sprint: null, nextCeremony: null }));

      const page = await open('/acme/teams/atlas');

      expect(page.querySelector('[data-testid="room-card"]')).toBeNull();
      expect(joinButton(page)).toBeNull();
      expect(text(page, 'sprint-day')).toBe('Sin sprint activo');
    });

    it('is offered to a member like to an admin', async () => {
      const page = await open('/acme/teams/cielo');

      expect(joinButton(page)).not.toBeNull();
    });
  });

  // ---------------------------------------------- criterion 5: the settings entry --
  describe('the settings entry', () => {
    it('is not in the page: it lives in the top bar and only an admin gets it', async () => {
      const admin = await open('/acme/teams/atlas');
      expect(admin.querySelector('a[href$="/settings"]')).toBeNull();

      const member = await open('/acme/teams/cielo');
      expect(member.querySelector('a[href$="/settings"]')).toBeNull();
      expect(member.querySelectorAll('a').length).toBe(0);
    });
  });
});
