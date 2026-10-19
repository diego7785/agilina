import { type Observable } from 'rxjs';

import { type RoomAccess } from '../domain/room-access';

/**
 * Port towards the API that issues the token of a room (AGI-59). An abstract class so that it
 * doubles as the injection token; the HTTP adapter is bound in app.config.ts.
 */
export abstract class RoomAccessPort {
  /**
   * A new access to the room of the team's daily of today. It fails with a `RoomFailure` when
   * the person may not enter or the room service does not answer.
   */
  abstract requestAccess(teamId: string): Observable<RoomAccess>;
}
