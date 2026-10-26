import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { provideTestRuntimeConfig, TEST_RUNTIME_CONFIG } from '@testing/runtime-config';

import { HttpDailyParticipantsApi } from './http-daily-participants.api';
import { type DailyParticipant } from '../domain/daily-participant';
import { RoomFailure } from '../domain/room-failure';

describe('HttpDailyParticipantsApi', () => {
  const participantsUrl = `${TEST_RUNTIME_CONFIG.apiUrl}/v1/teams/atlas/dailies/current/participants`;
  let api: HttpDailyParticipantsApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        HttpDailyParticipantsApi,
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTestRuntimeConfig(),
      ],
    });
    api = TestBed.inject(HttpDailyParticipantsApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
  });

  it('asks for the invited of the daily in progress and keeps their turn order', () => {
    let received: readonly DailyParticipant[] | undefined;
    api.participantsOf('atlas').subscribe((participants) => (received = participants));

    const request = backend.expectOne(participantsUrl);
    expect(request.request.method).toBe('GET');
    request.flush({
      participants: [
        { room_identity: 'user-luis', full_name: 'Luis Mora', email: 'luis@example.test' },
        { room_identity: 'user-eva', full_name: 'Eva Prueba', email: 'eva@example.test' },
      ],
    });

    expect(received).toEqual([
      { identity: 'user-luis', fullName: 'Luis Mora', email: 'luis@example.test' },
      { identity: 'user-eva', fullName: 'Eva Prueba', email: 'eva@example.test' },
    ]);
  });

  it('encodes the team id in the address', () => {
    api.participantsOf('a/b').subscribe();

    backend
      .expectOne(`${TEST_RUNTIME_CONFIG.apiUrl}/v1/teams/a%2Fb/dailies/current/participants`)
      .flush({ participants: [] });
  });

  for (const [status, code] of [
    [403, 'not_a_daily_participant'],
    [409, 'no_active_sprint'],
    [500, 'internal_error'],
  ] as const) {
    it(`fails on ${status} ${code} with the port's error`, () => {
      let failure: unknown;
      api.participantsOf('atlas').subscribe({ error: (error: unknown) => (failure = error) });

      backend
        .expectOne(participantsUrl)
        .flush(
          { error: { status, code, message: 'eva@example.test', request_id: 'r1' } },
          { status, statusText: 'Error' },
        );

      expect(failure).toEqual(new RoomFailure('unexpected'));
    });
  }

  it('fails when the API does not answer', () => {
    let failure: unknown;
    api.participantsOf('atlas').subscribe({ error: (error: unknown) => (failure = error) });

    backend.expectOne(participantsUrl).error(new ProgressEvent('error'));

    expect(failure).toEqual(new RoomFailure('unexpected'));
  });
});
