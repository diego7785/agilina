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
 * The real room needs a LiveKit server whose keys the API has (it issues the token): without it the
 * room answers with a failure and these tests are skipped, saying why. The Firefox that
 * Playwright ships has not been able to set up the audio (WebRTC) with a local LiveKit server, so
 * there it ends the same way.
 *
 * AGI-61 as one person can check it: her own row in Participantes, the actions shown but not yet
 * available, no live transcript, «Salir de la sala» back to the dashboard and the room on a
 * phone. Who else comes and goes, who is speaking (in under a second) and Agilina in the room
 * need several people and the agent: they are checked by hand with three people, one on a phone
 * (AGI-135 and AGI-61, in docs/sala-y-emision-del-token.md).
 */
const RUN = process.env['E2E_RUN'] ?? '';
const TENANT = 'acme';
const EMAIL = `e2e-${RUN}@example.test`;
const PASSWORD = 'una-clave-bien-larga-1';
const WITHOUT_ROOM =
  'The room could not be reached: it needs LiveKit, and a browser that sets up WebRTC';

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

test('her own row in the participants says it is her, connected', async ({ page }) => {
  await signIn(page);
  await enterRoom(page);

  const own = page
    .getByTestId('room-participant')
    .filter({ has: page.getByTestId('participant-self') });
  await expect(own).toHaveCount(1);
  await expect(own.getByTestId('participant-self')).toHaveText('· tú');
  await expect(own.getByTestId('participant-email')).toHaveText(EMAIL);
  await expect(own.getByTestId('participant-presence')).toHaveText('Conectado');
});

test('the actions are shown, not yet available, and there is no live transcript', async ({
  page,
}) => {
  await signIn(page);
  await enterRoom(page);

  for (const action of ['room-start-daily', 'room-end-turn', 'room-end-ceremony']) {
    await expect(page.getByTestId(action)).toBeVisible();
    await expect(page.getByTestId(action)).toBeDisabled();
  }
  await expect(page.getByTestId('room-actions-unavailable')).toBeVisible();
  // A guard against a live transcript added later; criterion 5 is checked by hand (AGI-140).
  await expect(page.locator('[data-testid*="transcript"]')).toHaveCount(0);
});

test('«Salir de la sala» takes her back to the dashboard and out of the room', async ({ page }) => {
  await signIn(page);
  await enterRoom(page);

  await page.getByTestId('room-leave').click();

  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams/[0-9a-f-]{36}$`));
  await expect(page.getByTestId('join-room')).toBeVisible();
  await expect(page.locator('[data-testid="remote-audio"]')).toHaveCount(0);
});

test('on a phone the room stacks, nothing scrolls sideways and she can still leave', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page);
  await enterRoom(page);

  await expect(page.getByTestId('room-participants')).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  const participants = await page.getByTestId('room-participants').boundingBox();
  const actions = await page.getByTestId('room-actions').boundingBox();
  expect(actions!.y).toBeGreaterThan(participants!.y + participants!.height - 1);
  await page.getByTestId('room-leave').scrollIntoViewIfNeeded();
  await expect(page.getByTestId('room-leave')).toBeInViewport();
  await page.getByTestId('room-leave').click();
  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams/[0-9a-f-]{36}$`));
});
