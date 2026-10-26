/**
 * Someone in the LiveKit room right now: their identity there, whether it is an agent (Agilina)
 * and whether it is the one looking at the screen.
 */
export interface RoomPresence {
  readonly identity: string;
  readonly agent: boolean;
  readonly local: boolean;
}
