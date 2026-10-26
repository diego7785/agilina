import { expect, test, type BrowserContext, type Page } from '@playwright/test';

/**
 * HU-12 as an admin lives it, in the tenant acme: the dashboard of her team with no sprint yet,
 * the top bar with its entries and the team header in Settings → Sprint, then the sprint she
 * configures (the day N of M, the next daily and the room that opens ten minutes before it), the
 * way to switch team even with a single one, and the screen on a phone.
 *
 * She is the person of the sign-in story (`make test-e2e` invited her to a team of her own and
 * `sign-in.spec.ts` activated her account, which runs before this file). The sprint is set for
 * the time zone of Bogota, which the browser of this story uses, so the times typed here are
 * the ones the dashboard shows.
 *
 * Elements are found by their `data-testid`; what the person reads is still checked, on the
 * element found that way. The member's side (no Settings entry at all) is in the members story.
 */
const RUN = process.env['E2E_RUN'] ?? '';
const TENANT = 'acme';
const EMAIL = `e2e-${RUN}@example.test`;
const PASSWORD = 'una-clave-bien-larga-1';
const TEAM = `E2E ${RUN} ${TENANT}`;
const ZONE = 'America/Bogota';
const KEYCLOAK_LOGIN = new RegExp(
  `localhost:8080/realms/agilina-${TENANT}/protocol/openid-connect/auth`,
);

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  expect(RUN, 'E2E_RUN: run these tests with `make test-e2e`').not.toBe('');
});

/** A wall-clock time in Bogota, `HH:MM`, some minutes from now. */
function bogotaTimeIn(minutes: number): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: ZONE,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(Date.now() + minutes * 60_000));
}

/** Types a time (`HH:MM`, 24 hours) in the hour, minutes and a. m. or p. m. boxes. */
async function fillDailyTime(time: string): Promise<void> {
  const [hours, minutes] = time.split(':').map(Number) as [number, number];
  await page.getByTestId('sprint-daily-time').fill(String(hours % 12 === 0 ? 12 : hours % 12));
  await page.getByTestId('sprint-daily-time-minute').fill(String(minutes).padStart(2, '0'));
  await page.getByTestId('sprint-daily-time-period').fill(hours < 12 ? 'a' : 'p');
}

/** A calendar date in Bogota, `YYYY-MM-DD`, some days from today. */
function bogotaDateIn(days: number): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: ZONE }).format(
    new Date(Date.now() + days * 24 * 60 * 60_000),
  );
}

let context: BrowserContext;
let page: Page;
let teamUrl = '';

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext({ locale: 'es-CO', timezoneId: ZONE });
  page = await context.newPage();
  await page.goto(`/${TENANT}`);
  await expect(page).toHaveURL(KEYCLOAK_LOGIN);
  await page.getByTestId('login-email').fill(EMAIL);
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').click();
  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams/[0-9a-f-]{36}$`));
  teamUrl = page.url();
});

test.afterAll(async () => {
  await context.close();
});

/** Picks a day in the calendar of a date box, moving to its month first if needed. */
async function pickDate(box: string, date: string): Promise<void> {
  await page.getByTestId(box).click();
  // The calendar is drawn as a whole: once it is there, counting the days does not race it.
  const calendar = page.locator(`[id="${box}-calendar"]`);
  await calendar.waitFor();
  const day = calendar.locator(`[data-date="${date}"]`);
  const firstDay = calendar.locator('[data-date]').first();
  for (let month = 0; month < 2 && (await day.count()) === 0; month++) {
    const shown = (await firstDay.getAttribute('data-date')) ?? '';
    await page.getByRole('button', { name: 'Mes siguiente' }).click();
    // Counting again before the next month is drawn would move one month too many, and the
    // click would land on the day in the same cell of that month.
    await expect(firstDay).not.toHaveAttribute('data-date', shown);
  }
  await day.click();
}

/** Opens Settings → Sprint from the top bar and the tabs. */
async function openSprintSettings(): Promise<void> {
  await page.getByTestId('nav-settings').click();
  await page.getByTestId('settings-tab-sprint').click();
  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams/[0-9a-f-]{36}/settings/sprint$`));
}

test('a team with no sprint says so, offers no room and shows the mode as a read only label', async () => {
  await expect(page.getByTestId('dashboard-title')).toHaveText('Dashboard');
  await expect(page.getByTestId('sprint-day')).toHaveText('Sin sprint activo');
  await expect(page.getByTestId('ceremony-none')).toHaveText('No hay ceremonias programadas');
  await expect(page.getByTestId('team-mode')).toHaveText('Soporte');
  await expect(page.getByTestId('mode-card').locator('button, input, select')).toHaveCount(0);
  await expect(page.getByTestId('room-card')).toHaveCount(0);
  await expect(page.getByTestId('join-room')).toHaveCount(0);
});

test('the top bar names the team and the role, with the dashboard and Settings entries', async () => {
  await expect(page.getByTestId('header-team')).toHaveText(TEAM);
  await expect(page.getByTestId('header-role-label')).toHaveText('Scrum Master');
  await expect(page.getByTestId('nav-dashboard')).toHaveAttribute('aria-current', 'page');
  await expect(page.getByTestId('nav-settings')).toBeVisible();
  await expect(page.getByTestId('nav-settings')).not.toHaveAttribute('aria-current', 'page');
});

