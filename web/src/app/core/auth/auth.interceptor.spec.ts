import { DOCUMENT } from '@angular/common';
import { HttpClient, HttpContext, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';

import { TenantContext } from '@core/tenant/tenant-context';
import { FakeAuthSession, provideFakeAuthSession } from '@testing/auth';
import { provideTestRuntimeConfig, TEST_RUNTIME_CONFIG } from '@testing/runtime-config';
import { provideTestTenant } from '@testing/tenant';

import { authInterceptor, TENANT_HEADER, WITHOUT_SESSION } from './auth.interceptor';

const API = TEST_RUNTIME_CONFIG.apiUrl;

describe('authInterceptor', () => {
  let session: FakeAuthSession;
  let http: HttpClient;
  let backend: HttpTestingController;
  let navigations: string[];

  beforeEach(() => {
    session = new FakeAuthSession(true);
    session.token = 'the-token';
    navigations = [];
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideTestRuntimeConfig(),
        provideFakeAuthSession(session),
        provideTestTenant('acme'),
        {
          provide: DOCUMENT,
          useValue: { location: { pathname: '/acme/teams/a', search: '?x=1' } },
        },
        {
          provide: Router,
          useValue: {
            navigateByUrl: (url: string) => {
              navigations.push(url);
              return Promise.resolve(true);
            },
          },
        },
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
  });

  /** Lets the interceptor's promise settle before the request is looked for. */
  async function settle(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
  }

  describe('the tenant', () => {
    it('is named in every request to the API, so that the API uses its database and realm', async () => {
      http.get(`${API}/v1/teams`).subscribe();
      await settle();

      expect(backend.expectOne(`${API}/v1/teams`).request.headers.get(TENANT_HEADER)).toBe('acme');
    });

    it('is named even when nobody is signed in (the invitation is answered by its tenant)', async () => {
      session.token = null;

      http.post(`${API}/v1/invitations/status`, {}).subscribe();
      await settle();

      const request = backend.expectOne(`${API}/v1/invitations/status`).request;
      expect(request.headers.get(TENANT_HEADER)).toBe('acme');
      expect(request.headers.has('Authorization')).toBeFalse();
    });

    it('follows the address: another tenant, another header', async () => {
      TestBed.inject(TenantContext).set('ecomoda');

      http.get(`${API}/v1/teams`).subscribe();
      await settle();

      expect(backend.expectOne(`${API}/v1/teams`).request.headers.get(TENANT_HEADER)).toBe(
        'ecomoda',
      );
    });

    it('is not sent anywhere else', async () => {
      http.get('http://auth.test/realms/agilina-acme/protocol/openid-connect/certs').subscribe();
      http.get(`${API}.evil.test/v1/teams`).subscribe();
      await settle();

      for (const request of backend.match(() => true)) {
        expect(request.request.headers.has(TENANT_HEADER)).toBeFalse();
      }
    });

    it('without a tenant in the address nothing is added and no session is asked for', async () => {
      TestBed.inject(TenantContext).set('acme');
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(withInterceptors([authInterceptor])),
          provideHttpClientTesting(),
          provideTestRuntimeConfig(),
          provideFakeAuthSession(session),
          { provide: DOCUMENT, useValue: { location: { pathname: '/', search: '' } } },
          { provide: Router, useValue: {} },
        ],
      });
      const bare = TestBed.inject(HttpClient);
      const bareBackend = TestBed.inject(HttpTestingController);

      bare.get(`${API}/health`).subscribe();
      await settle();

      const request = bareBackend.expectOne(`${API}/health`).request;
      expect(request.headers.has(TENANT_HEADER)).toBeFalse();
      expect(request.headers.has('Authorization')).toBeFalse();
    });
  });

  describe('a request without a session', () => {
    it('names the tenant but asks nothing of the session and carries no token', async () => {
      // The check of the tenant itself: made before anybody can have signed in, and before it is
      // known that the tenant has a realm.
      http
        .get(`${API}/v1/tenant`, { context: new HttpContext().set(WITHOUT_SESSION, true) })
        .subscribe();
      await settle();

      const request = backend.expectOne(`${API}/v1/tenant`).request;
      expect(request.headers.get(TENANT_HEADER)).toBe('acme');
      expect(request.headers.has('Authorization')).toBeFalse();
      expect(session.tokenRequests).toBe(0);
    });
  });

  describe('the token', () => {
    it('is sent to the API', async () => {
      http.get(`${API}/v1/teams`).subscribe();
      await settle();

      expect(backend.expectOne(`${API}/v1/teams`).request.headers.get('Authorization')).toBe(
        'Bearer the-token',
      );
    });

    it('is never sent anywhere else', async () => {
      http.get('http://auth.test/realms/agilina-acme/protocol/openid-connect/certs').subscribe();
      http.get(`${API}.evil.test/v1/teams`).subscribe();
      await settle();

      for (const request of backend.match(() => true)) {
        expect(request.request.headers.has('Authorization')).toBeFalse();
      }
    });

    it('is not sent when nobody is signed in', async () => {
      session.token = null;

      http.get(`${API}/v1/invitations/status`).subscribe();
      await settle();

      expect(
        backend.expectOne(`${API}/v1/invitations/status`).request.headers.has('Authorization'),
      ).toBeFalse();
    });
  });

  describe('what the API answers', () => {
    it('takes the person to sign in, back to where they were, on a 401', async () => {
      let failed = false;
      http.get(`${API}/v1/teams`).subscribe({ error: () => (failed = true) });
      await settle();

      backend
        .expectOne(`${API}/v1/teams`)
        .flush(
          { error: { code: 'not_authenticated' } },
          { status: 401, statusText: 'Unauthorized' },
        );
      await settle();

      expect(failed).toBeTrue();
      expect(session.signIns).toEqual([{ returnUrl: '/acme/teams/a?x=1' }]);
    });

    it('takes the person to the page that is not found when the tenant is not there', async () => {
      http.get(`${API}/v1/teams`).subscribe({ error: () => undefined });
      await settle();

      backend
        .expectOne(`${API}/v1/teams`)
        .flush({ error: { code: 'tenant_not_found' } }, { status: 404, statusText: 'Not Found' });
      await settle();

      expect(navigations).toEqual(['/not-found']);
      expect(session.signIns).toEqual([]);
    });

    it('takes the person to the page of an account that is not active, and does not sign in again', async () => {
      http.get(`${API}/v1/teams`).subscribe({ error: () => undefined });
      await settle();

      backend
        .expectOne(`${API}/v1/teams`)
        .flush({ error: { code: 'account_not_active' } }, { status: 403, statusText: 'Forbidden' });
      await settle();

      expect(navigations).toEqual(['/acme/account-not-active']);
      expect(session.signIns).toEqual([]);
    });

    it('does not sign in again when a 401 arrives right after signing in: that is the loop', async () => {
      session.cameBackFromSignIn = true;
      http.get(`${API}/v1/teams`).subscribe({ error: () => undefined });
      await settle();

      backend
        .expectOne(`${API}/v1/teams`)
        .flush(
          { error: { code: 'not_authenticated' } },
          { status: 401, statusText: 'Unauthorized' },
        );
      await settle();

      expect(navigations).toEqual(['/acme/account-not-active']);
      expect(session.signIns).toEqual([]);
    });

    it('signs in again on a 401 once the API has accepted the session (an expired token)', async () => {
      session.cameBackFromSignIn = true;
      http.get(`${API}/v1/teams`).subscribe();
      await settle();
      backend.expectOne(`${API}/v1/teams`).flush([]);
      await settle();
      expect(session.confirmations).toBe(1);

      http.get(`${API}/v1/teams`).subscribe({ error: () => undefined });
      await settle();
      backend
        .expectOne(`${API}/v1/teams`)
        .flush(
          { error: { code: 'not_authenticated' } },
          { status: 401, statusText: 'Unauthorized' },
        );
      await settle();

      expect(session.signIns).toEqual([{ returnUrl: '/acme/teams/a?x=1' }]);
      expect(navigations).toEqual([]);
    });

    it('does not take a 403 for another reason to that page', async () => {
      http.get(`${API}/v1/teams`).subscribe({ error: () => undefined });
      await settle();

      backend
        .expectOne(`${API}/v1/teams`)
        .flush({ error: { code: 'not_a_team_member' } }, { status: 403, statusText: 'Forbidden' });
      await settle();

      expect(navigations).toEqual([]);
    });

    it('does not confirm the session with an answer to a request made without it', async () => {
      http
        .get(`${API}/v1/tenant`, { context: new HttpContext().set(WITHOUT_SESSION, true) })
        .subscribe();
      await settle();
      backend.expectOne(`${API}/v1/tenant`).flush({});
      await settle();

      expect(session.confirmations).toBe(0);
    });

    it('leaves any other 404 to the screen that asked', async () => {
      http.get(`${API}/v1/teams/x`).subscribe({ error: () => undefined });
      await settle();

      backend
        .expectOne(`${API}/v1/teams/x`)
        .flush(
          { error: { code: 'invitation_not_found' } },
          { status: 404, statusText: 'Not Found' },
        );
      await settle();

      expect(navigations).toEqual([]);
    });

    it('does not sign in again for other errors', async () => {
      http.get(`${API}/v1/teams`).subscribe({ error: () => undefined });
      await settle();

      backend.expectOne(`${API}/v1/teams`).flush({}, { status: 403, statusText: 'Forbidden' });
      await settle();

      expect(session.signIns).toEqual([]);
      expect(navigations).toEqual([]);
    });

    it('survives an error with no body at all', async () => {
      http.get(`${API}/v1/teams`).subscribe({ error: () => undefined });
      await settle();

      backend.expectOne(`${API}/v1/teams`).flush(null, { status: 404, statusText: 'Not Found' });
      await settle();

      expect(navigations).toEqual([]);
    });
  });
});
