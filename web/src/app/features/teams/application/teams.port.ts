import { type Observable } from 'rxjs';

import { type Team } from '../domain/team';
import { type TeamDashboard } from '../domain/team-dashboard';

/**
 * Port towards the teams of the API. An abstract class so that it doubles as the
 * injection token; the HTTP adapter is bound in app.config.ts.
 */
export abstract class TeamsPort {
  /** The teams the signed-in user belongs to. */
  abstract listMine(): Observable<readonly Team[]>;

  /** Creates a team with the signed-in user as its admin and emits the new team's id. */
  abstract create(name: string): Observable<string>;

  /** One team of the signed-in user; the API refuses a team the user does not belong to. */
  abstract get(teamId: string): Observable<Team>;

  /** Everything the dashboard of a team shows, in one read; the API refuses a non-member. */
  abstract dashboard(teamId: string): Observable<TeamDashboard>;
}
