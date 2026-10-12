import { DOCUMENT } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';

import { TenantContext } from '@core/tenant/tenant-context';
import { provideTestI18n } from '@testing/i18n';
import { provideTestRuntimeConfig } from '@testing/runtime-config';

import {
  isSignInAnswer,
  KEYCLOAK_CLIENT_FACTORY,
  KeycloakAuthSession,
  type KeycloakClient,
} from './keycloak-auth-session';

/** keycloak-js double: records what the adapter asks of it. */
class FakeKeycloak {
  authenticated: boolean | undefined = false;
  token: string | undefined;
  readonly inits: object[] = [];
  readonly logins: object[] = [];
  readonly logouts: object[] = [];
  readonly renewals: number[] = [];
  renewalFails = false;

  init(options: object): Promise<boolean> {
    this.inits.push(options);
    return Promise.resolve(this.authenticated === true);
  }

  login(options: object): Promise<void> {
    this.logins.push(options);
    return Promise.resolve();
  }

  logout(options: object): Promise<void> {
    this.logouts.push(options);
    return Promise.resolve();
  }

  updateToken(minValidity: number): Promise<boolean> {
    this.renewals.push(minValidity);
    return this.renewalFails ? Promise.reject(new Error('session ended')) : Promise.resolve(true);
  }
}

