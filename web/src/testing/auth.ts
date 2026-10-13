import { signal, type Provider } from '@angular/core';

import { AuthSession, type SignInOptions } from '@core/auth/auth-session';

/** Session double: it is signed in or not as the test decides, and remembers what it was asked. */
export class FakeAuthSession extends AuthSession {
  private readonly signedIn = signal(false);
  readonly authenticated = this.signedIn.asReadonly();
  readonly ensured: (string | undefined)[] = [];
  readonly signIns: SignInOptions[] = [];
  readonly signOuts: number[] = [];
  cameBackFromSignIn = false;
  confirmations = 0;
  token: string | null = null;
  tokenRequests = 0;

  constructor(signedIn = false) {
    super();
    this.signedIn.set(signedIn);
  }

  ensureSignedIn(returnUrl?: string): Promise<boolean> {
    this.ensured.push(returnUrl);
    return Promise.resolve(this.signedIn());
  }

  accessToken(): Promise<string | null> {
    this.tokenRequests++;
    return Promise.resolve(this.token);
  }

  justSignedIn(): boolean {
    return this.cameBackFromSignIn;
  }

  confirmSession(): void {
    this.confirmations++;
    this.cameBackFromSignIn = false;
  }

  signOut(): Promise<void> {
    this.signOuts.push(this.signOuts.length + 1);
    return Promise.resolve();
  }

  signIn(options: SignInOptions = {}): Promise<void> {
    this.signIns.push(options);
    return Promise.resolve();
  }
}

export function provideFakeAuthSession(
  session: FakeAuthSession = new FakeAuthSession(true),
): Provider {
  return { provide: AuthSession, useValue: session };
}
