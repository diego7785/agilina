import { defineConfig } from '@playwright/test';

/** Where the environment (`make up`) is reachable from this container (host network). */
export const WEB = process.env['E2E_WEB_URL'] ?? 'http://localhost:4200';
export const MAILPIT = process.env['E2E_MAILPIT_URL'] ?? 'http://localhost:8025';

export default defineConfig({
  testDir: './specs',
  // One story told in order (invite, activate, sign in): the tests share what the first creates.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: WEB,
    // The application and Keycloak follow the browser's language: the texts asserted are Spanish.
    locale: 'es-CO',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    // The stories of the product, told once and in order: they share the accounts they create.
    { name: 'chromium', use: { browserName: 'chromium' }, testIgnore: /room\.spec\.ts/ },
    // The room of the daily (AGI-60), after the stories that activate the person and give her team
    // a daily minutes away. The microphone is a fake device the browser grants without asking.
    // Chromium is the full browser (`channel`): the headless shell that Playwright uses by default
    // has no microphone at all. Firefox is checked by hand (AGI-135): the one Playwright ships does
    // not set up WebRTC with LiveKit, neither local nor Cloud (its ICE fails, TURN included).
    {
      name: 'room-chromium',
      dependencies: ['chromium'],
      testMatch: /room\.spec\.ts/,
      use: {
        browserName: 'chromium',
        channel: 'chromium',
        permissions: ['microphone'],
        launchOptions: { args: ['--use-fake-device-for-media-stream'] },
      },
    },
  ],
});
