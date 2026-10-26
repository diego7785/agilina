import { type Observable } from 'rxjs';

import { type DailyParticipant } from '../domain/daily-participant';

/**
 * Port towards the API that lists who is invited to the team's daily in progress (AGI-61). An
 * abstract class so that it doubles as the injection token; the HTTP adapter is bound in
 * app.config.ts.
 */
export abstract class DailyParticipantsPort {
  /** The invited, in turn order. Only an invited person may ask; anyone else gets a failure. */
  abstract participantsOf(teamId: string): Observable<readonly DailyParticipant[]>;
}
