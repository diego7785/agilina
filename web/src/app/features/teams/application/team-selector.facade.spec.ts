import { ApplicationRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { NEVER, of, throwError, type Observable } from 'rxjs';

import { aTeam } from '@testing/team';

import { TeamSelectorFacade } from './team-selector.facade';
import { TeamsPort } from './teams.port';
import { type Team } from '../domain/team';
import { TeamFailure } from '../domain/team-failure';

/** Port double: listMine() answers what the test chose. */
class FakeTeamsPort extends TeamsPort {
  dashboard(): Observable<never> {
    return NEVER;
  }

  mine: Observable<readonly Team[]> = of([]);

  listMine(): Observable<readonly Team[]> {
    return this.mine;
  }

  create(): Observable<string> {
    return NEVER;
  }

  get(): Observable<Team> {
    return NEVER;
  }
}

describe('TeamSelectorFacade', () => {
  let port: FakeTeamsPort;

  beforeEach(() => {
    port = new FakeTeamsPort();
    TestBed.configureTestingModule({
      providers: [TeamSelectorFacade, { provide: TeamsPort, useValue: port }],
    });
  });

  async function settled(): Promise<TeamSelectorFacade> {
    const facade = TestBed.inject(TeamSelectorFacade);
    await TestBed.inject(ApplicationRef).whenStable();
    return facade;
  }

  it('exposes the teams of the user once the API answers', async () => {
    port.mine = of([aTeam('a', 'Atlas', 'admin'), aTeam('b', 'Boreal', 'admin')]);

    const facade = await settled();

    expect(facade.teams()).toEqual([aTeam('a', 'Atlas', 'admin'), aTeam('b', 'Boreal', 'admin')]);
    expect(facade.loading()).toBeFalse();
    expect(facade.failed()).toBeFalse();
  });

  it('tells an empty list apart from a list that has not arrived', () => {
    port.mine = NEVER;
    const waiting = TestBed.inject(TeamSelectorFacade);
    TestBed.tick();

    expect(waiting.teams()).toBeNull();
    expect(waiting.loading()).toBeTrue();
  });

  it('exposes an empty list when the user has no team', async () => {
    port.mine = of([]);

    const facade = await settled();

    expect(facade.teams()).toEqual([]);
  });

  it('turns a failed request into the failed state', async () => {
    port.mine = throwError(() => new Error('403'));

    const facade = await settled();

    expect(facade.failed()).toBeTrue();
    expect(facade.problem()).toBe('unavailable');
    expect(facade.teams()).toBeNull();
    expect(facade.loading()).toBeFalse();
  });

  it('says when the user is not signed in', async () => {
    port.mine = throwError(() => new TeamFailure('not_authenticated'));

    const facade = await settled();

    expect(facade.problem()).toBe('not_authenticated');
  });
});
