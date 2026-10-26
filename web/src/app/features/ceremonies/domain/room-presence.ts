/** What Agilina says she is doing, as the agent publishes it: waiting, or unable to facilitate. */
export type AgentState = 'standby' | 'no_facilitation';

/**
 * Someone in the LiveKit room right now: their identity there, whether it is an agent (Agilina)
 * whether it is the one looking at the screen, whether their microphone is off (silenced, or
 * never turned on: a listener) and, for an agent, the state it published (`null` if none yet).
 */
export interface RoomPresence {
  readonly identity: string;
  readonly agent: boolean;
  readonly local: boolean;
  readonly muted: boolean;
  readonly agentState: AgentState | null;
}
