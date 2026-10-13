import { expect, test, type Browser, type Page } from '@playwright/test';

import { MAILPIT } from '../playwright.config';

/**
 * HU-06 as an admin lives it, in Settings → Team of the tenant acme: the operator made them the
 * admin of a team of their own (`make test-e2e` did it before this runs, apart from the sign-in
 * story); they see the members, invite a person by email, who activates the account and joins
 * with the chosen role, change that person's role and remove them from the team. A member who
 * opens the screen by its address gets "no access": the API answers 403 and the screen only
 * reacts.
 *
 * Elements are found by their `data-testid` (a member's row by `member-<email>`), which does not
 * move when a text, a label or the markup changes; what the person reads is still checked, on
 * the element found that way.
 *
 * The sprint in progress is not walked here: Settings → Sprint (HU-07) creates it, and its own
 * flows are covered by the integration tests of the API and the unit tests of the web.
 */
const RUN = process.env['E2E_RUN'] ?? '';
const TENANT = 'acme';
const ADMIN_EMAIL = `e2e-admin-${RUN}@example.test`;
const ADMIN_NAME = 'Ada Prueba';
const TEAM = `E2E Integrantes ${RUN}`;
const MEMBER_EMAIL = `e2e-member-${RUN}@example.test`;
const MEMBER_NAME = 'Mario Prueba';
const PASSWORD = 'una-clave-bien-larga-1';
const KEYCLOAK_LOGIN = new RegExp(
  `localhost:8080/realms/agilina-${TENANT}/protocol/openid-connect/auth`,
);
const ACTIVATION_LINK = new RegExp(`https?://\\S+/${TENANT}/activate#t=[\\w-]+`);

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  expect(RUN, 'E2E_RUN: run these tests with `make test-e2e`').not.toBe('');
});

/** The plain-text bodies of the emails Mailpit holds for an address, newest first. */
async function emailsTo(email: string): Promise<string[]> {
  const found = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`);
  const { messages } = (await found.json()) as { messages: { ID: string }[] };
  return Promise.all(
    messages.map(async ({ ID }) => {
      const message = await fetch(`${MAILPIT}/api/v1/message/${ID}`);
      return ((await message.json()) as { Text: string }).Text;
    }),
  );
}

/** Waits until an email for the address matches, and returns its text. */
async function emailMatching(email: string, matches: (text: string) => boolean): Promise<string> {
  for (let attempt = 0; attempt < 20; attempt++) {
    const text = (await emailsTo(email)).find(matches);
    if (text !== undefined) {
      return text;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`No matching email for ${email} arrived in Mailpit`);
}

async function activationLink(email: string): Promise<string> {
  const text = await emailMatching(email, (body) => ACTIVATION_LINK.test(body));
  return (ACTIVATION_LINK.exec(text) as RegExpExecArray)[0];
}

/** Activates the account from the invitation email and signs in: the person lands on their
 * only team. */
async function activateAndSignIn(page: Page, email: string): Promise<void> {
  await page.goto(await activationLink(email));
  await page.getByTestId('activate-password').fill(PASSWORD);
  await page.getByTestId('activate-confirmation').fill(PASSWORD);
  await page.getByTestId('activate-submit').click();

  await expect(page).toHaveURL(KEYCLOAK_LOGIN);
  await expect(page.getByTestId('login-email')).toHaveValue(email);
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').click();

  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams/[0-9a-f-]{36}$`));
  await expect(page.getByTestId('header-team')).toHaveText(TEAM);
}

/** A team starts in support mode (HU-04): its admin is the Scrum Master, in the top bar too. */
async function expectHeaderLabel(page: Page, label: string): Promise<void> {
  await expect(page.getByTestId('header-team')).toHaveText(TEAM);
  await expect(page.getByTestId('header-role-label')).toHaveText(label);
  // The person themselves, as the team knows them (`GET /v1/users/me`).
  await expect(page.getByTestId('header-user-name')).toHaveText(ADMIN_NAME);
}

/** A browser without session or cookies: a person arriving cold. */
async function freshPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ locale: 'es-CO' });
  return context.newPage();
}

/** The row of a member in the list. */
function memberRow(page: Page, email: string) {
  return page.getByTestId(`member-${email}`);
}

/** Fills the invitation dialog and sends it. */
async function invite(page: Page, name: string, email: string): Promise<void> {
  await page.getByTestId('invite-open').click();
  await page.getByTestId('invite-full-name').fill(name);
  await page.getByTestId('invite-email').fill(email);
  await page.getByTestId('invite-submit').click();
}

let page: Page;
let settingsUrl = '';

test.beforeAll(async ({ browser }) => {
  page = await freshPage(browser);
});

test.afterAll(async () => {
  await page.context().close();
});

test('the admin opens Settings → Team and sees themself as the only admin', async () => {
  await activateAndSignIn(page, ADMIN_EMAIL);
  await expectHeaderLabel(page, 'Scrum Master');

  await page.getByTestId('nav-settings').click();
  await expect(page).toHaveURL(new RegExp(`/${TENANT}/teams/[0-9a-f-]{36}/settings$`));
  await expect(page.getByTestId('settings-title')).toHaveText('Equipo');
  settingsUrl = page.url();

  const me = memberRow(page, ADMIN_EMAIL);
  await expect(me.getByTestId('member-name')).toHaveText(ADMIN_NAME);
  await expect(me.getByTestId('member-role').locator('option:checked')).toHaveText('Scrum Master');
  await expectHeaderLabel(page, 'Scrum Master');
  // The only admin: the API says why the controls are off, and the screen shows it.
  await expect(me.getByTestId('member-role')).toBeDisabled();
  await expect(me.getByTestId('member-role-blocked')).toContainText('Es el único Scrum Master');
  await expect(me.getByTestId('member-remove')).toBeDisabled();
});

