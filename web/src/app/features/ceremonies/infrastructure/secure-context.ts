import { InjectionToken } from '@angular/core';

/**
 * Whether the page runs in a secure context (HTTPS, or `localhost`), the only place where
 * browsers offer the microphone. A token, so that a test can say no.
 */
export const SECURE_CONTEXT = new InjectionToken<boolean>('SECURE_CONTEXT', {
  providedIn: 'root',
  factory: () => globalThis.isSecureContext,
});
