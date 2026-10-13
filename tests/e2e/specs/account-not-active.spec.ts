import { expect, test } from '@playwright/test';

/**
 * AGI-123: someone with a valid session in Keycloak but no user in the organization (here, a
 * person created by hand in the console of the realm of acme). Before, the browser bounced
 * between the application and Keycloak without end; now it stops at a page that says why, and
 * ends the session on request. `make test-e2e` creates the user (`make keycloak-orphan`).
 */
const RUN = process.env['E2E_RUN'] ?? '';
const EMAIL = `e2e-orphan-${RUN}@example.test`;
const PASSWORD = 'una-clave-bien-larga-1';
const KEYCLOAK_LOGIN = /localhost:8080\/realms\/agilina-acme\/protocol\/openid-connect\/auth/;

test.beforeAll(() => {
  expect(RUN, 'E2E_RUN: run these tests with `make test-e2e`').not.toBe('');
});

test('a person without an account in the organization stops at a page that says so, with no bounce', async ({
  page,
}) => {
  // Every trip to the sign-in page of Keycloak counts: the loop is a second one.
  let signInTrips = 0;
  page.on('request', (request) => {
    if (KEYCLOAK_LOGIN.test(request.url()) && request.isNavigationRequest()) {
      signInTrips++;
    }
  });

  await page.goto('/acme');
  await expect(page).toHaveURL(KEYCLOAK_LOGIN);
  await page.getByTestId('login-email').fill(EMAIL);
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').click();

  await expect(page).toHaveURL(/\/acme\/account-not-active$/);
  await expect(page.getByTestId('account-not-active-title')).toHaveText(
    'Tu cuenta no está activa en esta organización',
  );
  // Time for a loop to show itself: if the application went back to Keycloak, it would be here.
  await page.waitForTimeout(2_000);
  await expect(page).toHaveURL(/\/acme\/account-not-active$/);
  expect(signInTrips).toBe(1);
});

test('signing out ends the session and goes back to the sign-in', async ({ page }) => {
  await page.goto('/acme');
  await page.getByTestId('login-email').fill(EMAIL);
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').click();
  await expect(page).toHaveURL(/\/acme\/account-not-active$/);

  await page.getByTestId('account-not-active-sign-out').click();

  // The session of Keycloak is gone: the entrance asks for the credentials again.
  await expect(page).toHaveURL(KEYCLOAK_LOGIN);
  await expect(page.getByTestId('login-email')).toBeVisible();
});
