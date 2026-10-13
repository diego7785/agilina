import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { provideTestRuntimeConfig, TEST_RUNTIME_CONFIG } from '@testing/runtime-config';

import { HttpTeamsApi } from './http-teams.api';
import { type Team } from '../domain/team';
import { type TeamDashboard } from '../domain/team-dashboard';
import { TeamFailure } from '../domain/team-failure';

describe('HttpTeamsApi', () => {
  const teamsUrl = `${TEST_RUNTIME_CONFIG.apiUrl}/v1/teams`;
  let api: HttpTeamsApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        HttpTeamsApi,
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTestRuntimeConfig(),
      ],
    });
    api = TestBed.inject(HttpTeamsApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
  });

  it('lists the teams of the user and keeps their id, name, role, mode and label', () => {
    let received: readonly Team[] | undefined;
    api.listMine().subscribe((teams) => (received = teams));

    const request = backend.expectOne(teamsUrl);
    expect(request.request.method).toBe('GET');
    request.flush([
      { id: 'a', name: 'Atlas', role: 'admin', mode: 'support', label: 'scrum_master' },
      { id: 'b', name: 'Boreal', role: 'member', mode: 'autonomous', label: 'member' },
      { id: 'c', name: 'Cielo', role: 'admin', mode: 'autonomous', label: 'admin' },
    ]);

    expect(received).toEqual([
      { id: 'a', name: 'Atlas', role: 'admin', mode: 'support', label: 'scrum_master' },
      { id: 'b', name: 'Boreal', role: 'member', mode: 'autonomous', label: 'member' },
      { id: 'c', name: 'Cielo', role: 'admin', mode: 'autonomous', label: 'admin' },
    ]);
  });

  it('reads a mode or a label it does not know as support and member', () => {
    let received: readonly Team[] | undefined;
    api.listMine().subscribe((teams) => (received = teams));

    backend
      .expectOne(teamsUrl)
      .flush([{ id: 'a', name: 'Atlas', role: 'admin', mode: 'hybrid', label: 'product_owner' }]);

    expect(received).toEqual([
      { id: 'a', name: 'Atlas', role: 'admin', mode: 'support', label: 'member' },
    ]);
  });

  it('creates a team sending only its name and emits the new id', () => {
    let created: string | undefined;
    api.create('  Atlas  ').subscribe((id) => (created = id));

    const request = backend.expectOne(teamsUrl);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ name: '  Atlas  ' });
    request.flush({ id: 'new-id' }, { status: 201, statusText: 'Created' });

    expect(created).toBe('new-id');
  });

  it('reads one team and maps it to the domain', () => {
    let received: Team | undefined;
    api.get('team-1').subscribe((team) => (received = team));

    const request = backend.expectOne(`${teamsUrl}/team-1`);
    expect(request.request.method).toBe('GET');
    request.flush({
      id: 'team-1',
      name: 'Atlas',
      mode: 'autonomous',
      language: 'en',
      role: 'admin',
      label: 'admin',
    });

    expect(received).toEqual({
      id: 'team-1',
      name: 'Atlas',
      role: 'admin',
      mode: 'autonomous',
      label: 'admin',
    });
  });

  it('escapes the team id in the path', () => {
    api.get('a/b').subscribe();

    backend.expectOne(`${teamsUrl}/a%2Fb`).flush({ id: 'a/b', name: 'Atlas' });
  });

  it('turns the error codes of the API into team failures', () => {
    const failures: unknown[] = [];
    const keep = (error: unknown): void => {
      failures.push(error);
    };

    api.get('someone-elses').subscribe({ error: keep });
    backend
      .expectOne(`${teamsUrl}/someone-elses`)
      .flush({ error: { code: 'not_a_team_member' } }, { status: 403, statusText: 'Forbidden' });
    api.create(' ').subscribe({ error: keep });
    backend
      .expectOne(teamsUrl)
      .flush(
        { error: { code: 'invalid_team_name' } },
        { status: 422, statusText: 'Unprocessable' },
      );
    api.listMine().subscribe({ error: keep });
    backend
      .expectOne(teamsUrl)
      .flush({ error: { code: 'not_authenticated' } }, { status: 401, statusText: 'Unauthorized' });

    expect(failures).toEqual([
      new TeamFailure('not_a_member'),
      new TeamFailure('invalid_name'),
      new TeamFailure('not_authenticated'),
    ]);
  });

  it('treats an answer without a known code as the service being unavailable', () => {
    let failure: unknown;
    api.listMine().subscribe({ error: (error: unknown) => (failure = error) });

    backend.expectOne(teamsUrl).flush('Bad gateway', { status: 502, statusText: 'Bad Gateway' });

    expect(failure).toEqual(new TeamFailure('unavailable'));
  });
  describe('dashboard', () => {
    const body = {
      team: { id: 'atlas', name: 'Atlas', mode: 'support', label: 'scrum_master' },
      sprint: {
        number: 12,
        start_date: '2026-10-05',
        end_date: '2026-10-16',
        day: { number: 3, total: 12, phase: 'in_progress' },
      },
      next_ceremony: {
        type: 'daily',
        starts_at: '2026-10-08T14:00:00Z',
        join_opens_at: '2026-10-08T13:50:00Z',
      },
      can_configure: true,
    };

    it('reads the whole dashboard of a team with a single GET', () => {
      let received: TeamDashboard | undefined;
      api.dashboard('atlas').subscribe((dashboard) => (received = dashboard));

      const request = backend.expectOne(`${teamsUrl}/atlas/dashboard`);
      expect(request.request.method).toBe('GET');
      request.flush(body);

      expect(received).toEqual({
        team: { id: 'atlas', name: 'Atlas', mode: 'support', label: 'scrum_master' },
        sprint: {
          number: 12,
          startDate: '2026-10-05',
          endDate: '2026-10-16',
          day: { number: 3, total: 12, phase: 'in_progress' },
        },
        nextCeremony: {
          type: 'daily',
          startsAt: '2026-10-08T14:00:00Z',
          joinOpensAt: '2026-10-08T13:50:00Z',
        },
        canConfigure: true,
      });
    });

    it('keeps a team without sprint and without ceremony as nulls', () => {
      let received: TeamDashboard | undefined;
      api.dashboard('atlas').subscribe((dashboard) => (received = dashboard));

      backend.expectOne(`${teamsUrl}/atlas/dashboard`).flush({
        ...body,
        sprint: null,
        next_ceremony: null,
        can_configure: false,
      });

      expect(received?.sprint).toBeNull();
      expect(received?.nextCeremony).toBeNull();
      expect(received?.canConfigure).toBeFalse();
    });

    it('reads a mode or a label it does not know as the most careful one', () => {
      let received: TeamDashboard | undefined;
      api.dashboard('atlas').subscribe((dashboard) => (received = dashboard));

      backend.expectOne(`${teamsUrl}/atlas/dashboard`).flush({
        ...body,
        team: { id: 'atlas', name: 'Atlas', mode: 'new_mode', label: 'new_label' },
      });

      expect(received?.team.mode).toBe('support');
      expect(received?.team.label).toBe('member');
    });

    it('turns the refusal of a non-member into the not-a-member failure', () => {
      let failure: unknown;
      api.dashboard('atlas').subscribe({ error: (error: unknown) => (failure = error) });

      backend
        .expectOne(`${teamsUrl}/atlas/dashboard`)
        .flush(
          { error: { status: 403, code: 'not_a_team_member', message: 'x', request_id: 'r' } },
          { status: 403, statusText: 'Forbidden' },
        );

      expect(failure).toEqual(new TeamFailure('not_a_member'));
    });

    it('turns anything else into the unavailable failure', () => {
      let failure: unknown;
      api.dashboard('atlas').subscribe({ error: (error: unknown) => (failure = error) });

      backend
        .expectOne(`${teamsUrl}/atlas/dashboard`)
        .flush('boom', { status: 500, statusText: 'Server Error' });

      expect(failure).toEqual(new TeamFailure('unavailable'));
    });
  });
});
