import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { provideTestRuntimeConfig, TEST_RUNTIME_CONFIG } from '@testing/runtime-config';

import { HttpSprintsApi } from './http-sprints.api';
import { type ActiveSprint } from '../domain/active-sprint';
import { type SprintDraft } from '../domain/sprint-draft';
import { SprintFailure, type SprintFailureKind } from '../domain/sprint-failure';

/** The active sprint exactly as the API sends it (docs/api.md, section Sprint). */
const RESPONSE = {
  id: 'sprint-1',
  number: 12,
  start_date: '2026-10-05',
  end_date: '2026-10-16',
  daily_time: '2026-10-05T14:00:00Z',
  time_zone: 'America/Bogota',
  next_daily_at: '2026-10-08T14:00:00Z',
  // Out of order on purpose: the turn is turn_order, not the position in the array.
  participants: [
    { user_id: 'carla', turn_order: 3 },
    { user_id: 'ana', turn_order: 1 },
    { user_id: 'bruno', turn_order: 2 },
  ],
  day: { number: 3, total: 12, phase: 'in_progress' },
};
const SPRINT: ActiveSprint = {
  id: 'sprint-1',
  number: 12,
  startDate: '2026-10-05',
  endDate: '2026-10-16',
  dailyTime: '2026-10-05T14:00:00Z',
  timeZone: 'America/Bogota',
  nextDailyAt: '2026-10-08T14:00:00Z',
  participants: ['ana', 'bruno', 'carla'],
  day: { number: 3, total: 12, phase: 'in_progress' },
};
const DRAFT: SprintDraft = {
  startDate: '2026-10-05',
  endDate: '2026-10-16',
  dailyTime: '2026-10-05T14:00:00.000Z',
  timeZone: 'America/Bogota',
  participants: ['bruno', 'ana'],
};
const REQUEST = {
  start_date: '2026-10-05',
  end_date: '2026-10-16',
  daily_time: '2026-10-05T14:00:00.000Z',
  time_zone: 'America/Bogota',
  participants: ['bruno', 'ana'],
};