test('Settings → Sprint keeps the team header and marks Settings as the current entry', async () => {
  await openSprintSettings();

  await expect(page.getByTestId('header-team')).toHaveText(TEAM);
  await expect(page.getByTestId('header-role-label')).toHaveText('Scrum Master');
  await expect(page.getByTestId('nav-settings')).toHaveAttribute('aria-current', 'page');
  await expect(page.getByTestId('nav-dashboard')).not.toHaveAttribute('aria-current', 'page');
  // With no sprint there is nothing to close, and no number to show: the API gives it on saving.
  await expect(page.getByTestId('sprint-close-open')).toHaveCount(0);
  await expect(page.getByTestId('sprint-title')).toHaveText('Sprint');
});

test('with a sprint whose daily is hours away, the dashboard shows day 1 and the room closed', async () => {
  await pickDate('sprint-start-date', bogotaDateIn(0));
  await pickDate('sprint-end-date', bogotaDateIn(9));
  await fillDailyTime(bogotaTimeIn(180));
  await page.getByTestId(`sprint-participant-${EMAIL}`).locator('input').check();
  await expect(page.getByTestId('sprint-submit')).toHaveText('Guardar');
  await page.getByTestId('sprint-submit').click();
  // The confirmation is a toast, outside the page: it does not push anything.
  await expect(page.getByTestId('toast-success').last()).toHaveText(/Sprint guardado\./);
  await expect(page.locator('main')).not.toContainText('Sprint guardado.');
  // The pointer is still where "Guardar" was, now under the toast, which waits while it is there:
  // a person moves away before going on.
  await page.mouse.move(0, 0);
  // What was typed is now the saved sprint: there is nothing new to save.
  await expect(page.getByTestId('sprint-submit')).toBeDisabled();
  // The first sprint of the team is number 1, assigned by the API.
  await expect(page.getByTestId('sprint-title')).toHaveText('Sprint 1');
  // Now there is an active sprint: the button to close it shows, and does nothing yet.
  await expect(page.getByTestId('sprint-close-title')).toHaveText('Cerrar sprint activo');
  await expect(page.getByTestId('sprint-close-open')).toBeVisible();
  await page.getByTestId('sprint-close-open').click();
  await expect(page.getByTestId('sprint-active-badge')).toBeVisible();

  await page.getByTestId('nav-dashboard').click();

  await expect(page).toHaveURL(teamUrl);
  await expect(page.getByTestId('sprint-day')).toHaveText('Día 1 de 10');
  await expect(page.getByTestId('sprint-number')).toHaveText('Sprint 1');
  await expect(page.getByTestId('sprint-progress')).toHaveAttribute('value', '1');
  await expect(page.getByTestId('sprint-progress')).toHaveAttribute('max', '10');
  await expect(page.getByTestId('ceremony-time')).toHaveText(/\d{1,2}:\d{2}/);
  await expect(page.getByTestId('ceremony-day')).toContainText('Reunión diaria');
  await expect(page.getByTestId('join-room')).toBeDisabled();
  await expect(page.getByTestId('join-hint')).toContainText('Se habilita a las');
});

test('when the daily is minutes away the room is open, and pressing it takes to the room', async () => {
  // Five minutes ahead that cross midnight would put today's daily in the past.
  test.skip(
    bogotaDateIn(0) !== new Intl.DateTimeFormat('en-CA', { timeZone: ZONE }).format(new Date(Date.now() + 5 * 60_000)),
    'the next five minutes cross midnight',
  );
  await openSprintSettings();
  // Saved as it is, there is nothing to send; a new time turns the button on.
  await expect(page.getByTestId('sprint-submit')).toBeDisabled();
  await fillDailyTime(bogotaTimeIn(5));
  await expect(page.getByTestId('sprint-submit')).toBeEnabled();
  await page.getByTestId('sprint-submit').click();
  await expect(page.getByTestId('toast-success').last()).toHaveText(/Sprint guardado\./);
  await page.mouse.move(0, 0);
  await page.getByTestId('nav-dashboard').click();

  await expect(page.getByTestId('join-room')).toBeEnabled();
  await expect(page.getByTestId('join-hint')).toHaveCount(0);
  await page.getByTestId('join-room').click();
  // What happens inside the room is told by room.spec.ts (AGI-60).
  await expect(page).toHaveURL(`${teamUrl}/room`);
  await page.goto(teamUrl);
  await expect(page.getByTestId('join-room')).toBeVisible();
});

test('a success toast goes away by itself, a few seconds after it appeared', async () => {
  await page.getByTestId('nav-dashboard').click();
  await expect(page.getByTestId('toast-success')).toHaveCount(0, { timeout: 10_000 });
});

test('switching team leads to the selector even with a single team, with the way to create another', async () => {
  await page.getByTestId('change-team').click();

  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams$`));
  await expect(page.getByTestId('team-option-name')).toHaveText(TEAM);
  await expect(page.locator(`a[href="/${TENANT}/teams/new"]`)).toBeVisible();
  // Time for the selector to send her straight back into the team, if it were going to.
  await page.waitForTimeout(1_500);
  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams$`));

  await page.getByTestId('team-option-name').click();
  await expect(page).toHaveURL(teamUrl);
});

test('on a phone the cards stack, nothing scrolls sideways and the room is in reach', async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(teamUrl);

  await expect(page.getByTestId('sprint-card')).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  const sprint = await page.getByTestId('sprint-card').boundingBox();
  const ceremony = await page.getByTestId('ceremony-card').boundingBox();
  expect(ceremony!.y).toBeGreaterThan(sprint!.y + sprint!.height - 1);
  await page.getByTestId('join-room').scrollIntoViewIfNeeded();
  await expect(page.getByTestId('join-room')).toBeInViewport();
});
