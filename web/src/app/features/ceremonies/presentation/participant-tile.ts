import { Component, computed, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { initialsOf } from '@shared/utils/initials';

import { type ParticipantRow } from '../domain/participant-row';

/**
 * One person in the list of the room: their initials, name and email, «· you» on the one looking
 * at the screen, and whether they are connected. A disconnected person is dimmed and the row
 * also says so in words; the email and the label keep their contrast.
 */
@Component({
  selector: 'agl-participant-tile',
  imports: [TranslocoDirective],
  templateUrl: './participant-tile.html',
})
export class ParticipantTile {
  readonly row = input.required<ParticipantRow>();

  protected readonly initials = computed(() => initialsOf(this.row().name));
}
