import { DOCUMENT } from '@angular/common';
import { inject, Injectable, InjectionToken, signal } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';
import type Keycloak from 'keycloak-js';

import { RUNTIME_CONFIG } from '@core/config/runtime-config';
import { TenantContext } from '@core/tenant/tenant-context';
import { isValidTenantSlug } from '@core/tenant/tenant-slug';

import { type AuthSession, type SignInOptions } from './auth-session';

/** The part of keycloak-js this adapter uses: what a test double has to answer. */
export type KeycloakClient = Pick<
  Keycloak,
  'init' | 'login' | 'logout' | 'updateToken' | 'authenticated' | 'token'
>;

/** Builds the keycloak-js client of a realm; bound in provide-auth.ts. */
export type KeycloakClientFactory = (realm: string) => KeycloakClient;

export const KEYCLOAK_CLIENT_FACTORY = new InjectionToken<KeycloakClientFactory>(
  'KEYCLOAK_CLIENT_FACTORY',
);

/** The access token is renewed when it has less than this many seconds left. */
const MIN_TOKEN_VALIDITY_SECONDS = 30;

/**
 * Whether the fragment of the address is Keycloak's answer to a sign-in (`#state=…&code=…`,
 * or `#state=…&error=…`). The activation link (`#t=…`) is not.
 */
export function isSignInAnswer(fragment: string): boolean {
  const params = new URLSearchParams(fragment.replace(/^#/, ''));
  return params.has('state') && (params.has('code') || params.has('error'));
}

interface TenantSession {
  readonly client: KeycloakClient;
  readonly started: Promise<void>;
}

/**
 * Keycloak adapter of the session (authorization code flow with PKCE, which the realm's
 * `agilina-web` client requires). Every tenant has its own realm (AD-29): the client is the
 * one of the realm of the tenant in the address, made the first time it is needed. The tokens
 * live in memory only: never in localStorage.
 */
@Injectable()
export class KeycloakAuthSession implements AuthSession {
  private readonly newClient = inject(KEYCLOAK_CLIENT_FACTORY);
  private readonly realmPrefix = inject(RUNTIME_CONFIG).keycloak.realmPrefix;
  private readonly tenant = inject(TenantContext);
  private readonly document = inject(DOCUMENT);
  private readonly language = inject(TranslocoService);
  private readonly sessions = new Map<string, TenantSession>();
  private readonly signedIn = signal(false);
  private cameBackFromSignIn = false;

  readonly authenticated = this.signedIn.asReadonly();

  async ensureSignedIn(returnUrl?: string): Promise<boolean> {
    const { client } = await this.start();
    if (client.authenticated) {
      return true;
    }
    await this.redirectToSignIn(client, returnUrl === undefined ? {} : { returnUrl });
    return false;
  }

  async accessToken(): Promise<string | null> {
    const { client } = await this.start();
    if (!client.authenticated) {
      return null;
    }
    try {
      await client.updateToken(MIN_TOKEN_VALIDITY_SECONDS);
    } catch {
      // The session cannot be renewed (it ended in Keycloak): sign in again.
      this.signedIn.set(false);
      await this.redirectToSignIn(client, {});
      return null;
    }
    return client.token ?? null;
  }

  async signIn(options: SignInOptions = {}): Promise<void> {
    const { client } = await this.start();
    await this.redirectToSignIn(client, options);
  }

  justSignedIn(): boolean {
    return this.cameBackFromSignIn;
  }

  confirmSession(): void {
    this.cameBackFromSignIn = false;
  }

  async signOut(): Promise<void> {
    const { client } = await this.start();
    await client.logout({ redirectUri: `${this.document.location.origin}${this.tenant.url()}` });
  }

  /**
   * Reads Keycloak's answer to a sign-in that has just come back, when the address carries
   * one, so that it happens before the router reads the address (provide-auth.ts runs it while
   * the application starts). keycloak-js takes the answer out of the address; read later, from
   * the guard, the router would write the address it started with back, answer included.
   *
   * No guard has recorded the tenant yet, so it is the first segment of the address, the realm
   * the answer comes from; the guard that asks later finds that session already started.
   * Without an answer it does nothing: the public screens never start keycloak-js.
   */
  async readSignInAnswer(): Promise<void> {
    const { hash, pathname } = this.document.location;
    const slug = pathname.split('/')[1] ?? '';
    if (isSignInAnswer(hash) && isValidTenantSlug(slug)) {
      const { client } = await this.start(slug);
      this.cameBackFromSignIn = client.authenticated;
    }
  }

  /**
   * Starts keycloak-js for the tenant of the address, once. With no `onLoad` it only reads the
   * answer of a sign-in that has just come back (the `code` in the address) and redirects
   * nowhere.
   */
  private async start(slug = this.tenant.require()): Promise<TenantSession> {
    let session = this.sessions.get(slug);
    if (session === undefined) {
      const client = this.newClient(`${this.realmPrefix}${slug}`);
      const started = client.init({ pkceMethod: 'S256', checkLoginIframe: false }).then(() => {
        this.signedIn.set(client.authenticated);
      });
      session = { client, started };
      this.sessions.set(slug, session);
    }
    await session.started;
    this.signedIn.set(session.client.authenticated);
    return session;
  }

  private async redirectToSignIn(client: KeycloakClient, options: SignInOptions): Promise<void> {
    const location = this.document.location;
    const returnUrl = options.returnUrl;
    await client.login({
      redirectUri: returnUrl === undefined ? location.href : `${location.origin}${returnUrl}`,
      locale: this.language.getActiveLang(),
      ...(options.loginHint !== undefined && { loginHint: options.loginHint }),
    });
  }
}
