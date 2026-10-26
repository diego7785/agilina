import { type DailyParticipant } from './daily-participant';
import { type ParticipantRow } from './participant-row';
import { type RoomPresence } from './room-presence';

/**
 * The list of the room: first the invited, in turn order, connected or not; then whoever else is
 * in the room, with no name the room knows. Agents (Agilina) are never a row. A row speaks when
 * its identity is among `speaking` and it is in the room.
 */
export function participantRows(
  invitees: readonly DailyParticipant[],
  present: readonly RoomPresence[],
  speaking: readonly string[],
): ParticipantRow[] {
  const people = new Map(
    present.filter((presence) => !presence.agent).map((presence) => [presence.identity, presence]),
  );
  const invited = invitees.map((invitee): ParticipantRow => {
    const presence = people.get(invitee.identity);
    people.delete(invitee.identity);
    return {
      identity: invitee.identity,
      name: invitee.fullName,
      email: invitee.email,
      connected: presence !== undefined,
      muted: presence?.muted ?? false,
      speaking: presence !== undefined && speaking.includes(invitee.identity),
      self: presence?.local ?? false,
    };
  });
  const others = [...people.values()].map((presence): ParticipantRow => ({
    identity: presence.identity,
    name: '',
    email: null,
    connected: true,
    muted: presence.muted,
    speaking: speaking.includes(presence.identity),
    self: presence.local,
  }));
  return [...invited, ...others];
}
