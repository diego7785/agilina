import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, map, type Observable, throwError } from 'rxjs';

import { RUNTIME_CONFIG } from '@core/config/runtime-config';
import { readApiError } from '@core/http/api-error';

import { toRoleLabel } from './role-label';
import { toTeamRole } from './team-role';
import { type TeamsPort } from '../application/teams.port';
import { type SprintPhase } from '../domain/active-sprint';
import { type Team, type TeamMode } from '../domain/team';
import { type TeamDashboard } from '../domain/team-dashboard';
import { TeamFailure, type TeamFailureKind } from '../domain/team-failure';

/** Item of GET /v1/teams, exactly as the API sends it. */
interface MyTeamResponse {
  id: string;
  name: string;
  role: string;
  mode: string;
  label: string;
}

/** Body of POST /v1/teams. */
interface CreateTeamRequest {
  name: string;
}

/** Body of the 201 answer of POST /v1/teams. */
interface CreatedTeamResponse {
  id: string;
}

/** Body of GET /v1/teams/{team_id}. */
interface TeamResponse {
  id: string;
  name: string;
  mode: string;
  language: string;
  role: string;
  label: string;
}

/** Body of GET /v1/teams/{team_id}/dashboard. */
interface TeamDashboardResponse {
  team: { id: string; name: string; mode: string; label: string };
  sprint: {
    number: number;
    start_date: string;
    end_date: string;
    day: { number: number; total: number; phase: SprintPhase };
  } | null;
  next_ceremony: {
    type: 'daily';
    starts_at: string;
    join_opens_at: string;
    join_closes_at: string;
  } | null;
  can_configure: boolean;
}

const FAILURES: Readonly<Record<string, TeamFailureKind>> = {
  not_authenticated: 'not_authenticated',
  invalid_team_name: 'invalid_name',
  not_a_team_member: 'not_a_member',
};

/** HTTP adapter of the teams port: the only exit of this feature towards the API. */
@Injectable()
export class HttpTeamsApi implements TeamsPort {
  private readonly http = inject(HttpClient);
  private readonly teamsUrl = `${inject(RUNTIME_CONFIG).apiUrl}/v1/teams`;

  listMine(): Observable<readonly Team[]> {
    return this.http.get<MyTeamResponse[]>(this.teamsUrl).pipe(
      map((teams) => teams.map(toTeam)),
      catchError(failWithDomainError),
    );
  }

  create(name: string): Observable<string> {
    const body: CreateTeamRequest = { name };
    return this.http.post<CreatedTeamResponse>(this.teamsUrl, body).pipe(
      map((created) => created.id),
      catchError(failWithDomainError),
    );
  }

  get(teamId: string): Observable<Team> {
    return this.http
      .get<TeamResponse>(`${this.teamsUrl}/${encodeURIComponent(teamId)}`)
      .pipe(map(toTeam), catchError(failWithDomainError));
  }

  dashboard(teamId: string): Observable<TeamDashboard> {
    return this.http
      .get<TeamDashboardResponse>(`${this.teamsUrl}/${encodeURIComponent(teamId)}/dashboard`)
      .pipe(map(toDashboard), catchError(failWithDomainError));
  }
}

/**
 * The API contract stays in this file; the rest of the app sees the domain model.
 * The language is not shown yet, so it does not reach the domain.
 */
function toTeam(response: MyTeamResponse | TeamResponse): Team {
  return {
    id: response.id,
    name: response.name,
    role: toTeamRole(response.role),
    label: toRoleLabel(response.label),
    mode: toTeamMode(response.mode),
  };
}

/** The API contract stays in this file; the rest of the app sees the domain model. */
function toDashboard(response: TeamDashboardResponse): TeamDashboard {
  return {
    team: {
      id: response.team.id,
      name: response.team.name,
      mode: toTeamMode(response.team.mode),
      label: toRoleLabel(response.team.label),
    },
    sprint:
      response.sprint === null
        ? null
        : {
            number: response.sprint.number,
            startDate: response.sprint.start_date,
            endDate: response.sprint.end_date,
            day: response.sprint.day,
          },
    nextCeremony:
      response.next_ceremony === null
        ? null
        : {
            type: response.next_ceremony.type,
            startsAt: response.next_ceremony.starts_at,
            joinOpensAt: response.next_ceremony.join_opens_at,
            joinClosesAt: response.next_ceremony.join_closes_at,
          },
    canConfigure: response.can_configure,
  };
}

/** A mode this app does not know reads as the one where a human is still in charge. */
function toTeamMode(mode: string): TeamMode {
  return mode === 'autonomous' ? 'autonomous' : 'support';
}

/** The API's error codes stay in this file: the rest of the app only sees `TeamFailure`. */
function failWithDomainError(error: unknown): Observable<never> {
  return throwError(() => toFailure(error));
}

function toFailure(error: unknown): TeamFailure {
  if (!(error instanceof HttpErrorResponse)) {
    return new TeamFailure('unavailable');
  }
  const body = readApiError(error.error);
  return new TeamFailure((body !== undefined ? FAILURES[body.code] : undefined) ?? 'unavailable');
}
