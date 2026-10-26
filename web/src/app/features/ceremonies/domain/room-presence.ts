/**
 * Someone in the LiveKit room right now: their identity there, whether it is an agent (Agilina)
 * whether it is the one looking at the screen, and whether their microphone is off (silenced, or
 * never turned on: a listener).
 */
export interface RoomPresence {
  readonly identity: string;
  readonly agent: boolean;
  readonly local: boolean;
  readonly muted: boolean;
}
