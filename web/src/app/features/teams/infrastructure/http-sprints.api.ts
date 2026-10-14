import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, map, type Observable, throwError } from 'rxjs';

import { RUNTIME_CONFIG } from '@core/config/runtime-config';
import { readApiError } from '@core/http/api-error';

import { type SprintsPort } from '../application/sprints.port';
import { type ActiveSprint, type SprintPhase } from '../domain/active-sprint';
import { type SprintDraft } from '../domain/sprint-draft';
import { SprintFailure, type SprintFailureKind } from '../domain/sprint-failure';

/**
 * Body of the answer of GET and PUT /v1/teams/{team_id}/sprints/active and of POST
 * /v1/teams/{team_id}/sprints, exactly as the API sends it.
 */
interface ActiveSprintResponse {
  id: string;
  number: number;
  start_date: string;
  end_date: string;
  daily_time: string;
  time_zone: string;
  next_daily_at: string | null;
  participants: DailyParticipantResponse[];
  day: SprintDayResponse;
}

interface DailyParticipantResponse {
  user_id: string;
  turn_order: number;
}

interface SprintDayResponse {
  number: number;
  total: number;
  phase: SprintPhase;
}

/** Body of POST /v1/teams/{team_id}/sprints and of PUT /v1/teams/{team_id}/sprints/active. */
interface SprintRequest {
  start_date: string;
  end_date: string;
  daily_time: string;
  time_zone: string;
  participants: string[];
}

const FAILURES: Readonly<Record<string, SprintFailureKind>> = {
  not_authenticated: 'not_authenticated',
  // Someone else's team and a team where the user is not an admin read the same: no access.
  not_a_team_member: 'forbidden',
  not_a_team_admin: 'forbidden',
  no_active_sprint: 'no_active_sprint',
  active_sprint_exists: 'active_sprint_exists',
  sprint_ends_before_start: 'ends_before_start',
  invalid_time_zone: 'invalid_time_zone',
  no_daily_participants: 'no_participants',
  duplicate_daily_participant: 'duplicate_participant',
  daily_participant_not_a_member: 'participant_not_a_member',
};

/** HTTP adapter of the sprints port: read, create and edit the active sprint of a team. */
@Injectable()
export class HttpSprintsApi implements SprintsPort {
  private readonly http = inject(HttpClient);
  private readonly teamsUrl = `${inject(RUNTIME_CONFIG).apiUrl}/v1/teams`;

  active(teamId: string): Observable<ActiveSprint | null> {
    return this.http.get<ActiveSprintResponse | null>(this.activeUrl(teamId)).pipe(
      map((response) => (response === null ? null : toActiveSprint(response))),
      catchError(failWithDomainError),
    );
  }

  start(teamId: string, draft: SprintDraft): Observable<ActiveSprint> {
    return this.http
      .post<ActiveSprintResponse>(this.sprintsUrl(teamId), toRequest(draft))
      .pipe(map(toActiveSprint), catchError(failWithDomainError));
  }

  reconfigure(teamId: string, draft: SprintDraft): Observable<ActiveSprint> {
    return this.http
      .put<ActiveSprintResponse>(this.activeUrl(teamId), toRequest(draft))
      .pipe(map(toActiveSprint), catchError(failWithDomainError));
  }

  private sprintsUrl(teamId: string): string {
    return `${this.teamsUrl}/${encodeURIComponent(teamId)}/sprints`;
  }

  private activeUrl(teamId: string): string {
    return `${this.sprintsUrl(teamId)}/active`;
  }
}

/** The API contract stays in this file; the rest of the app sees the domain model. */
function toRequest(draft: SprintDraft): SprintRequest {
  return {
    start_date: draft.startDate,
    end_date: draft.endDate,
    daily_time: draft.dailyTime,
    time_zone: draft.timeZone,
    participants: [...draft.participants],
  };
}

/** The participants come in turn order; sorting by it keeps that order whatever arrives. */
function toActiveSprint(response: ActiveSprintResponse): ActiveSprint {
  return {
    id: response.id,
    number: response.number,
    startDate: response.start_date,
    endDate: response.end_date,
    dailyTime: response.daily_time,
    timeZone: response.time_zone,
    nextDailyAt: response.next_daily_at,
    participants: [...response.participants]
      .sort((first, second) => first.turn_order - second.turn_order)
      .map((participant) => participant.user_id),
    day: {
      number: response.day.number,
      total: response.day.total,
      phase: response.day.phase,
    },
  };
}

/** The API's error codes stay in this file: the rest of the app only sees `SprintFailure`. */
function failWithDomainError(error: unknown): Observable<never> {
  return throwError(() => toFailure(error));
}

function toFailure(error: unknown): SprintFailure {
  if (!(error instanceof HttpErrorResponse)) {
    return new SprintFailure('unavailable');
  }
  const body = readApiError(error.error);
  return new SprintFailure((body !== undefined ? FAILURES[body.code] : undefined) ?? 'unavailable');
}
