import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { type ApplicationConfig } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { authInterceptor } from '@core/auth/auth.interceptor';
import { provideAuth } from '@core/auth/provide-auth';
import { RUNTIME_CONFIG, type RuntimeConfig } from '@core/config/runtime-config';
import { httpErrorLoggingInterceptor } from '@core/http/http-error-logging.interceptor';
import { provideI18n } from '@core/i18n/provide-i18n';
import { provideLogging } from '@core/logging/provide-logging';
import { HttpTenantApi } from '@core/tenant/http-tenant.api';
import { TenantPort } from '@core/tenant/tenant.port';
import { RoomAccessPort } from '@features/ceremonies/application/room-access.port';
import { RoomPort } from '@features/ceremonies/application/room.port';
import { HttpRoomAccessApi } from '@features/ceremonies/infrastructure/http-room-access.api';
import { LiveKitRoomAdapter } from '@features/ceremonies/infrastructure/livekit-room.adapter';
import { InvitationPort } from '@features/identity/application/invitation.port';
import { LoginRedirectPort } from '@features/identity/application/login-redirect.port';
import { HttpInvitationApi } from '@features/identity/infrastructure/http-invitation.api';
import { SessionLoginAdapter } from '@features/identity/infrastructure/session-login.adapter';
import { HealthPort } from '@features/status/application/health.port';
import { HttpHealthApi } from '@features/status/infrastructure/http-health.api';
import { SprintsPort } from '@features/teams/application/sprints.port';
import { TeamsPort } from '@features/teams/application/teams.port';
import { UsersPort } from '@features/teams/application/users.port';
import { HttpSprintsApi } from '@features/teams/infrastructure/http-sprints.api';
import { HttpTeamsApi } from '@features/teams/infrastructure/http-teams.api';
import { HttpUsersApi } from '@features/teams/infrastructure/http-users.api';

import { routes } from './app.routes';

/**
 * Composition root of the web application: the only place that knows which
 * adapter serves each port. Zoneless and OnPush are the Angular 22 defaults.
 */
export function createAppConfig(runtimeConfig: RuntimeConfig): ApplicationConfig {
  return {
    providers: [
      { provide: RUNTIME_CONFIG, useValue: runtimeConfig },
      provideLogging(),
      provideRouter(routes, withComponentInputBinding()),
      provideHttpClient(withInterceptors([authInterceptor, httpErrorLoggingInterceptor])),
      provideI18n(),
      provideAuth(),

      { provide: TenantPort, useClass: HttpTenantApi },

      // Ports of the features, bound to their adapters.
      { provide: HealthPort, useClass: HttpHealthApi },
      { provide: InvitationPort, useClass: HttpInvitationApi },
      { provide: LoginRedirectPort, useClass: SessionLoginAdapter },
      { provide: TeamsPort, useClass: HttpTeamsApi },
      { provide: UsersPort, useClass: HttpUsersApi },
      { provide: SprintsPort, useClass: HttpSprintsApi },
      { provide: RoomAccessPort, useClass: HttpRoomAccessApi },
      { provide: RoomPort, useClass: LiveKitRoomAdapter },
    ],
  };
}
