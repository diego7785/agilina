import { type Routes } from '@angular/router';

import { authGuard, entranceGuard } from '@core/auth/auth.guard';
import { tenantGuard, tenantMatch } from '@core/tenant/tenant.guard';
import { AppShell } from '@layout/app-shell/app-shell';
import { CenteredLayout } from '@layout/centered-layout/centered-layout';

/** The page for an address that names no organization, inside the frame of the sign-in. */
const notFound: Routes = [
  {
    path: '',
    component: CenteredLayout,
    children: [
      {
        path: '',
        loadComponent: () =>
          import('@features/tenancy/presentation/not-found-page').then((m) => m.NotFoundPage),
        title: 'Agilina',
      },
    ],
  },
];

/**
 * Screen map of the product. Every screen is lazy-loaded and arrives with the story that
 * builds it, inside the layout its mockup asks for: the team selector and its form in the
 * centered frame, the rest under the application header.
 *
 * Every tenant is an organization with its own login, so every screen lives under the tenant's
 * name (`/acme/teams`, AD-29): the first segment decides which realm signs the person in and
 * which database the API uses. `/` names no organization and is not found.
 *
 * Public screens: `/:tenant/activate` (the account activation, HU-02) and `/:tenant/status`
 * (the environment status, which proves that the application talks to the API). The entrance,
 * `/:tenant`, sends the signed-in to their teams and everybody else to sign in (HU-03). The
 * routes of the teams need a session: the guard takes the person to sign in and brings them
 * back to the page they asked for. It is comfort, not security: the API decides who sees a team.
 * That includes the team settings (Team and Sprint), which only an admin may open: no guard checks
 * the role, since it would hide the API's 403, and the screen shows "no access" with it. The room
 * of the daily follows the same idea: the API says who may enter it.
 */
export const routes: Routes = [
  { path: 'not-found', children: notFound },
  {
    path: ':tenant',
    canMatch: [tenantMatch],
    canActivate: [tenantGuard],
    children: [
      {
        path: 'teams',
        component: CenteredLayout,
        canActivate: [authGuard],
        children: [
          {
            path: '',
            loadComponent: () =>
              import('@features/teams/presentation/team-selector-page').then(
                (m) => m.TeamSelectorPage,
              ),
            title: 'Agilina',
          },
          {
            // Before any team id, so that it is never read as one.
            path: 'new',
            loadComponent: () =>
              import('@features/teams/presentation/create-team-page').then((m) => m.CreateTeamPage),
            title: 'Agilina',
          },
        ],
      },
      {
        // A valid session of someone who is not an active user of this tenant (AGI-123). It asks
        // nothing of the API, so it cannot bounce between the application and Keycloak.
        path: 'account-not-active',
        component: CenteredLayout,
        canActivate: [authGuard],
        children: [
          {
            path: '',
            loadComponent: () =>
              import('@features/identity/presentation/account-not-active-page').then(
                (m) => m.AccountNotActivePage,
              ),
            title: 'Agilina',
          },
        ],
      },
      {
        path: '',
        component: AppShell,
        children: [
          {
            // Never renders: the guard always sends the person somewhere else.
            path: '',
            pathMatch: 'full',
            canActivate: [entranceGuard],
            children: [],
          },
          {
            path: 'status',
            loadComponent: () =>
              import('@features/status/presentation/status-page').then((m) => m.StatusPage),
            title: 'Agilina',
          },
          {
            // The activation link of the invitation email: /<tenant>/activate#t=<token>.
            path: 'activate',
            loadComponent: () =>
              import('@features/identity/presentation/activate-page').then((m) => m.ActivatePage),
            title: 'Agilina',
          },
          {
            path: 'teams/:teamId',
            canActivate: [authGuard],
            loadComponent: () =>
              import('@features/teams/presentation/team-dashboard-page').then(
                (m) => m.TeamDashboardPage,
              ),
            title: 'Agilina',
          },
          {
            // The room of the team's daily (AGI-60). No guard checks the window or the
            // participants: the API decides whether it issues the token, and the room says why not.
            path: 'teams/:teamId/room',
            canActivate: [authGuard],
            loadComponent: () =>
              import('@features/ceremonies/presentation/room-page').then((m) => m.RoomPage),
            title: 'Agilina',
          },
          {
            // Settings → Team (HU-06): the members of the team, for its admins.
            path: 'teams/:teamId/settings',
            canActivate: [authGuard],
            loadComponent: () =>
              import('@features/teams/presentation/team-settings-page').then(
                (m) => m.TeamSettingsPage,
              ),
            title: 'Agilina',
          },
          {
            // Settings → Sprint (HU-07): the active sprint and its daily, for the team's admins.
            path: 'teams/:teamId/settings/sprint',
            canActivate: [authGuard],
            loadComponent: () =>
              import('@features/teams/presentation/team-sprint-settings-page').then(
                (m) => m.TeamSprintSettingsPage,
              ),
            title: 'Agilina',
          },
        ],
      },
    ],
  },
  // `/`, a name that cannot be a tenant's and anything under it that does not exist.
  { path: '**', redirectTo: 'not-found' },
];
