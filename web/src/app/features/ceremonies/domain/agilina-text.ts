import { type RoomPresence } from './room-presence';

/**
 * What Agilina could not say out loud and left in writing, as an agent in the room published it;
 * `null` while her voice works or she is not there.
 */
export function agilinaTextOf(present: readonly RoomPresence[]): string | null {
  return (
    present.find((presence) => presence.agent && presence.agentText !== null)?.agentText ?? null
  );
}