describe('HttpSprintsApi', () => {
  const sprintsUrl = `${TEST_RUNTIME_CONFIG.apiUrl}/v1/teams/atlas/sprints`;
  let api: HttpSprintsApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        HttpSprintsApi,
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTestRuntimeConfig(),
      ],
    });
    api = TestBed.inject(HttpSprintsApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
  });

  it('reads the active sprint and maps it to the domain, participants in turn order', () => {
    let received: ActiveSprint | null | undefined;
    api.active('atlas').subscribe((sprint) => (received = sprint));

    const request = backend.expectOne(`${sprintsUrl}/active`);
    expect(request.request.method).toBe('GET');
    request.flush(RESPONSE);

    expect(received).toEqual(SPRINT);
  });

  it('reads that the team has no active sprint: 200 with null is not a failure', () => {
    let received: ActiveSprint | null | undefined;
    api.active('atlas').subscribe((sprint) => (received = sprint));

    backend.expectOne(`${sprintsUrl}/active`).flush(null);

    expect(received).toBeNull();
  });

  it('maps a sprint with no daily left and the other phases', () => {
    let received: ActiveSprint | null | undefined;
    api.active('atlas').subscribe((sprint) => (received = sprint));

    backend.expectOne(`${sprintsUrl}/active`).flush({
      ...RESPONSE,
      next_daily_at: null,
      day: { number: 12, total: 12, phase: 'finished' },
    });

    expect(received?.nextDailyAt).toBeNull();
    expect(received?.day).toEqual({ number: 12, total: 12, phase: 'finished' });
  });

  it('creates the sprint with POST and the body in snake_case, and emits the active sprint', () => {
    let received: ActiveSprint | undefined;
    api.start('atlas', DRAFT).subscribe((sprint) => (received = sprint));

    const request = backend.expectOne(sprintsUrl);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(REQUEST);
    request.flush(RESPONSE, { status: 201, statusText: 'Created' });

    expect(received).toEqual(SPRINT);
  });

  it('edits the active sprint with PUT and the same body, and emits the active sprint', () => {
    let received: ActiveSprint | undefined;
    api.reconfigure('atlas', DRAFT).subscribe((sprint) => (received = sprint));

    const request = backend.expectOne(`${sprintsUrl}/active`);
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual(REQUEST);
    request.flush(RESPONSE);

    expect(received).toEqual(SPRINT);
  });

  it('escapes the team id in the path', () => {
    api.active('a/b').subscribe();

    const request = backend.expectOne(
      `${TEST_RUNTIME_CONFIG.apiUrl}/v1/teams/a%2Fb/sprints/active`,
    );
    expect(request.request.method).toBe('GET');
    request.flush(null);
  });

  const codes: [string, number, SprintFailureKind][] = [
    ['not_authenticated', 401, 'not_authenticated'],
    ['not_a_team_member', 403, 'forbidden'],
    ['not_a_team_admin', 403, 'forbidden'],
    ['no_active_sprint', 409, 'no_active_sprint'],
    ['active_sprint_exists', 409, 'active_sprint_exists'],
    ['sprint_ends_before_start', 422, 'ends_before_start'],
    ['invalid_time_zone', 422, 'invalid_time_zone'],
    ['no_daily_participants', 422, 'no_participants'],
    ['duplicate_daily_participant', 422, 'duplicate_participant'],
    ['daily_participant_not_a_member', 422, 'participant_not_a_member'],
    ['validation_error', 422, 'unavailable'],
    ['team_not_found', 404, 'unavailable'],
    ['something_new', 500, 'unavailable'],
  ];

  codes.forEach(([code, status, kind]) => {
    it(`translates ${status} ${code} into the failure "${kind}"`, () => {
      let failure: unknown;
      api.reconfigure('atlas', DRAFT).subscribe({ error: (error: unknown) => (failure = error) });

      backend
        .expectOne(`${sprintsUrl}/active`)
        .flush(
          { error: { status, code, message: 'for developers', request_id: 'r-1' } },
          { status, statusText: 'Error' },
        );

      expect(failure).toEqual(jasmine.any(SprintFailure));
      expect((failure as SprintFailure).kind).toBe(kind);
    });
  });

  it('translates the refusals of creating and reading too', () => {
    const failures: unknown[] = [];
    api.start('atlas', DRAFT).subscribe({ error: (error: unknown) => failures.push(error) });
    api.active('atlas').subscribe({ error: (error: unknown) => failures.push(error) });

    backend
      .expectOne(sprintsUrl)
      .flush(
        { error: { status: 409, code: 'active_sprint_exists', message: '', request_id: 'r-1' } },
        { status: 409, statusText: 'Conflict' },
      );
    backend
      .expectOne(`${sprintsUrl}/active`)
      .flush(
        { error: { status: 403, code: 'not_a_team_member', message: '', request_id: 'r-2' } },
        { status: 403, statusText: 'Forbidden' },
      );

    expect(failures.map((failure) => (failure as SprintFailure).kind)).toEqual([
      'active_sprint_exists',
      'forbidden',
    ]);
  });

  it('treats an answer that is not the API error body as unavailable', () => {
    let failure: unknown;
    api.active('atlas').subscribe({ error: (error: unknown) => (failure = error) });

    backend
      .expectOne(`${sprintsUrl}/active`)
      .flush('<html>Bad gateway</html>', { status: 502, statusText: 'Bad Gateway' });

    expect((failure as SprintFailure).kind).toBe('unavailable');
  });

  it('treats a network failure as unavailable', () => {
    let failure: unknown;
    api.active('atlas').subscribe({ error: (error: unknown) => (failure = error) });

    backend.expectOne(`${sprintsUrl}/active`).error(new ProgressEvent('error'));

    expect((failure as SprintFailure).kind).toBe('unavailable');
  });

  it('treats an answer it cannot map as unavailable', () => {
    let failure: unknown;
    api.active('atlas').subscribe({ error: (error: unknown) => (failure = error) });

    // A body without `participants` makes the mapping throw: that is not an HTTP error.
    backend.expectOne(`${sprintsUrl}/active`).flush({ id: 'sprint-1' });

    expect(failure).toEqual(jasmine.any(SprintFailure));
    expect((failure as SprintFailure).kind).toBe('unavailable');
  });
});
