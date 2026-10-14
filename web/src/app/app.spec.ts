import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Notifier } from '@core/notifications/notifier';
import { provideTestI18n } from '@testing/i18n';

import { App } from './app';

describe('App', () => {
  async function render(): Promise<{
    fixture: ReturnType<typeof TestBed.createComponent<App>>;
    element: HTMLElement;
  }> {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([]), provideTestI18n()],
    });
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    return { fixture, element: fixture.nativeElement as HTMLElement };
  }

  it('leaves the frame of each screen to its route', async () => {
    const { element } = await render();

    expect(element.querySelector('router-outlet')).not.toBeNull();
    expect(element.querySelector('header')).toBeNull();
  });

  it('shows over any screen what the notifier says, and closes it on request', async () => {
    const { fixture, element } = await render();

    TestBed.inject(Notifier).success('teams.sprint.saved');
    await fixture.whenStable();

    expect(element.querySelector('[role="status"]')?.textContent).toContain('Sprint guardado.');
    const close = element.querySelector<HTMLButtonElement>('[data-testid="toast-close"]')!;
    expect(close.getAttribute('aria-label')).toBe('Cerrar aviso');

    close.click();
    await fixture.whenStable();

    expect(element.querySelectorAll('[data-testid="toast-message"]').length).toBe(0);
  });

  it('keeps a success on screen while the person points at it', async () => {
    const { fixture, element } = await render();
    const notifier = TestBed.inject(Notifier);
    notifier.success('teams.sprint.saved');
    await fixture.whenStable();

    element
      .querySelector('[data-testid="toast-success"]')!
      .dispatchEvent(new MouseEvent('mouseenter'));
    const paused = notifier.notifications()[0];

    expect(paused?.kind).toBe('success');
  });
});
