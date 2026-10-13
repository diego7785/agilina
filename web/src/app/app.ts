import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { Notifier } from '@core/notifications/notifier';
import { ToastList } from '@shared/ui/toast-list';

/**
 * Root component. The frame around each screen is a layout chosen by its route; the toasts hang
 * from here, so they show over any screen and outlive a change of screen.
 */
@Component({
  selector: 'agl-root',
  imports: [RouterOutlet, TranslocoPipe, ToastList],
  templateUrl: './app.html',
})
export class App {
  protected readonly notifier = inject(Notifier);
}
