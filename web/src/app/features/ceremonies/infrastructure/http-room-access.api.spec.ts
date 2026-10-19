import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { provideTestRuntimeConfig, TEST_RUNTIME_CONFIG } from '@testing/runtime-config';

import { HttpRoomAccessApi } from './http-room-access.api';
import { type RoomAccess } from '../domain/room-access';
import { RoomFailure } from '../domain/room-failure';

describe('HttpRoomAccessApi', () => {
  const tokenUrl = `${TEST_RUNTIME_CONFIG.apiUrl}/v1/teams/atlas/dailies/current/token`;
  let api: HttpRoomAccessApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        HttpRoomAccessApi,
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTestRuntimeConfig(),
      ],
    });
    api = TestBed.inject(HttpRoomAccessApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
  });

  it('asks for the token of the daily of today with a POST without body', () => {
    let received: RoomAccess | undefined;
    api.requestAccess('atlas').subscribe((access) => (received = access));

    const request = backend.expectOne(tokenUrl);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toBeNull();
    request.flush(
      {
        room_name: 'acme-3f2c9a1e-8d4b-4c7a-9e21-5b6f0d1a2c3e',
        token: 'eyJhbGciOi',
        expires_at: '2026-10-08T16:00:00Z',
        livekit_url: 'wss://agilina.livekit.cloud',
      },
      { status: 201, statusText: 'Created' },
    );

    expect(received).toEqual({
      roomName: 'acme-3f2c9a1e-8d4b-4c7a-9e21-5b6f0d1a2c3e',
      token: 'eyJhbGciOi',
      expiresAt: '2026-10-08T16:00:00Z',
      serverUrl: 'wss://agilina.livekit.cloud',
    });
  });

  it('encodes the team id in the address', () => {
    api.requestAccess('a/b').subscribe();

    backend.expectOne(`${TEST_RUNTIME_CONFIG.apiUrl}/v1/teams/a%2Fb/dailies/current/token`).flush({
      room_name: 'r',
      token: 't',
      expires_at: '2026-10-08T16:00:00Z',
      livekit_url: 'wss://x',
    });
  });

  const failures: readonly [number, string, string][] = [
    [403, 'not_a_team_member', 'no_access'],
    [403, 'not_a_daily_participant', 'no_access'],
    [409, 'no_active_sprint', 'no_active_sprint'],
    [503, 'room_service_unavailable', 'service_unavailable'],
    [500, 'internal_error', 'unexpected'],
    [422, 'validation_error', 'unexpected'],
    [400, 'tenant_required', 'unexpected'],
  ];
  for (const [status, code, kind] of failures) {
    it(`translates ${status} ${code} into ${kind}`, () => {
      let failure: unknown;
      api.requestAccess('atlas').subscribe({ error: (error: unknown) => (failure = error) });

      backend
        .expectOne(tokenUrl)
        .flush(
          { error: { status, code, message: 'x', request_id: 'r1' } },
          { status, statusText: 'Error' },
        );

      expect(failure).toEqual(new RoomFailure(kind as RoomFailure['kind']));
    });
  }

  it('reads an answer that is not the API error as unexpected', () => {
    let failure: unknown;
    api.requestAccess('atlas').subscribe({ error: (error: unknown) => (failure = error) });

    backend.expectOne(tokenUrl).error(new ProgressEvent('error'));

    expect(failure).toEqual(new RoomFailure('unexpected'));
  });
});
