import { DOCUMENT } from '@angular/common';
import {
  HttpContextToken,
  HttpErrorResponse,
  HttpResponse,
  type HttpInterceptorFn,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, from, switchMap, tap, throwError } from 'rxjs';

import { RUNTIME_CONFIG } from '@core/config/runtime-config';
import { readApiError } from '@core/http/api-error';
import { TenantContext } from '@core/tenant/tenant-context';

import { AuthSession } from './auth-session';

/**
 * A request that must go without the session: it is made before anyone can have signed in, and
 * before it is known that the tenant has a realm to sign in to.
 */
export const WITHOUT_SESSION = new HttpContextToken<boolean>(() => false);

/** Where the person with a valid session but no active account in the tenant is taken. */
export const ACCOUNT_NOT_ACTIVE_PATH = 'account-not-active';

/** The header that tells the API which tenant a request is about (AD-29). */
export const TENANT_HEADER = 'X-Agilina-Tenant';

/**
 * Everything the web sends to the API: the tenant of the address in `X-Agilina-Tenant`, so
 * that the API uses that tenant's database and realm, and the access token, when there is a
 * session. Nothing of this goes anywhere else: never to Keycloak or to any other host.
 *
 * When the API answers 401 (no token, or one that expired or was refused), the person is taken
 * to sign in and comes back to where they were. When it answers that the account is not active
 * in the organization (403 `account_not_active`: the session is valid, the person is not a
 * user there), signing in again would only bounce between the application and Keycloak, so
 * the person is taken to the page that explains it. A 401 that arrives right after signing in
 * is the same bounce in disguise and goes to the same page. When the API answers that the
 * tenant does not exist, the address names an organization that is not there: the page that
 * is not found. The error keeps propagating.
 */
export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const apiUrl = inject(RUNTIME_CONFIG).apiUrl;
  if (!request.url.startsWith(`${apiUrl}/`)) {
    return next(request);
  }
  const session = inject(AuthSession);
  const tenant = inject(TenantContext).current();
  const location = inject(DOCUMENT).location;
  const router = inject(Router);
  const tenanted =
    tenant === null ? request : request.clone({ setHeaders: { [TENANT_HEADER]: tenant } });

  const withoutSession = tenant === null || request.context.get(WITHOUT_SESSION);

  const accountNotActive = (): void => {
    void router.navigateByUrl(`/${tenant}/${ACCOUNT_NOT_ACTIVE_PATH}`);
  };

  return from(withoutSession ? Promise.resolve(null) : session.accessToken()).pipe(
    switchMap((token) =>
      next(
        token === null
          ? tenanted
          : tenanted.clone({ setHeaders: { Authorization: `Bearer ${token}` } }),
      ),
    ),
    tap((event) => {
      if (event instanceof HttpResponse && !withoutSession) {
        session.confirmSession();
      }
    }),
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse) {
        if (error.status === 401) {
          if (tenant !== null && session.justSignedIn()) {
            accountNotActive();
          } else {
            void session.signIn({ returnUrl: `${location.pathname}${location.search}` });
          }
        } else if (
          tenant !== null &&
          error.status === 403 &&
          readApiError(error.error)?.code === 'account_not_active'
        ) {
          accountNotActive();
        } else if (error.status === 404 && readApiError(error.error)?.code === 'tenant_not_found') {
          void router.navigateByUrl('/not-found');
        }
      }
      return throwError(() => error);
    }),
  );
};
