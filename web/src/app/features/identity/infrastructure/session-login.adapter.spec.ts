import { TestBed } from '@angular/core/testing';

import { AuthSession } from '@core/auth/auth-session';
import { FakeAuthSession } from '@testing/auth';
import { provideTestTenant } from '@testing/tenant';

import { SessionLoginAdapter } from './session-login.adapter';

describe('SessionLoginAdapter', () => {
  let session: FakeAuthSession;
  let adapter: SessionLoginAdapter;

  beforeEach(() => {
    session = new FakeAuthSession();
    TestBed.configureTestingModule({
      providers: [
        SessionLoginAdapter,
        { provide: AuthSession, useValue: session },
        provideTestTenant('ecomoda'),
      ],
    });
    adapter = TestBed.inject(SessionLoginAdapter);
  });

  it('signs in with the email filled in and lands on the teams of the tenant afterwards', async () => {
    await adapter.redirect('julian@example.test');

    expect(session.signIns).toEqual([
      { returnUrl: '/ecomoda/teams', loginHint: 'julian@example.test' },
    ]);
  });

  it('can also sign in without knowing the email', async () => {
    await adapter.redirect();

    expect(session.signIns).toEqual([{ returnUrl: '/ecomoda/teams' }]);
  });
});
