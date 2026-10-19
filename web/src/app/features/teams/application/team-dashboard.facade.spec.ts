import { ApplicationRef, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { NEVER, of, throwError, type Observable } from 'rxjs';

import { aDashboard } from '@testing/dashboard';
import { TestClock } from '@testing/now';

import { TeamDashboardFacade } from './team-dashboard.facade';
import { TeamsPort } from './teams.port';
import { type Team } from '../domain/team';
import { type TeamDashboard } from '../domain/team-dashboard';
import { TeamFailure } from '../domain/team-failure';

/** Port double: dashboard() answers what the test chose for each team id. */
class FakeTeamsPort extends TeamsPort {
  readonly requested: string[] = [];
  readonly answers: Record<string, Observable<TeamDashboard>> = {
    atlas: of(aDashboard()),
    boreal: of(
      aDashboard({ team: { id: 'boreal', name: 'Boreal', mode: 'autonomous', label: 'admin' } }),
    ),
  };

  listMine(): Observable<readonly Team[]> {
    return NEVER;
  }

  create(): Observable<string> {
    return NEVER;
  }

  get(): Observable<Team> {
    return NEVER;
  }

  dashboard(teamId: string): Observable<TeamDashboard> {
    this.requested.push(teamId);
    return this.answers[teamId] ?? throwError(() => new TeamFailure('not_a_member'));
  }
}

describe('TeamDashboardFacade', () => {
  let port: FakeTeamsPort;
  let clock: TestClock;
  let facade: TeamDashboardFacade;

  /** The daily of `aDashboard()` starts at 14:00 UTC; its room opens at 13:50 and closes at 14:15. */
  function start(now: string): void {
    port = new FakeTeamsPort();
    clock = new TestClock(now);
    TestBed.configureTestingModule({
      providers: [TeamDashboardFacade, { provide: TeamsPort, useValue: port }, clock.provide()],
    });
    facade = TestBed.inject(TeamDashboardFacade);
  }

  async function stable(): Promise<void> {
    await TestBed.inject(ApplicationRef).whenStable();
  }

  describe('reading', () => {
    beforeEach(() => {
      start('2026-10-08T12:00:00Z');
    });

    it('asks for nothing until it knows which team to follow', async () => {
      await stable();

      expect(port.requested).toEqual([]);
      expect(facade.team()).toBeNull();
      expect(facade.known()).toBeFalse();
      expect(facade.failed()).toBeFalse();
    });

    it('loads the dashboard of the id it receives, in a single read', async () => {
      facade.follow(signal('atlas'));
      await stable();

      expect(port.requested).toEqual(['atlas']);
      expect(facade.team()?.name).toBe('Atlas');
      expect(facade.sprint()?.day).toEqual({ number: 3, total: 10, phase: 'in_progress' });
      expect(facade.nextCeremony()?.startsAt).toBe('2026-10-08T14:00:00Z');
      expect(facade.canConfigure()).toBeTrue();
      expect(facade.known()).toBeTrue();
      expect(facade.loading()).toBeFalse();
    });

    it('loads the dashboard again when the id changes', async () => {
      const teamId = signal('atlas');
      facade.follow(teamId);
      await stable();

      teamId.set('boreal');
      await stable();

      expect(port.requested).toEqual(['atlas', 'boreal']);
      expect(facade.team()?.name).toBe('Boreal');
    });

    it('has no sprint and no ceremony when the team has none, and does not configure for a member', async () => {
      port.answers['atlas'] = of(
        aDashboard({ sprint: null, nextCeremony: null, canConfigure: false }),
      );
      facade.follow(signal('atlas'));
      await stable();

      expect(facade.known()).toBeTrue();
      expect(facade.sprint()).toBeNull();
      expect(facade.nextCeremony()).toBeNull();
      expect(facade.canConfigure()).toBeFalse();
      expect(facade.joinState()).toBe('none');
    });

    it('turns a refused team into the failed state with its problem', async () => {
      facade.follow(signal('someone-elses'));
      await stable();

      expect(facade.failed()).toBeTrue();
      expect(facade.problem()).toBe('not_a_member');
      expect(facade.team()).toBeNull();
    });

    it('says there is no problem while the team opens', async () => {
      facade.follow(signal('atlas'));
      await stable();

      expect(facade.problem()).toBeNull();
    });

    it('tells the room is not yet open before the window', async () => {
      facade.follow(signal('atlas'));
      await stable();

      expect(facade.joinState()).toBe('not_yet');
    });
  });

  describe('the window to join', () => {
    beforeEach(() => {
      jasmine.clock().install();
    });

    afterEach(() => {
      jasmine.clock().uninstall();
    });

    /** Lets the resource and the effects run with the mocked timers. */
    async function settle(): Promise<void> {
      for (let round = 0; round < 5; round++) {
        TestBed.tick();
        jasmine.clock().tick(0);
        await Promise.resolve();
      }
    }

    it('opens the room by itself when the window starts', async () => {
      start('2026-10-08T13:49:00Z');
      facade.follow(signal('atlas'));
      await settle();
      expect(facade.joinState()).toBe('not_yet');

      clock.now = new Date('2026-10-08T13:50:00Z');
      jasmine.clock().tick(60_000);
      await settle();

      expect(facade.joinState()).toBe('open');
    });

    it('keeps the room joinable for whoever arrives late once the ceremony starts', async () => {
      start('2026-10-08T13:59:00Z');
      facade.follow(signal('atlas'));
      await settle();
      expect(facade.joinState()).toBe('open');

      clock.now = new Date('2026-10-08T14:00:00Z');
      jasmine.clock().tick(60_000);
      await settle();

      expect(facade.joinState()).toBe('started');
      expect(facade.canJoin()).toBeTrue();
      expect(port.requested).toEqual(['atlas']);
    });

    it('asks for the next ceremony by itself when the window to join closes', async () => {
      start('2026-10-08T14:14:00Z');
      facade.follow(signal('atlas'));
      await settle();
      expect(facade.joinState()).toBe('started');
      expect(port.requested).toEqual(['atlas']);
      port.answers['atlas'] = of(
        aDashboard({
          nextCeremony: {
            type: 'daily',
            startsAt: '2026-10-09T14:00:00Z',
            joinOpensAt: '2026-10-09T13:50:00Z',
            joinClosesAt: '2026-10-09T14:15:00Z',
          },
        }),
      );

      clock.now = new Date('2026-10-08T14:15:00Z');
      jasmine.clock().tick(60_000);
      await settle();

      expect(port.requested).toEqual(['atlas', 'atlas']);
      expect(facade.nextCeremony()?.startsAt).toBe('2026-10-09T14:00:00Z');
      expect(facade.joinState()).toBe('not_yet');
    });

    it('sets no timer when the team has no ceremony', async () => {
      start('2026-10-08T13:00:00Z');
      port.answers['atlas'] = of(aDashboard({ sprint: null, nextCeremony: null }));
      facade.follow(signal('atlas'));
      await settle();

      jasmine.clock().tick(24 * 60 * 60 * 1000);
      await settle();

      expect(port.requested).toEqual(['atlas']);
    });

    it('stops its timer when it is destroyed', async () => {
      start('2026-10-08T13:59:00Z');
      facade.follow(signal('atlas'));
      await settle();

      TestBed.resetTestingModule();
      clock.now = new Date('2026-10-08T14:00:00Z');
      jasmine.clock().tick(60_000);

      expect(port.requested).toEqual(['atlas']);
    });
  });
});
