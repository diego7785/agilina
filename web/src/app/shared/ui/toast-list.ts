import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, input, output } from '@angular/core';

import { IconButton } from './icon-button';

/** A notice as the list draws it: its text is already in the active language. */
export interface ToastView {
  readonly id: number;
  readonly kind: 'success' | 'error';
  readonly message: string;
}

/**
 * The toasts of the application, piled at the bottom right of the screen (full width on a
 * phone). Green with a check for what worked, red with an alert for what failed: the icon says
 * it too, so the colour is not the only signal. Presentation only: it draws what it receives and
 * says what the person did (`dismissed`, `paused`, `resumed`); `Notifier` decides the rest.
 *
 * Both regions are always in the page, empty when there is nothing to say, because a screen
 * reader announces what is added to a region that already existed, not a region that appears
 * with its message: successes are polite (`status`), errors are urgent (`alert`).
 */
@Component({
  selector: 'agl-toast-list',
  imports: [NgTemplateOutlet, IconButton],
  templateUrl: './toast-list.html',
})
export class ToastList {
  readonly toasts = input.required<readonly ToastView[]>();
  /** The name of the close button, already translated. */
  readonly closeLabel = input.required<string>();
  readonly dismissed = output<number>();
  readonly paused = output<number>();
  readonly resumed = output<number>();

  protected readonly successes = computed(() =>
    this.toasts().filter((toast) => toast.kind === 'success'),
  );
  protected readonly errors = computed(() =>
    this.toasts().filter((toast) => toast.kind === 'error'),
  );
}
