import { Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

/**
 * Someone is speaking: an icon and «Speaking», in words from sm on. On a phone only the icon
 * shows and a screen reader still reads the word, so it does not rely on color alone.
 */
@Component({
  selector: 'agl-speaking-indicator',
  imports: [TranslocoDirective],
  templateUrl: './speaking-indicator.html',
  host: { class: 'inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-success' },
})
export class SpeakingIndicator {}
