import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { ToastList, type ToastView } from './toast-list';

@Component({
  imports: [ToastList],
  template: `<agl-toast-list
    [toasts]="toasts()"
    closeLabel="Cerrar aviso"
    (dismissed)="dismissed.push($event)"
    (paused)="paused.push($event)"
    (resumed)="resumed.push($event)"
  />`,
})
class Host {
  readonly toasts = signal<readonly ToastView[]>([]);
  readonly dismissed: number[] = [];
  readonly paused: number[] = [];
  readonly resumed: number[] = [];
}

describe('ToastList', () => {
  async function render(toasts: readonly ToastView[] = []) {
    const fixture = TestBed.createComponent(Host);
    fixture.componentInstance.toasts.set(toasts);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    return { fixture, element, host: fixture.componentInstance };
  }

  const saved: ToastView = { id: 1, kind: 'success', message: 'Sprint guardado.' };
  const failed: ToastView = { id: 2, kind: 'error', message: 'No se pudo guardar.' };

  it('has its two regions in the page even when there is nothing to say', async () => {
    const { element } = await render();

    expect(element.querySelector('[role="status"][aria-live="polite"]')).not.toBeNull();
    expect(element.querySelector('[role="alert"]')).not.toBeNull();
    expect(element.querySelectorAll('[data-testid="toast-message"]').length).toBe(0);
  });

  it('puts a success in the polite region, green and with a check', async () => {
    const { element } = await render([saved]);

    const region = element.querySelector('[role="status"]')!;
    const toast = region.querySelector('[data-testid="toast-success"]')!;
    expect(toast.textContent).toContain('Sprint guardado.');
    expect(toast.querySelector('[data-testid="toast-icon-success"]')).not.toBeNull();
    expect(toast.querySelector('[data-testid="toast-icon-error"]')).toBeNull();
    expect(toast.innerHTML).toContain('border-success');
    expect(toast.innerHTML).not.toContain('danger');
  });

  it('puts an error in the urgent region, red and with an alert', async () => {
    const { element } = await render([failed]);

    const region = element.querySelector('[role="alert"]')!;
    const toast = region.querySelector('[data-testid="toast-error"]')!;
    expect(toast.textContent).toContain('No se pudo guardar.');
    expect(toast.querySelector('[data-testid="toast-icon-error"]')).not.toBeNull();
    expect(toast.innerHTML).toContain('border-danger');
    expect(toast.innerHTML).not.toContain('border-success');
  });

  it('keeps each kind in its own region when both are on screen', async () => {
    const { element } = await render([saved, failed]);

    expect(element.querySelectorAll('[role="status"] [data-testid="toast-message"]').length).toBe(
      1,
    );
    expect(element.querySelectorAll('[role="alert"] [data-testid="toast-message"]').length).toBe(1);
  });

  it('names the close button with the label it receives', async () => {
    const { element } = await render([saved]);

    expect(element.querySelector('[data-testid="toast-close"]')?.getAttribute('aria-label')).toBe(
      'Cerrar aviso',
    );
  });

  it('says which toast the person closed', async () => {
    const { element, host } = await render([saved, failed]);

    element.querySelector<HTMLButtonElement>('[data-testid="toast-error"] button')!.click();

    expect(host.dismissed).toEqual([2]);
  });

  it('says when the pointer or the focus is on a toast and when it leaves', async () => {
    const { element, host } = await render([saved]);
    const toast = element.querySelector('[data-testid="toast-success"]')!;

    toast.dispatchEvent(new MouseEvent('mouseenter'));
    toast.dispatchEvent(new MouseEvent('mouseleave'));
    toast.dispatchEvent(new FocusEvent('focusin'));
    toast.dispatchEvent(new FocusEvent('focusout'));

    expect(host.paused).toEqual([1, 1]);
    expect(host.resumed).toEqual([1, 1]);
  });

  it('does not block clicks on the page behind, only on the toasts', async () => {
    const { element } = await render([saved]);

    expect(element.querySelector('[data-testid="toasts"]')?.className).toContain(
      'pointer-events-none',
    );
    expect(element.querySelector('[data-testid="toast-success"]')?.className).toContain(
      'pointer-events-auto',
    );
  });
});
