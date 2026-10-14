import { ApplicationRef, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { NEVER, of, Subject, throwError, type Observable } from 'rxjs';

import { BROWSER_TIME_ZONE } from '@core/time/browser-time-zone';

import { SprintSettingsFacade } from './sprint-settings.facade';
import { SprintsPort } from './sprints.port';
import { UsersPort } from './users.port';
import { type ActiveSprint } from '../domain/active-sprint';
import { MemberFailure } from '../domain/member-failure';
import { type SprintDraft, type SprintFields } from '../domain/sprint-draft';
import { SprintFailure } from '../domain/sprint-failure';
import { type TeamMember, type TeamMembers } from '../domain/team-member';

const ANA: TeamMember = {
  userId: 'ana',
  fullName: 'Ana Gil',
  email: 'ana@example.com',
  role: 'admin',
  label: 'admin',
  joinedAt: new Date('2026-10-08T15:04:05Z'),
  roleChangeBlockedBy: null,
  removalBlockedBy: null,
};
const BRUNO: TeamMember = { ...ANA, userId: 'bruno', fullName: 'Bruno Díaz', role: 'member' };
const MEMBERS: TeamMembers = { roles: [], members: [ANA, BRUNO] };

const SPRINT: ActiveSprint = {
  id: 'sprint-1',
  number: 12,
  startDate: '2026-10-05',
  endDate: '2026-10-16',
  dailyTime: '2026-10-05T14:00:00Z',
  timeZone: 'America/Bogota',
  nextDailyAt: '2026-10-08T14:00:00Z',
  participants: ['bruno', 'ana'],
  day: { number: 3, total: 12, phase: 'in_progress' },
};

const FIELDS: SprintFields = {
  startDate: '2026-10-19',
  endDate: '2026-10-30',
  dailyTime: '09:30',
  participants: ['ana', 'bruno'],
};

/**
 * Sprints port double: active() answers what `current` holds for the team (a failure, or
 * nothing yet for 'slow'); start() and reconfigure() wait until the test answers them.
 */
class FakeSprintsPort extends SprintsPort {
  current: ActiveSprint | null | SprintFailure = SPRINT;
  readonly read: string[] = [];
  readonly started: [string, SprintDraft][] = [];
  readonly reconfigured: [string, SprintDraft][] = [];
  private pending = new Subject<ActiveSprint>();

  active(teamId: string): Observable<ActiveSprint | null> {
    this.read.push(teamId);
    if (teamId === 'slow') {
      return NEVER;
    }
    const current = this.current;
    return current instanceof SprintFailure ? throwError(() => current) : of(current);
  }

  start(teamId: string, draft: SprintDraft): Observable<ActiveSprint> {
    this.started.push([teamId, draft]);
    return this.command();
  }

  reconfigure(teamId: string, draft: SprintDraft): Observable<ActiveSprint> {
    this.reconfigured.push([teamId, draft]);
    return this.command();
  }

  accept(sprint: ActiveSprint): void {
    this.pending.next(sprint);
    this.pending.complete();
  }

  refuse(failure: Error): void {
    this.pending.error(failure);
  }

  private command(): Observable<ActiveSprint> {
    this.pending = new Subject<ActiveSprint>();
    return this.pending;
  }
}

/** Members port double: list() answers `answer`; nothing else is used by this facade. */
class FakeUsersPort extends UsersPort {
  answer: TeamMembers | MemberFailure = MEMBERS;
  readonly listed: string[] = [];

  list(teamId: string): Observable<TeamMembers> {
    this.listed.push(teamId);
    if (teamId === 'slow') {
      return NEVER;
    }
    const answer = this.answer;
    return answer instanceof MemberFailure ? throwError(() => answer) : of(answer);
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

describe('SprintSettingsFacade', () => {
  let sprints: FakeSprintsPort;
  let members: FakeUsersPort;
  let facade: SprintSettingsFacade;

  beforeEach(() => {
    sprints = new FakeSprintsPort();
    members = new FakeUsersPort();
    TestBed.configureTestingModule({
      providers: [
        SprintSettingsFacade,
        { provide: SprintsPort, useValue: sprints },
        { provide: UsersPort, useValue: members },
        { provide: BROWSER_TIME_ZONE, useValue: 'America/Bogota' },
      ],
    });
    facade = TestBed.inject(SprintSettingsFacade);
  });

  async function stable(): Promise<void> {
    await TestBed.inject(ApplicationRef).whenStable();
  }

  async function following(teamId = 'atlas'): Promise<void> {
    facade.follow(signal(teamId));
    await stable();
  }

  it('asks for nothing until it knows which team to follow', async () => {
    await stable();

    expect(sprints.read).toEqual([]);
    expect(members.listed).toEqual([]);
    expect(facade.sprint()).toBeUndefined();
    expect(facade.members()).toBeNull();
    expect(facade.ready()).toBeFalse();
  });

  it('loads the active sprint and the members of the team it follows', async () => {
    await following();

    expect(sprints.read).toEqual(['atlas']);
    expect(members.listed).toEqual(['atlas']);
    expect(facade.sprint()).toEqual(SPRINT);
    expect(facade.members()).toEqual([ANA, BRUNO]);
    expect(facade.ready()).toBeTrue();
    expect(facade.loading()).toBeFalse();
    expect(facade.problem()).toBeNull();
  });

  it('is ready with no sprint when the team has none', async () => {
    sprints.current = null;
    await following();

    expect(facade.sprint()).toBeNull();
    expect(facade.ready()).toBeTrue();
  });

  it('is loading, and not ready, while the API has not answered', () => {
    facade.follow(signal('slow'));
    TestBed.tick();

    expect(facade.loading()).toBeTrue();
    expect(facade.ready()).toBeFalse();
  });

  it('loads them again when the team id changes', async () => {
    const teamId = signal('atlas');
    facade.follow(teamId);
    await stable();

    teamId.set('boreal');
    await stable();

    expect(sprints.read).toEqual(['atlas', 'boreal']);
    expect(members.listed).toEqual(['atlas', 'boreal']);
  });

  it('offers the time zone of the browser as the one the daily is saved with', () => {
    expect(facade.timeZone).toBe('America/Bogota');
  });

  it('turns a refused list of members into the problem of the screen', async () => {
    members.answer = new MemberFailure('forbidden');
    await following();

    expect(facade.problem()).toBe('forbidden');
    expect(facade.ready()).toBeFalse();
  });

  it('turns a refused sprint into the problem of the screen', async () => {
    sprints.current = new SprintFailure('not_authenticated');
    await following();

    expect(facade.problem()).toBe('not_authenticated');
    expect(facade.ready()).toBeFalse();
  });

  it('turns an unexpected failure into "unavailable"', async () => {
    members.answer = new MemberFailure('unavailable');
    await following();

    expect(facade.problem()).toBe('unavailable');
  });

  it('creates the sprint when the team has none, with the daily in UTC and the browser zone', async () => {
    sprints.current = null;
    await following();

    const saving = facade.save(FIELDS);
    expect(facade.saving()).toBeTrue();
    const created: ActiveSprint = { ...SPRINT, id: 'sprint-2', startDate: '2026-10-19' };
    sprints.accept(created);

    expect(await saving).toBeTrue();
    expect(sprints.reconfigured).toEqual([]);
    expect(sprints.started).toEqual([
      [
        'atlas',
        {
          startDate: '2026-10-19',
          endDate: '2026-10-30',
          dailyTime: new Date(2026, 9, 19, 9, 30).toISOString(),
          timeZone: 'America/Bogota',
          participants: ['ana', 'bruno'],
        },
      ],
    ]);
    expect(facade.saving()).toBeFalse();
    expect(facade.saved()).toBeTrue();
    expect(facade.saveProblem()).toBeNull();
    // The answer of the API replaces the sprint shown: it is no longer "no sprint".
    expect(facade.sprint()).toEqual(created);
  });

  it('edits the active sprint when the team has one, and shows what the API answered', async () => {
    await following();

    const saving = facade.save(FIELDS);
    const edited: ActiveSprint = {
      ...SPRINT,
      participants: ['ana', 'bruno'],
      day: { number: 0, total: 12, phase: 'not_started' },
    };
    sprints.accept(edited);

    expect(await saving).toBeTrue();
    expect(sprints.started).toEqual([]);
    expect(sprints.reconfigured.map(([teamId]) => teamId)).toEqual(['atlas']);
    expect(sprints.reconfigured[0]?.[1].timeZone).toBe('America/Bogota');
    expect(facade.sprint()).toEqual(edited);
    expect(sprints.read).toEqual(['atlas']);
  });

  it('turns a refusal into a problem the screen translates, keeping the sprint shown', async () => {
    await following();

    const saving = facade.save({ ...FIELDS, endDate: '2026-10-01' });
    sprints.refuse(new SprintFailure('ends_before_start'));

    expect(await saving).toBeFalse();
    expect(facade.saveProblem()).toBe('ends_before_start');
    expect(facade.saved()).toBeFalse();
    expect(facade.saving()).toBeFalse();
    expect(facade.sprint()).toEqual(SPRINT);
    expect(sprints.read).toEqual(['atlas']);
  });

  it('turns an unexpected failure while saving into "unavailable"', async () => {
    await following();

    const saving = facade.save(FIELDS);
    sprints.refuse(new Error('boom'));

    expect(await saving).toBeFalse();
    expect(facade.saveProblem()).toBe('unavailable');
  });

  it('reads the sprint again when someone else created it meanwhile, so the next save edits it', async () => {
    sprints.current = null;
    await following();

    const saving = facade.save(FIELDS);
    sprints.current = SPRINT;
    sprints.refuse(new SprintFailure('active_sprint_exists'));
    expect(await saving).toBeFalse();
    await stable();

    expect(facade.saveProblem()).toBe('active_sprint_exists');
    expect(sprints.read).toEqual(['atlas', 'atlas']);
    expect(facade.sprint()).toEqual(SPRINT);

    void facade.save(FIELDS);
    expect(sprints.reconfigured.length).toBe(1);
  });

  it('reads the sprint again when it stopped being active meanwhile, so the next save creates it', async () => {
    await following();

    const saving = facade.save(FIELDS);
    sprints.current = null;
    sprints.refuse(new SprintFailure('no_active_sprint'));
    expect(await saving).toBeFalse();
    await stable();

    expect(sprints.read).toEqual(['atlas', 'atlas']);
    expect(facade.sprint()).toBeNull();

    void facade.save(FIELDS);
    expect(sprints.started.length).toBe(1);
  });

  it('clears the problem of the last save when saving again', async () => {
    await following();
    const first = facade.save(FIELDS);
    sprints.refuse(new SprintFailure('no_participants'));
    await first;

    const second = facade.save(FIELDS);
    expect(facade.saveProblem()).toBeNull();
    sprints.accept(SPRINT);

    expect(await second).toBeTrue();
    expect(facade.saveProblem()).toBeNull();
  });

  it('does not save twice at the same time', async () => {
    await following();

    void facade.save(FIELDS);
    expect(await facade.save(FIELDS)).toBeFalse();

    expect(sprints.reconfigured.length).toBe(1);
  });

  it('does not save before it knows the team and its sprint', async () => {
    expect(await facade.save(FIELDS)).toBeFalse();

    facade.follow(signal('slow'));
    TestBed.tick();
    expect(await facade.save(FIELDS)).toBeFalse();

    expect(sprints.started).toEqual([]);
    expect(sprints.reconfigured).toEqual([]);
  });
});
