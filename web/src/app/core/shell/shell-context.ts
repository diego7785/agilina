import { Injectable, signal } from '@angular/core';

/** What the top bar shows about the team the user is in. */
export interface ShellTeam {
  /** The team's id, for the entries of the navigation. */
  readonly id: string;
  readonly name: string;
  /** The code of the label of the user's role in that team; the bar translates it. */
  readonly roleLabel: string;
  /** The signed-in person, as the team knows them. */
  readonly userName: string;
  /**
   * Whether to draw the Settings entry: only for an admin. It is comfort and not security: the
   * API checks the permission on every settings route.
   */
  readonly canConfigure: boolean;
}

/**
 * The team the user is looking at, for the top bar. The layout cannot import a feature, so
 * the screens of a team say which one it is here and the bar reads it. A screen that is not
 * about a team (the selector, creating one) leaves it empty.
 */
@Injectable({ providedIn: 'root' })
export class ShellContext {
  private readonly current = signal<ShellTeam | null>(null);

  readonly team = this.current.asReadonly();

  enter(team: ShellTeam): void {
    this.current.set(team);
  }

  /** Leaves the team, unless a screen of another team already took the bar over. */
  leave(team: ShellTeam): void {
    if (this.current() === team) {
      this.current.set(null);
    }
  }
}