describe('KeycloakAuthSession', () => {
  let keycloak: FakeKeycloak;
  let session: KeycloakAuthSession;
  /** The realm each client was made for, in order, and the clients of each realm. */
  let realms: string[];
  let clients: Map<string, FakeKeycloak>;

  beforeEach(() => {
    realms = [];
    clients = new Map();
    keycloak = new FakeKeycloak();
    TestBed.configureTestingModule({
      providers: [
        KeycloakAuthSession,
        provideTestI18n(),
        provideTestRuntimeConfig(),
        {
          provide: KEYCLOAK_CLIENT_FACTORY,
          useValue: (realm: string): KeycloakClient => {
            realms.push(realm);
            const client = realms.length === 1 ? keycloak : new FakeKeycloak();
            clients.set(realm, client);
            return client as unknown as KeycloakClient;
          },
        },
        {
          provide: DOCUMENT,
          useValue: {
            location: {
              href: 'http://app.test/acme/teams/a',
              origin: 'http://app.test',
              pathname: '/acme/teams/a',
              hash: '',
            },
          },
        },
      ],
    });
    TestBed.inject(TenantContext).set('acme');
    session = TestBed.inject(KeycloakAuthSession);
  });

  describe('one realm per tenant', () => {
    it('uses the realm of the tenant in the address: the prefix and its name', async () => {
      await session.accessToken();

      expect(realms).toEqual(['agilina-acme']);
    });

    it('makes the client of a realm once, however many times it is asked', async () => {
      await session.accessToken();
      await session.ensureSignedIn();
      await session.signIn();

      expect(realms).toEqual(['agilina-acme']);
    });

    it('keeps a separate session for each tenant: signing in to one is not signing in to another', async () => {
      keycloak.authenticated = true;
      expect(await session.ensureSignedIn()).toBeTrue();

      TestBed.inject(TenantContext).set('ecomoda');
      expect(await session.ensureSignedIn()).toBeFalse();

      expect(realms).toEqual(['agilina-acme', 'agilina-ecomoda']);
      expect(clients.get('agilina-ecomoda')?.logins).toHaveSize(1);
      expect(keycloak.logins).toEqual([]);
    });

    it('cannot work without a tenant: the address names none', async () => {
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          KeycloakAuthSession,
          provideTestI18n(),
          provideTestRuntimeConfig(),
          { provide: KEYCLOAK_CLIENT_FACTORY, useValue: () => new FakeKeycloak() },
        ],
      });

      await expectAsync(TestBed.inject(KeycloakAuthSession).accessToken()).toBeRejectedWithError(
        /No tenant/,
      );
    });
  });

  it('starts keycloak-js once, with PKCE and without any redirect of its own', async () => {
    await session.accessToken();
    await session.accessToken();
    await session.ensureSignedIn();

    expect(keycloak.inits).toEqual([{ pkceMethod: 'S256', checkLoginIframe: false }]);
  });

  it('is not signed in until something has asked', () => {
    expect(session.authenticated()).toBeFalse();
  });

  describe('readSignInAnswer', () => {
    function arriveAt(pathname: string, hash: string): void {
      Object.assign(TestBed.inject(DOCUMENT).location, { pathname, hash });
    }

    it("reads Keycloak's answer right away, in the realm of the tenant of the address", async () => {
      keycloak.authenticated = true;
      arriveAt('/acme/teams/a', '#state=s-1&session_state=x&iss=http%3A%2F%2Fkc&code=c-1');

      await session.readSignInAnswer();

      expect(realms).toEqual(['agilina-acme']);
      expect(keycloak.inits).toEqual([{ pkceMethod: 'S256', checkLoginIframe: false }]);
      expect(session.authenticated()).toBeTrue();
    });

    it('takes the tenant from the address, since no guard has recorded it yet', async () => {
      arriveAt('/ecomoda/teams/a', '#state=s-1&code=c-1');

      await session.readSignInAnswer();

      expect(realms).toEqual(['agilina-ecomoda']);
    });

    it('starts keycloak-js only once: the guard that asks later reuses that start', async () => {
      keycloak.authenticated = true;
      arriveAt('/acme/teams/a', '#state=s-1&code=c-1');

      await session.readSignInAnswer();
      expect(await session.ensureSignedIn('/acme/teams/a')).toBeTrue();

      expect(realms).toEqual(['agilina-acme']);
      expect(keycloak.inits.length).toBe(1);
      expect(keycloak.logins).toEqual([]);
    });

    it('remembers that the page began with a sign-in until the API accepts the session', async () => {
      keycloak.authenticated = true;
      arriveAt('/acme/teams/a', '#state=s-1&code=c-1');
      await session.readSignInAnswer();

      expect(session.justSignedIn()).toBeTrue();

      session.confirmSession();

      expect(session.justSignedIn()).toBeFalse();
    });

    it('does not take a failed sign-in for a session', async () => {
      keycloak.authenticated = false;
      arriveAt('/acme/teams/a', '#state=s-1&error=access_denied');
      await session.readSignInAnswer();

      expect(session.justSignedIn()).toBeFalse();
    });

    it('did not just sign in when the page began some other way', async () => {
      keycloak.authenticated = true;
      await session.accessToken();

      expect(session.justSignedIn()).toBeFalse();
    });

    it('does nothing without an answer, as on the activation link', async () => {
      arriveAt('/acme/activate', '#t=activation-token');
      await session.readSignInAnswer();
      arriveAt('/acme/teams', '');
      await session.readSignInAnswer();

      expect(realms).toEqual([]);
    });

    it('does nothing when the address names no tenant', async () => {
      arriveAt('/', '#state=s-1&code=c-1');
      await session.readSignInAnswer();
      arriveAt('/not-found', '#state=s-1&code=c-1');
      await session.readSignInAnswer();

      expect(realms).toEqual([]);
    });
  });

  describe('signOut', () => {
    it('ends the session in Keycloak and comes back to the entrance of the tenant', async () => {
      keycloak.authenticated = true;

      await session.signOut();

      expect(keycloak.logouts).toEqual([{ redirectUri: 'http://app.test/acme' }]);
    });
  });

  describe('isSignInAnswer', () => {
    it('recognises a code or an error that comes with its state', () => {
      expect(isSignInAnswer('#state=s&code=c')).toBeTrue();
      expect(isSignInAnswer('#state=s&error=access_denied')).toBeTrue();
      expect(isSignInAnswer('state=s&code=c')).toBeTrue();
    });

    it('ignores anything else', () => {
      expect(isSignInAnswer('')).toBeFalse();
      expect(isSignInAnswer('#t=token')).toBeFalse();
      expect(isSignInAnswer('#code=c')).toBeFalse();
      expect(isSignInAnswer('#state=s')).toBeFalse();
    });
  });

  describe('ensureSignedIn', () => {
    it('says yes when there is a session, and records it', async () => {
      keycloak.authenticated = true;

      expect(await session.ensureSignedIn('/acme/teams')).toBeTrue();
      expect(session.authenticated()).toBeTrue();
      expect(keycloak.logins).toEqual([]);
    });

    it('takes the person to sign in, back to the page they were on, in their language', async () => {
      expect(await session.ensureSignedIn()).toBeFalse();

      expect(keycloak.logins).toEqual([
        { redirectUri: 'http://app.test/acme/teams/a', locale: 'es' },
      ]);
    });

    it('comes back to the page the guard asked for', async () => {
      await session.ensureSignedIn('/acme/teams/b');

      expect(keycloak.logins).toEqual([
        { redirectUri: 'http://app.test/acme/teams/b', locale: 'es' },
      ]);
    });

    it('asks in the language the application is in', async () => {
      TestBed.inject(TranslocoService).setActiveLang('en');

      await session.ensureSignedIn();

      expect(keycloak.logins).toEqual([
        { redirectUri: 'http://app.test/acme/teams/a', locale: 'en' },
      ]);
    });
  });

  describe('accessToken', () => {
    it('is null while nobody is signed in', async () => {
      expect(await session.accessToken()).toBeNull();
      expect(keycloak.renewals).toEqual([]);
    });

    it('renews the token when it is about to expire and gives it', async () => {
      keycloak.authenticated = true;
      keycloak.token = 'the-token';

      expect(await session.accessToken()).toBe('the-token');
      expect(keycloak.renewals).toEqual([30]);
    });

    it('signs in again when the session ended and cannot be renewed', async () => {
      keycloak.authenticated = true;
      keycloak.token = 'the-token';
      await session.ensureSignedIn();
      keycloak.renewalFails = true;

      expect(await session.accessToken()).toBeNull();
      expect(session.authenticated()).toBeFalse();
      expect(keycloak.logins).toHaveSize(1);
    });

    it('is null when keycloak-js has no token even though it says there is a session', async () => {
      keycloak.authenticated = true;

      expect(await session.accessToken()).toBeNull();
    });
  });

  describe('signIn', () => {
    it('goes to the sign-in with the email and the page to come back to', async () => {
      await session.signIn({ loginHint: 'julian@example.test', returnUrl: '/acme/teams' });

      expect(keycloak.logins).toEqual([
        {
          redirectUri: 'http://app.test/acme/teams',
          locale: 'es',
          loginHint: 'julian@example.test',
        },
      ]);
    });

    it('works with no options', async () => {
      await session.signIn();

      expect(keycloak.logins).toEqual([
        { redirectUri: 'http://app.test/acme/teams/a', locale: 'es' },
      ]);
    });
  });
});