test('inviting someone without an account emails them the activation link', async () => {
  await page.getByTestId('invite-open').click();
  await expect(page.getByTestId('invite-role')).toHaveValue('member');
  await page.getByTestId('invite-full-name').fill(MEMBER_NAME);
  await page.getByTestId('invite-email').fill(MEMBER_EMAIL);
  await page.getByTestId('invite-submit').click();

  await expect(page.getByTestId('invite-outcome')).toContainText(
    'Enviamos la invitación por correo',
  );
  expect(await activationLink(MEMBER_EMAIL)).toMatch(new RegExp(`/${TENANT}/activate#t=`));
});

test('the invited person activates the account and joins as a member, without access to the settings', async ({
  browser,
}) => {
  const memberPage = await freshPage(browser);
  await activateAndSignIn(memberPage, MEMBER_EMAIL);
  // The Settings entry does not exist in the navigation of a member, it is not just hidden.
  await expect(memberPage.getByTestId('nav-dashboard')).toBeVisible();
  await expect(memberPage.getByTestId('nav-settings')).toHaveCount(0);
  // The top bar names the person and their role in this team: a member, whatever the mode.
  await expect(memberPage.getByTestId('header-team')).toHaveText(TEAM);
  await expect(memberPage.getByTestId('header-role-label')).toHaveText('Miembro');
  await expect(memberPage.getByTestId('header-user-name')).toHaveText(MEMBER_NAME);

  // By its address: the API answers 403 and the screen says so.
  await memberPage.goto(settingsUrl);
  await expect(memberPage.getByTestId('settings-forbidden-title')).toHaveText(
    'No tienes acceso a esta pantalla',
  );
  await expect(memberPage.getByTestId('member-role')).toHaveCount(0);
  await memberPage.context().close();
});

test('the admin sees the new member, and inviting them again is refused', async () => {
  await page.reload();
  const member = memberRow(page, MEMBER_EMAIL);
  await expect(member.getByTestId('member-name')).toHaveText(MEMBER_NAME);
  await expect(member.getByTestId('member-role').locator('option:checked')).toHaveText('Miembro');

  await invite(page, MEMBER_NAME, MEMBER_EMAIL);

  await expect(page.getByTestId('invite-problem')).toHaveText(
    'Esta persona ya es integrante del equipo.',
  );
  await page.getByTestId('invite-cancel').click();
  await expect(page.getByTestId('invite-submit')).toHaveCount(0);
});

test('the eye opens the detail of the member in a dialog, and it closes', async () => {
  const member = memberRow(page, MEMBER_EMAIL);

  await member.getByTestId('member-view').click();

  await expect(page.getByTestId('user-detail-title')).toHaveText(MEMBER_NAME);
  await expect(page.getByTestId('user-detail-email')).toHaveText(MEMBER_EMAIL);
  await expect(page.getByTestId('user-detail-label')).toHaveText('Miembro');
  await expect(page.getByTestId('user-detail-joined')).not.toHaveText('');
  await page.getByTestId('user-detail-close').click();
  await expect(page.getByTestId('user-detail-title')).toHaveCount(0);
});

test('the admin changes the role of the member, and back', async () => {
  const member = memberRow(page, MEMBER_EMAIL);
  const me = memberRow(page, ADMIN_EMAIL);

  await member.getByTestId('member-role').selectOption('admin');
  await expect(member.getByTestId('member-role').locator('option:checked')).toHaveText('Scrum Master');
  // With a second admin, the first one is no longer the last: their controls turn on.
  await expect(me.getByTestId('member-role')).toBeEnabled();

  await member.getByTestId('member-role').selectOption('member');
  await expect(member.getByTestId('member-role').locator('option:checked')).toHaveText('Miembro');
  await expect(me.getByTestId('member-role')).toBeDisabled();
});

test('removing the member asks first and warns they stop receiving the meetings', async () => {
  await memberRow(page, MEMBER_EMAIL).getByTestId('member-remove').click();
  await expect(page.getByTestId('remove-title')).toHaveText(
    `¿Eliminar a ${MEMBER_NAME} del equipo?`,
  );
  await expect(page.getByTestId('remove-warning')).toContainText(
    'dejará de pertenecer al equipo y de recibir sus convocatorias',
  );

  await page.getByTestId('remove-confirm').click();

  await expect(page.getByTestId('remove-confirm')).toHaveCount(0);
  await expect(memberRow(page, MEMBER_EMAIL)).toHaveCount(0);
});

test('inviting back someone who has an account adds them at once and notifies them without a link', async () => {
  await invite(page, MEMBER_NAME, MEMBER_EMAIL);

  await expect(page.getByTestId('invite-outcome')).toContainText('ya tenía cuenta en Agilina');
  await expect(memberRow(page, MEMBER_EMAIL).getByTestId('member-role').locator('option:checked')).toHaveText('Miembro');

  const notice = await emailMatching(
    MEMBER_EMAIL,
    (body) => body.includes(TEAM) && !ACTIVATION_LINK.test(body),
  );
  expect(notice).toContain(`/${TENANT}/teams/`);
  expect(notice).not.toContain('#t=');
});
