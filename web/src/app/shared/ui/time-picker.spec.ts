import { Component, signal } from '@angular/core';
import { TestBed, type ComponentFixture } from '@angular/core/testing';

import { parseTime, TimePicker } from './time-picker';

@Component({
  imports: [TimePicker],
  template: `
    <label for="daily">Hora</label>
    <agl-time-picker
      inputId="daily"
      testId="daily-time"
      describedBy="daily-problem"
      placeholder="Elige una hora"
      listLabel="Horas"
      [invalid]="invalid()"
      [(value)]="value"
      (touched)="touches.set(touches() + 1)"
    />
    <p id="daily-problem">Elige la hora.</p>
    <button type="button" id="elsewhere">Otro</button>
  `,
})
class Host {
  readonly value = signal('09:00');
  readonly invalid = signal(false);
  readonly touches = signal(0);
}

describe('TimePicker', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;
  let root: HTMLElement;

  beforeEach(async () => {
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    root = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  });

  function box(): HTMLInputElement {
    return root.querySelector<HTMLInputElement>('#daily')!;
  }

  function list(): HTMLElement {
    return root.querySelector<HTMLElement>('[role="listbox"]')!;
  }

  function option(time: string): HTMLElement | null {
    return root.querySelector<HTMLElement>(`#daily-time-${time.replace(':', '')}`);
  }

  function active(): string {
    const id = box().getAttribute('aria-activedescendant');
    return id === null ? '' : (root.querySelector(`#${id}`)?.textContent.trim() ?? '');
  }

  async function open(): Promise<void> {
    box().click();
    await fixture.whenStable();
  }

  async function type(text: string): Promise<void> {
    box().value = text;
    box().dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  async function press(key: string, init: KeyboardEventInit = {}): Promise<void> {
    box().dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...init }));
    await fixture.whenStable();
  }

  it('is a combobox named by its label that shows the chosen time', () => {
    const label = root.querySelector('label')!;
    expect(box().id).toBe(label.htmlFor);
    expect(box().getAttribute('role')).toBe('combobox');
    expect(box().value).toBe('09:00');
    expect(box().getAttribute('data-testid')).toBe('daily-time');
    expect(box().getAttribute('aria-expanded')).toBe('false');
    expect(list().hidden).toBeTrue();
  });

  it('starts empty, saying what to do, when no time is chosen', async () => {
    host.value.set('');
    await fixture.whenStable();

    expect(box().value).toBe('');
    expect(box().placeholder).toBe('Elige una hora');
  });

  it('is described by its error and shows when it is invalid', async () => {
    host.invalid.set(true);
    await fixture.whenStable();

    expect(box().getAttribute('aria-describedby')).toBe('daily-problem');
    expect(box().getAttribute('aria-invalid')).toBe('true');
  });

  it('opens a list of times every fifteen minutes on the chosen one', async () => {
    await open();

    expect(box().getAttribute('aria-expanded')).toBe('true');
    expect(list().hidden).toBeFalse();
    expect(list().getAttribute('aria-label')).toBe('Horas');
    expect(root.querySelectorAll('[role="option"]').length).toBe(96);
    expect(option('09:15')).not.toBeNull();
    expect(option('09:05')).toBeNull();
    expect(active()).toBe('09:00');
    expect(option('09:00')!.getAttribute('aria-selected')).toBe('true');
  });

  it('picks a time with a click, closes and keeps the focus on the box', async () => {
    await open();

    option('10:30')!.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
    await fixture.whenStable();

    expect(host.value()).toBe('10:30');
    expect(box().value).toBe('10:30');
    expect(list().hidden).toBeTrue();
    expect(document.activeElement).toBe(box());
  });

  it('moves through the times with the arrows and picks one with Enter', async () => {
    box().focus();
    await press('ArrowDown');
    expect(list().hidden).toBeFalse();
    expect(active()).toBe('09:00');

    await press('ArrowDown');
    await press('ArrowDown');
    await press('ArrowUp');
    expect(active()).toBe('09:15');

    await press('Enter');
    expect(host.value()).toBe('09:15');
    expect(list().hidden).toBeTrue();
  });

  it('goes around the day at its edges', async () => {
    host.value.set('23:45');
    await fixture.whenStable();
    await open();

    await press('ArrowDown');

    expect(active()).toBe('00:00');
  });

  it('closes with Escape without changing the time, and counts as having been there', async () => {
    await open();
    await press('ArrowDown');

    await press('Escape');

    expect(list().hidden).toBeTrue();
    expect(host.value()).toBe('09:00');
    expect(host.touches()).toBe(1);
  });

  it('takes a typed time as soon as it is one, at any minute', async () => {
    await type('7:05');

    expect(host.value()).toBe('07:05');
  });

  it('leaves the box without a time while what is typed is not one', async () => {
    await type('25:00');
    expect(host.value()).toBe('');

    box().dispatchEvent(new Event('blur'));
    await fixture.whenStable();

    expect(box().value).toBe('');
    expect(host.touches()).toBe(1);
  });

  it('follows what is typed in the open list', async () => {
    await open();

    await type('14:20');

    expect(active()).toBe('14:30');
  });

  it('opens on the next time of the clock when none is chosen', async () => {
    jasmine.clock().install();
    jasmine.clock().mockDate(new Date(2026, 9, 19, 8, 7));
    try {
      host.value.set('');
      await fixture.whenStable();
      await open();

      expect(active()).toBe('08:15');
      expect(root.querySelector('[aria-selected="true"]')).toBeNull();
    } finally {
      jasmine.clock().uninstall();
    }
  });

  it('closes when the person clicks elsewhere or moves the focus out', async () => {
    await open();
    document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    await fixture.whenStable();
    expect(list().hidden).toBeTrue();

    await open();
    root.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    box().dispatchEvent(
      new FocusEvent('focusout', {
        bubbles: true,
        relatedTarget: root.querySelector('#elsewhere'),
      }),
    );
    await fixture.whenStable();
    expect(list().hidden).toBeTrue();
  });

  it('opens and closes with the clock button', async () => {
    const button = root.querySelector<HTMLButtonElement>('button[aria-hidden="true"]')!;

    button.click();
    await fixture.whenStable();
    expect(list().hidden).toBeFalse();

    button.click();
    await fixture.whenStable();
    expect(list().hidden).toBeTrue();
  });
});

describe('parseTime', () => {
  it('reads a time with or without the colon and the leading zero', () => {
    expect(parseTime('9:30')).toBe('09:30');
    expect(parseTime('09:30')).toBe('09:30');
    expect(parseTime('0930')).toBe('09:30');
    expect(parseTime(' 23:59 ')).toBe('23:59');
  });

  it('rejects what is not a time of the day', () => {
    expect(parseTime('')).toBeNull();
    expect(parseTime('24:00')).toBeNull();
    expect(parseTime('9:60')).toBeNull();
    expect(parseTime('9')).toBeNull();
    expect(parseTime('nueve')).toBeNull();
  });
});
