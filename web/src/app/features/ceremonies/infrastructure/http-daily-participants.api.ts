import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, map, type Observable, throwError } from 'rxjs';

import { RUNTIME_CONFIG } from '@core/config/runtime-config';

import { type DailyParticipantsPort } from '../application/daily-participants.port';
import { type DailyParticipant } from '../domain/daily-participant';
import { RoomFailure } from '../domain/room-failure';

/**
 * Body of the 200 answer of GET /v1/teams/{team_id}/dailies/current/participants. The API
 * contract stays in this file: if it changes, only this file changes.
 */
interface DailyParticipantsResponse {
  participants: DailyParticipantResponse[];
}

interface DailyParticipantResponse {
  room_identity: string;
  full_name: string;
  email: string;
}

/** HTTP adapter of the daily participants port. */
@Injectable()
export class HttpDailyParticipantsApi implements DailyParticipantsPort {
  private readonly http = inject(HttpClient);
  private readonly teamsUrl = `${inject(RUNTIME_CONFIG).apiUrl}/v1/teams`;

  participantsOf(teamId: string): Observable<readonly DailyParticipant[]> {
    return this.http
      .get<DailyParticipantsResponse>(
        `${this.teamsUrl}/${encodeURIComponent(teamId)}/dailies/current/participants`,
      )
      .pipe(
        map((response) => response.participants.map(toDailyParticipant)),
        // httpErrorLoggingInterceptor already logs the failure; the provider's error stays here.
        catchError(() => throwError(() => new RoomFailure('unexpected'))),
      );
  }
}

/** The API contract stays in this file; the rest of the app sees the domain model. */
function toDailyParticipant(response: DailyParticipantResponse): DailyParticipant {
  return {
    identity: response.room_identity,
    fullName: response.full_name,
    email: response.email,
  };
}
