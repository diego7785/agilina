import { inject, Injectable, signal } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';

/** What happened: a success confirms an action, an error says it did not work. */
export type NotificationKind = 'success' | 'error';

/** A notice on screen, already in the language of the person. */
export interface Notification {
  readonly id: number;
  readonly kind: NotificationKind;
  readonly message: string;
}

/** How long a success stays on screen on its own; an error stays until it is closed. */
export const SUCCESS_DURATION_MS = 5_000;
/** How many notices show at once: a new one pushes the oldest out. */
export const MAX_NOTIFICATIONS = 3;

/**
 * The toasts of the application: short notices that confirm an action or say it failed, drawn
 * by `agl-toast-list` at the bottom of the screen without moving what is on it.
 *
 * A screen asks for one with the key of its text in the catalogs (`teams.sprint.saved`) and its
 * parameters, never with the text: it is translated here, in the active language. It lives in
 * `core` and for the whole application, so a notice survives a change of screen.
 *
 * A success goes away by itself after `SUCCESS_DURATION_MS`, unless the person is pointing at it
 * or has the focus inside it; an error stays until it is closed, since it asks for something to
 * be read and maybe fixed. See "Notificaciones" in the web guide for what is not a toast.
 */
@Injectable({ providedIn: 'root' })
export class Notifier {
  private readonly transloco = inject(TranslocoService);
  private readonly shown = signal<readonly Notification[]>([]);
  private readonly timers = new Map<number, ReturnType<typeof setTimeout>>();
  private lastId = 0;

  readonly notifications = this.shown.asReadonly();

  /** Confirms that an action worked. */
  success(key: string, params?: Record<string, unknown>): void {
    this.show('success', key, params);
  }

  /** Says that an action did not work. */
  error(key: string, params?: Record<string, unknown>): void {
    this.show('error', key, params);
  }

  /** Closes a notice, whether the person asked or its time was up. */
  dismiss(id: number): void {
    this.stopTimer(id);
    this.shown.update((notices) => notices.filter((notice) => notice.id !== id));
  }

  /** The person points at a notice or focuses it: a success does not go away meanwhile. */
  pause(id: number): void {
    this.stopTimer(id);
  }

  /** The person moves away: a success that is still on screen starts its time again. */
  resume(id: number): void {
    const notice = this.shown().find((candidate) => candidate.id === id);
    if (notice?.kind === 'success') {
      this.startTimer(id);
    }
  }

  private show(kind: NotificationKind, key: string, params?: Record<string, unknown>): void {
    const id = ++this.lastId;
    const message = this.transloco.translate(key, params);
    this.shown.update((notices) => [...notices, { id, kind, message }].slice(-MAX_NOTIFICATIONS));
    this.forgetTimersOfGone();
    if (kind === 'success') {
      this.startTimer(id);
    }
  }

  private startTimer(id: number): void {
    this.stopTimer(id);
    this.timers.set(
      id,
      setTimeout(() => {
        this.dismiss(id);
      }, SUCCESS_DURATION_MS),
    );
  }

  private stopTimer(id: number): void {
    const timer = this.timers.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      this.timers.delete(id);
    }
  }

  /** The oldest notice that a new one pushed out must not leave a timer behind. */
  private forgetTimersOfGone(): void {
    const present = new Set(this.shown().map((notice) => notice.id));
    for (const id of this.timers.keys()) {
      if (!present.has(id)) {
        this.stopTimer(id);
      }
    }
  }
}
