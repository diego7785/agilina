import { type Signal } from '@angular/core';

export interface SignInOptions {
  /** Where to come back to after signing in, as a path of the application (`/teams/abc`).
   * By default, the page the person is on. */
  readonly returnUrl?: string;
  /** The email to fill in on the sign-in page. */
  readonly loginHint?: string;
}

/**
 * Port towards the session of the person using the application. An abstract class so that
 * it doubles as the injection token; the Keycloak adapter is bound in app.config.ts.
 *
 * The session is checked when something asks for it, not when the application starts: the
 * public screens (the activation link, the environment status) never take anybody to sign in.
 */
export abstract class AuthSession {
  /** Whether a signed-in session is known. It is `false` until something has asked. */
  abstract readonly authenticated: Signal<boolean>;

  /**
   * Resolves `true` when the person is signed in. When they are not, it takes them to the
   * sign-in page (and comes back to `returnUrl` afterwards), so what it resolves with then no
   * longer matters: the page is being left.
   */
  abstract ensureSignedIn(returnUrl?: string): Promise<boolean>;

  /** The access token to send to the API, renewed when it is about to expire, or `null`
   * when nobody is signed in. */
  abstract accessToken(): Promise<string | null>;

  /** Takes the person to the sign-in page, even if a session seems to exist. */
  abstract signIn(options?: SignInOptions): Promise<void>;

  /**
   * Whether this load of the page began with the answer of a sign-in and the API has not
   * accepted the session yet. A 401 in that window cannot be an expired token, and signing in
   * again would only come back to the same place: it is the end of a loop, not a reason to
   * sign in.
   */
  abstract justSignedIn(): boolean;

  /** The API accepted the session: from now on a 401 means the session needs renewing. */
  abstract confirmSession(): void;

  /** Ends the session in Keycloak and takes the person back to the entrance of the tenant. */
  abstract signOut(): Promise<void>;
}
