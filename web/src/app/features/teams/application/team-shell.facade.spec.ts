import { Component, inject, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { NEVER, type Observable, of, throwError } from 'rxjs';

import { ShellContext } from '@core/shell/shell-context';
import { aTeam } from '@testing/team';

import { TeamShellFacade } from './team-shell.facade';
import { TeamsPort } from './teams.port';
import { UsersPort } from './users.port';
import { MemberFailure } from '../domain/member-failure';
import { type Team } from '../domain/team';
import { type MyMembership } from '../domain/team-member';

class FakeTeamsPort extends TeamsPort {
  dashboard(): Observable<never> {
    return NEVER;
  }

  failing = false;

  listMine(): Observable<readonly Team[]> {
    return NEVER;
  }

  create(): Observable<string> {
    return NEVER;
  }

  get(teamId: string): Observable<Team> {
    return this.failing ? throwError(() => new Error('x')) : of(aTeam(teamId, `Team ${teamId}`));
  }
}

class FakeUsersPort extends UsersPort {
  label: MyMembership['label'] = 'scrum_master';
  failing = false;
  readonly asked: string[] = [];

  list(): Observable<never> {
    return NEVER;
  }

  get(): Observable<never> {
    return NEVER;
  }

  me(teamId: string): Observable<MyMembership> {
    this.asked.push(teamId);
    return this.failing
      ? throwError(() => new MemberFailure('forbidden'))
      : of({
          userId: 'ana',
          fullName: 'Ana Gil',
          email: 'ana@example.com',
          role: 'admin',
          label: this.label,
          joinedAt: new Date('2026-10-08T15:04:05Z'),
        });
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

/** A screen that provides the facade and follows a team, as the team pages do. */
@Component({ template: '', providers: [TeamShellFacade] })
class Screen {
  constructor() {
    inject(TeamShellFacade).follow(signal('atlas'));
  }
}

describe('TeamShellFacade', () => {
  let teams: FakeTeamsPort;
  let users: FakeUsersPort;
  let shell: ShellContext;

  beforeEach(() => {
    teams = new FakeTeamsPort();
    users = new FakeUsersPort();
    TestBed.configureTestingModule({
      providers: [
        TeamShellFacade,
        { provide: TeamsPort, useValue: teams },
        { provide: UsersPort, useValue: users },
      ],
    });
    shell = TestBed.inject(ShellContext);
  });

  function follow(id: string): ReturnType<typeof signal<string>> {
    const teamId = signal(id);
    TestBed.inject(TeamShellFacade).follow(teamId);
    TestBed.tick();
    return teamId;
  }

  it('puts the name of the team and my label in it in the top bar', () => {
    follow('atlas');

    expect(shell.team()).toEqual({
      id: 'atlas',
      name: 'Team atlas',
      roleLabel: 'scrum_master',
      userName: 'Ana Gil',
      canConfigure: true,
    });
    expect(users.asked).toEqual(['atlas']);
  });

  it('uses the label the API gives, not one of its own', () => {
    users.label = 'admin';

    follow('nova');

    expect(shell.team()?.roleLabel).toBe('admin');
  });

  it('says nothing about the team when it cannot be read', () => {
    teams.failing = true;

    follow('atlas');

    expect(shell.team()).toBeNull();
  });

  it('says nothing about the team when I cannot be read in it', () => {
    users.failing = true;

    follow('atlas');

    expect(shell.team()).toBeNull();
  });

  it('follows the team when the id changes', () => {
    const teamId = follow('atlas');

    teamId.set('boreal');
    TestBed.tick();

    expect(shell.team()?.name).toBe('Team boreal');
  });

  it('shows the label the API gives after a refresh: my own role may have changed', () => {
    follow('atlas');
    expect(shell.team()?.roleLabel).toBe('scrum_master');

    users.label = 'member';
    TestBed.inject(TeamShellFacade).refresh();
    TestBed.tick();

    expect(shell.team()?.roleLabel).toBe('member');
    expect(users.asked).toEqual(['atlas', 'atlas']);
  });

  it('stops naming the team when, after a refresh, I am no longer in it', () => {
    follow('atlas');

    users.failing = true;
    TestBed.inject(TeamShellFacade).refresh();
    TestBed.tick();

    expect(shell.team()).toBeNull();
  });

  it('takes the team out of the bar when its screen goes away', () => {
    const screen = TestBed.createComponent(Screen);
    screen.detectChanges();
    TestBed.tick();
    expect(shell.team()?.name).toBe('Team atlas');

    screen.destroy();
    TestBed.tick();

    expect(shell.team()).toBeNull();
  });
});
