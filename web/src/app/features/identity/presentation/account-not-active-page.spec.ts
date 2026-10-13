import { TestBed } from '@angular/core/testing';

import { FakeAuthSession, provideFakeAuthSession } from '@testing/auth';
import { provideTestI18n } from '@testing/i18n';

import { AccountNotActivePage } from './account-not-active-page';

describe('AccountNotActivePage', () => {
  let session: FakeAuthSession;
  let page: HTMLElement;

  beforeEach(async () => {
    session = new FakeAuthSession(true);
    TestBed.configureTestingModule({
      providers: [provideTestI18n(), provideFakeAuthSession(session)],
    });
    const fixture = TestBed.createComponent(AccountNotActivePage);
    await fixture.whenStable();
    page = fixture.nativeElement as HTMLElement;
  });

  const byTestId = (id: string): HTMLElement =>
    page.querySelector<HTMLElement>(`[data-testid="${id}"]`)!;

  it('says that the account is not active in this organization', () => {
    expect(byTestId('account-not-active-title').textContent).toContain(
      'Tu cuenta no está activa en esta organización',
    );
  });

  it('offers to sign out and ends the session once, however many times it is pressed', () => {
    const button = byTestId('account-not-active-sign-out') as HTMLButtonElement;
    expect(button.textContent).toContain('Cerrar sesión');

    button.click();
    button.click();

    expect(session.signOuts).toHaveSize(1);
  });
});
