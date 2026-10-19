import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, map, type Observable, throwError } from 'rxjs';

import { RUNTIME_CONFIG } from '@core/config/runtime-config';
import { readApiError } from '@core/http/api-error';

import { type RoomAccessPort } from '../application/room-access.port';
import { type RoomAccess } from '../domain/room-access';
import { RoomFailure, type RoomFailureKind } from '../domain/room-failure';

/**
 * Body of the 201 answer of POST /v1/teams/{team_id}/dailies/current/token, as AGI-59 proposes
 * it. That story is still being built: if its contract changes, only this file changes.
 */
interface RoomTokenResponse {
  room_name: string;
  token: string;
  expires_at: string;
  livekit_url: string;
}

const FAILURES: Readonly<Record<string, RoomFailureKind>> = {
  not_a_team_member: 'no_access',
  not_a_daily_participant: 'no_access',
  no_active_sprint: 'no_active_sprint',
  room_service_unavailable: 'service_unavailable',
};

/** HTTP adapter of the room access port: the API issues the token, never the client. */
@Injectable()
export class HttpRoomAccessApi implements RoomAccessPort {
  private readonly http = inject(HttpClient);
  private readonly teamsUrl = `${inject(RUNTIME_CONFIG).apiUrl}/v1/teams`;

  requestAccess(teamId: string): Observable<RoomAccess> {
    return this.http
      .post<RoomTokenResponse>(
        `${this.teamsUrl}/${encodeURIComponent(teamId)}/dailies/current/token`,
        null,
      )
      .pipe(map(toAccess), catchError(failWithDomainError));
  }
}

/** The API contract stays in this file; the rest of the app sees the domain model. */
function toAccess(response: RoomTokenResponse): RoomAccess {
  return {
    roomName: response.room_name,
    token: response.token,
    expiresAt: response.expires_at,
    serverUrl: response.livekit_url,
  };
}

/** The API's error codes stay in this file: the rest of the app only sees `RoomFailure`. */
function failWithDomainError(error: unknown): Observable<never> {
  return throwError(() => toFailure(error));
}

function toFailure(error: unknown): RoomFailure {
  if (!(error instanceof HttpErrorResponse)) {
    return new RoomFailure('unexpected');
  }
  const body = readApiError(error.error);
  return new RoomFailure((body !== undefined ? FAILURES[body.code] : undefined) ?? 'unexpected');
}
