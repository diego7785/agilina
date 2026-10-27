import { type AgentState, type RoomPresence } from './room-presence';

/** How long Agilina has, once the participant is in the room, to arrive and tell her state. */
export const AGILINA_ARRIVAL_BUDGET_MS = 30_000;

/** What the card «Estado de Agilina» says. */
export type AgilinaStatus = 'arriving' | AgentState | 'unavailable';

/**
 * The status of Agilina: the state an agent in the room published wins, even if it came late;
 * without one she is still arriving until the budget runs out, and unavailable after it.
 */
export function agilinaStatusOf(
  present: readonly RoomPresence[],
  arrivalExpired: boolean,
): AgilinaStatus {
  const state = present.find((presence) => presence.agent && presence.agentState !== null);
  return state?.agentState ?? (arrivalExpired ? 'unavailable' : 'arriving');
}
