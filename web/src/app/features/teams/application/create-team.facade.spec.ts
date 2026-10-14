import { TestBed } from '@angular/core/testing';
import { NEVER, Subject, type Observable } from 'rxjs';

import { CreateTeamFacade } from './create-team.facade';
import { TeamsPort } from './teams.port';
import { type Team } from '../domain/team';
import { TeamFailure } from '../domain/team-failure';

/** Port double: each create() waits until the test answers it. */
class FakeTeamsPort extends TeamsPort {
  dashboard(): Observable<never> {
    return NEVER;
  }

  pending = new Subject<string>();
  readonly names: string[] = [];

  listMine(): Observable<readonly Team[]> {
    return NEVER;
  }

  create(name: string): Observable<string> {
    this.names.push(name);
    this.pending = new Subject<string>();
    return this.pending;
  }

  get(): Observable<Team> {
    return NEVER;
  }
}

describe('CreateTeamFacade', () => {
  let port: FakeTeamsPort;
  let facade: CreateTeamFacade;

  beforeEach(() => {
    port = new FakeTeamsPort();
    TestBed.configureTestingModule({
      providers: [CreateTeamFacade, { provide: TeamsPort, useValue: port }],
    });
    facade = TestBed.inject(CreateTeamFacade);
  });

  function answer(id: string): void {
    port.pending.next(id);
    port.pending.complete();
  }

  it('creates the team with the name and resolves to its id', async () => {
    const created = facade.create('Atlas');
    answer('new-id');

    expect(await created).toBe('new-id');
    expect(port.names).toEqual(['Atlas']);
    expect(facade.failed()).toBeFalse();
  });

  it('is saving until the API answers', async () => {
    expect(facade.saving()).toBeFalse();

    const created = facade.create('Atlas');
    expect(facade.saving()).toBeTrue();

    answer('new-id');
    await created;
    expect(facade.saving()).toBeFalse();
  });

  it('resolves to null and marks the failure when the API refuses it', async () => {
    const created = facade.create('Atlas');
    port.pending.error(new TeamFailure('invalid_name'));

    expect(await created).toBeNull();
    expect(facade.failed()).toBeTrue();
    expect(facade.problem()).toBe('invalid_name');
    expect(facade.saving()).toBeFalse();
  });

  it('forgets the last failure when trying again', async () => {
    const refused = facade.create('Atlas');
    port.pending.error(new Error('503'));
    await refused;

    const retried = facade.create('Atlas');
    expect(facade.failed()).toBeFalse();
    answer('new-id');

    expect(await retried).toBe('new-id');
    expect(facade.failed()).toBeFalse();
  });
});
