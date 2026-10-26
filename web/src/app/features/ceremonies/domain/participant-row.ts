/**
 * A person of the daily as the room lists them: who they are, whether they are in the room now
 * and whether it is the one looking at the screen. Agilina is not a row: the room shows her apart.
 */
export interface ParticipantRow {
  /** Their identity in the LiveKit room, which tells the rows apart. */
  readonly identity: string;
  /** Empty when the room does not know them: in the room, but not invited to the daily. */
  readonly name: string;
  readonly email: string | null;
  readonly connected: boolean;
  readonly self: boolean;
}
