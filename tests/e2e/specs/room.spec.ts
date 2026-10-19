import { type Browser, type BrowserType, expect, type Page, test } from '@playwright/test';

import { WEB } from '../playwright.config';

/**
 * AGI-60 as a participant lives it, in Chromium and in Firefox (one project each): from the
 * dashboard she enters the room of her team's daily, with the microphone on; if the browser
 * refuses the microphone she is told how to allow it and stays as a listener; leaving the page
 * leaves the room. A network that drops is not told here: Playwright cannot cut a connection
 * already open to `localhost`, so it is covered by the facade's tests and by hand.
 *
 * She is the person of the sign-in story, and the dashboard story left her team with a daily a
 * few minutes away, so the room is open (from ten minutes before the daily to fifteen after).
 * The real room needs AGI-59 (the API issues the token) and a LiveKit server: without them the
 * room answers with a failure and these tests are skipped, saying why. The Firefox that
 * Playwright ships has not been able to set up the audio (WebRTC) with a local LiveKit server, so
 * there it ends the same way.
 *
 * Who else is in the room and whether they hear each other is checked by hand with two people
 * (AGI-135) until the room lists its participants (AGI-61).
 */
const RUN = process.env['E2E_RUN'] ?? '';
const TENANT = 'acme';
const EMAIL = `e2e-${RUN}@example.test`;
const PASSWORD = 'una-clave-bien-larga-1';
const WITHOUT_ROOM =
  'The room could not be reached: it needs AGI-59 and LiveKit, and a browser that sets up WebRTC';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  expect(RUN, 'E2E_RUN: run these tests with `make test-e2e`').not.toBe('');
});

/** Signs her in; with a single team she lands on its dashboard. */
async function signIn(page: Page): Promise<void> {
  await page.goto(`/${TENANT}`);
  await page.getByTestId('login-email').fill(EMAIL);
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').click();
  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams/[0-9a-f-]{36}$`));
}

/**
 * Enters the room from the dashboard and waits until the page says how it went: skipped when
 * the window to join is closed or the room cannot be reached in this environment.
 */
async function enterRoom(page: Page): Promise<void> {
  const join = page.getByTestId('join-room');
  await expect(join).toBeVisible();
  const isLink = (await join.evaluate((element) => element.tagName)) === 'A';
  test.skip(!isLink, 'The window to join is closed');
  await join.click();
  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams/[0-9a-f-]{36}/room$`));
  const settled = page
    .getByTestId('microphone-on')
    .or(page.getByTestId('microphone-alert'))
    .or(page.getByTestId('room-failure'));
  await expect(settled).toBeVisible({ timeout: 20_000 });
  test.skip(await page.getByTestId('room-failure').isVisible(), WITHOUT_ROOM);
}

/** A browser of the same kind whose microphone the person refuses. */
function refusingBrowser(browserType: BrowserType): Promise<Browser> {
  return browserType.name() === 'firefox'
    ? browserType.launch({
        firefoxUserPrefs: {
          'media.navigator.streams.fake': true,
          'permissions.default.microphone': 2,
        },
      })
    : browserType.launch({
        channel: 'chromium',
        // Without the microphone Chromium hides its local addresses behind mDNS names, which a
        // LiveKit server on this machine cannot reach; a hosted one is reached through TURN.
        args: [
          '--use-fake-device-for-media-stream',
          '--deny-permission-prompts',
          '--disable-features=WebRtcHideLocalIpsWithMdns',
        ],
      });
}

test('she enters the room from the dashboard and her microphone turns on', async ({ page }) => {
  await signIn(page);
  await enterRoom(page);

  await expect(page.getByTestId('room-status')).toHaveText('Conectado');
  await expect(page.getByTestId('microphone-on')).toHaveText('Micrófono activo');
});

test('if she refuses the microphone she is told how to allow it and stays as a listener', async ({
  playwright,
  browserName,
}) => {
  const browser = await refusingBrowser(playwright[browserName]);
  try {
    const context = await browser.newContext({ baseURL: WEB, locale: 'es-CO' });
    // The test runner hands the project's permissions to every context: this one has none.
    await context.clearPermissions();
    const page = await context.newPage();
    await signIn(page);
    await enterRoom(page);

    await expect(page.getByTestId('microphone-alert')).toContainText(
      'No tenemos permiso para usar tu micrófono',
    );
    await expect(page.getByTestId('microphone-alert')).toContainText('como oyente');
    await expect(page.getByTestId('room-status')).toHaveText('Conectado');
    await expect(page.getByTestId('microphone-retry')).toBeVisible();
  } finally {
    await browser.close();
  }
});

test('leaving the room for the dashboard leaves the room', async ({ page }) => {
  await signIn(page);
  await enterRoom(page);

  await page.goBack();

  await expect(page.getByTestId('join-room')).toBeVisible();
  await expect(page.locator('[data-testid="remote-audio"]')).toHaveCount(0);
});
