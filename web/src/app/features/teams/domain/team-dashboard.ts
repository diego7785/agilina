import { type SprintDay } from './active-sprint';
import { type TeamMode } from './team';
import { type RoleLabel } from './team-member';

/** The team as the dashboard shows it: how Agilina works in it and how the user is called in it. */
export interface DashboardTeam {
  readonly id: string;
  readonly name: string;
  readonly mode: TeamMode;
  readonly label: RoleLabel;
}

/** The sprint of the team as the dashboard shows it: its period and where today falls in it. */
export interface DashboardSprint {
  /** The sprint's number in its team (the 12 of "Sprint 12"), assigned by the API. */
  readonly number: number;
  /** First day of the sprint, `YYYY-MM-DD`. */
  readonly startDate: string;
  /** Last day of the sprint, included, `YYYY-MM-DD`. */
  readonly endDate: string;
  readonly day: SprintDay;
}

/**
 * The next ceremony and the instant from which the room opens to its participants, both in UTC
 * (ISO 8601). The window to join goes from `joinOpensAt` to `startsAt`.
 */
export interface NextCeremony {
  readonly type: 'daily';
  readonly startsAt: string;
  readonly joinOpensAt: string;
}

/**
 * Everything the dashboard of a team shows, read in one go. `canConfigure` only decides whether
 * the interface draws the settings entry: the API checks the permission on every settings route.
 */
export interface TeamDashboard {
  readonly team: DashboardTeam;
  /** Null when the team has no active sprint. */
  readonly sprint: DashboardSprint | null;
  /** Null when there is no active sprint or its last daily has already started. */
  readonly nextCeremony: NextCeremony | null;
  readonly canConfigure: boolean;
}
