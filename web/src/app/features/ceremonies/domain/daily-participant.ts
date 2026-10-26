/** A person invited to the team's daily in progress, in turn order, as the API lists them. */
export interface DailyParticipant {
  /** Their identity in the LiveKit room. */
  readonly identity: string;
  readonly fullName: string;
  readonly email: string;
}
