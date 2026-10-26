import { Component, computed, input } from '@angular/core';
import { TranslocoDirective, translateSignal } from '@jsverse/transloco';

import { initialsOf } from '@shared/utils/initials';

import { SpeakingIndicator } from './speaking-indicator';
import { type ParticipantRow } from '../domain/participant-row';

/**
 * One person in the list of the room: their initials, name and email, «· you» on the one looking
 * at the screen, and whether they are connected. A disconnected person is dimmed and the row
 * also says so in words; the email and the label keep their contrast. Whoever is speaking gets a
 * ring and the «Hablando» indicator (an icon and words), so it does not rest on the colour alone.
 * Someone the room does not know by name (in it, but not invited) is «Participante».
 */
@Component({
  selector: 'agl-participant-tile',
  imports: [TranslocoDirective, SpeakingIndicator],
  templateUrl: './participant-tile.html',
})
export class ParticipantTile {
  readonly row = input.required<ParticipantRow>();

  private readonly unknownName = translateSignal('ceremonies.room.participants.unknown');

  protected readonly name = computed(() => this.row().name || this.unknownName());
  protected readonly initials = computed(() => initialsOf(this.name()));
}
