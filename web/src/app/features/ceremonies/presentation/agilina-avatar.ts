import { Component, input } from '@angular/core';

/**
 * Agilina as a mascot rather than a robot icon: at rest she floats and blinks; while she speaks
 * her mouth opens and closes and she bounces a little; out of the room she is greyed out. It only
 * decorates (`aria-hidden`): the card says in words whether she is in the room and speaking. The
 * motion lives in its own stylesheet, the one thing utilities do not express, and stops for
 * whoever asks the system for reduced motion.
 */
@Component({
  selector: 'agl-agilina-avatar',
  templateUrl: './agilina-avatar.html',
  styleUrl: './agilina-avatar.scss',
  host: {
    'aria-hidden': 'true',
    '[class.speaking]': 'speaking()',
    '[class.absent]': '!present()',
  },
})
export class AgilinaAvatar {
  readonly speaking = input.required<boolean>();
  readonly present = input.required<boolean>();
}
